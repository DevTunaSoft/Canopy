"""Compose launcher search, favorites and a shell-free argv into one decision.

Pure, offline and stateless: no Qt, no desktop database, no process launch, no
filesystem walk, no polling and no background work. Callers supply a bounded
application catalog, an ordered favorites snapshot and an optional host
allowlist; this module returns one immutable decision record that a trusted
host can act on.

The composition is deliberately narrow: ranking comes from
``app_search_ranking`` and the argv from ``launch_argv.gio_launch_argv``. Every
emitted argv token is a plain, bounded, shell-free string, and an app that the
host does not approve yields a fail-closed ``NOT_APPROVED`` record with no
argv. Validating the catalog before ranking means a single malformed entry
refuses the whole summary rather than silently biasing the result.

This module alone is not a working desktop; a host must wire the record into
the compiled launcher and keep its own launch allowlist.
"""

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from canopy_features.apps.launch_argv import (
    DESKTOP_ID,
    LaunchArgvError,
    gio_launch_argv,
)
from canopy_features.launcher.app_search_ranking import RankedMatch, rank_applications

MAX_QUERY_CHARS = 256
MAX_CATALOG_ENTRIES = 1024
MAX_FAVORITES = 16

STATUS_READY = "READY"
STATUS_NO_MATCH = "NO_MATCH"
STATUS_NOT_APPROVED = "NOT_APPROVED"

__all__ = [
    "MAX_QUERY_CHARS",
    "MAX_CATALOG_ENTRIES",
    "MAX_FAVORITES",
    "STATUS_READY",
    "STATUS_NO_MATCH",
    "STATUS_NOT_APPROVED",
    "LauncherIntentError",
    "LauncherIntentSummary",
    "summarize_launcher_intent",
]


class LauncherIntentError(ValueError):
    """Invalid caller-supplied query, catalog or favorites input."""


@dataclass(frozen=True)
class LauncherIntentSummary:
    """One bounded, immutable launcher decision for a trusted host.

    ``argv`` is empty unless ``status`` is ``READY``. ``matches`` are the
    ranked application titles for the supplied query; ``favorites`` are the
    installed favorite app ids in display order.
    """

    query: str
    matches: Tuple[RankedMatch, ...]
    favorites: Tuple[str, ...]
    selected_app_id: Optional[str]
    argv: Tuple[str, ...]
    status: str

    def to_dict(self) -> dict:
        """Plain bounded mapping for a host bridge or evidence log."""
        return {
            "query": self.query,
            "matches": [
                {
                    "name": match.name,
                    "tier": match.tier,
                    "score": match.score,
                    "index": match.index,
                }
                for match in self.matches
            ],
            "favorites": list(self.favorites),
            "selected_app_id": self.selected_app_id,
            "argv": list(self.argv),
            "status": self.status,
        }


def _normalize_query(query: str) -> str:
    if type(query) is not str:
        raise LauncherIntentError("query must be a string")
    if len(query) > MAX_QUERY_CHARS:
        raise LauncherIntentError("query exceeds character bound")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in query):
        raise LauncherIntentError("query contains a control character")
    return query


def _iterable(value, label):
    if isinstance(value, (str, bytes, bytearray, dict)):
        raise LauncherIntentError(f"{label} must be an iterable")
    try:
        return iter(value)
    except TypeError:
        raise LauncherIntentError(f"{label} must be an iterable") from None


def _normalize_catalog(catalog) -> Tuple[Tuple[str, str], ...]:
    """Validate (desktop_id, title) pairs; reject any malformed entry."""
    pairs = []
    seen = set()
    for item in _iterable(catalog, "catalog"):
        if len(pairs) >= MAX_CATALOG_ENTRIES:
            raise LauncherIntentError("catalog exceeds entry bound")
        if isinstance(item, (str, bytes, bytearray)):
            raise LauncherIntentError("catalog entries must be pairs")
        try:
            parts = tuple(item)
        except TypeError:
            raise LauncherIntentError("catalog entries must be pairs") from None
        if len(parts) != 2:
            raise LauncherIntentError("catalog entries must be pairs")
        app_id, title = parts
        if type(app_id) is not str or DESKTOP_ID.fullmatch(app_id) is None:
            raise LauncherIntentError("invalid desktop application id")
        if type(title) is not str or not title:
            raise LauncherIntentError("invalid application title")
        if app_id in seen:
            raise LauncherIntentError("duplicate desktop application id")
        seen.add(app_id)
        pairs.append((app_id, title))
    if not pairs:
        raise LauncherIntentError("catalog must not be empty")
    return tuple(pairs)


def _normalize_favorites(favorites, catalog_ids) -> Tuple[str, ...]:
    """Keep installed favorites in order; hide unknown ids non-destructively."""
    kept = []
    seen = set()
    for app_id in _iterable(favorites, "favorites"):
        if type(app_id) is not str:
            raise LauncherIntentError("favorite must be a string")
        if app_id not in catalog_ids or app_id in seen:
            continue
        if len(kept) >= MAX_FAVORITES:
            raise LauncherIntentError("favorites exceed entry bound")
        seen.add(app_id)
        kept.append(app_id)
    return tuple(kept)


def summarize_launcher_intent(
    query: str,
    catalog: Iterable[Tuple[str, str]],
    *,
    favorites: Iterable[str] = (),
    allowed_app_ids: Optional[Iterable[str]] = None,
) -> LauncherIntentSummary:
    """Compose one deterministic launcher decision; never launches anything.

    For a non-blank query the first ranked match is selected. For a cleared
    search the first visible favorite is selected, falling back to the first
    catalog entry. An app absent from the host allowlist produces
    ``NOT_APPROVED`` with an empty argv.
    """
    query = _normalize_query(query)
    pairs = _normalize_catalog(catalog)
    titles = tuple(title for _, title in pairs)

    # First occurrence wins for duplicate titles, so selection from a ranked
    # title is deterministic and independent of dict/set iteration order.
    id_by_title = {}
    for app_id, title in pairs:
        id_by_title.setdefault(title, app_id)

    matches = rank_applications(query, titles)
    catalog_ids = frozenset(app_id for app_id, _ in pairs)
    visible_favorites = _normalize_favorites(favorites, catalog_ids)

    if not matches:
        return LauncherIntentSummary(
            query, (), visible_favorites, None, (), STATUS_NO_MATCH)

    if query.strip():
        selected = id_by_title[matches[0].name]
    elif visible_favorites:
        selected = visible_favorites[0]
    else:
        selected = pairs[0][0]

    try:
        argv = gio_launch_argv(selected, allowed_app_ids=allowed_app_ids)
    except LaunchArgvError:
        return LauncherIntentSummary(
            query, matches, visible_favorites, selected, (), STATUS_NOT_APPROVED)

    return LauncherIntentSummary(
        query, matches, visible_favorites, selected, argv, STATUS_READY)
