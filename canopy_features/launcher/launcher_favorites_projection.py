"""Compose bounded launcher ranking and favorites into one result projection.

Pure, offline and stateless: no Qt, no desktop database, no process launch, no
filesystem walk, no polling and no background work. Callers supply a bounded
catalog of stable app-id/title pairs, an optional ordered favorites snapshot
and a query; this module returns one immutable, deterministic display projection
that a trusted launcher host can render directly.

This is deliberately a *projection*, not a launch decision and not a keyboard:
:mod:`launcher_intent_summary` picks one app and builds argv, and
:mod:`launcher_search_view` binds ranking to a focused title. This module only
answers "which apps do I show, in what order, and which are favorites".

Ranking comes from :mod:`app_search_casefold` and id validation from
:mod:`launcher_favorites`; both are already bounded and tested. A cleared query
shows visible favorites first (in favorites display order) then the rest of the
catalog in catalog order. A non-blank query shows the ranked matches and breaks
equal-score ties in favour of favorites. Every source disagreement, malformed
input or oversized collection fails closed with ``ProjectionError``. The module
launches nothing and proves no running desktop.
"""
from dataclasses import dataclass
from typing import Iterable, Tuple

from canopy_features.launcher.app_search_casefold import (
    ANY,
    MAX_CANDIDATES,
    MAX_RESULTS,
    AppSearchError,
    Match,
    normalize_for_search,
    normalize_name,
    rank_matches,
)
from canopy_features.launcher.launcher_favorites import (
    MAX_FAVORITES,
    valid_app_id,
)

STATUS_READY = "READY"
STATUS_EMPTY = "EMPTY"

__all__ = [
    "MAX_RESULTS",
    "MAX_FAVORITES",
    "STATUS_EMPTY",
    "STATUS_READY",
    "ProjectedRow",
    "FavoritesProjection",
    "ProjectionError",
    "project_results",
]


class ProjectionError(ValueError):
    """Invalid caller input or a broken ranking/favorites agreement."""


@dataclass(frozen=True)
class ProjectedRow:
    """One display row: an app, its match tier, favorite flag and position."""

    app_id: str
    title: str
    score: int
    favorite: bool
    position: int


@dataclass(frozen=True)
class FavoritesProjection:
    """One immutable, bounded result list for the launcher host.

    ``key`` is the bounded caseless search key. ``rows`` is the ordered display
    list with contiguous ``position`` values. ``favorite_count`` is the number
    of rows flagged favorite. ``status`` is ``EMPTY`` when no row survives.
    """

    key: str
    rows: Tuple[ProjectedRow, ...]
    favorite_count: int
    status: str

    def to_dict(self) -> dict:
        """Plain bounded mapping for a host bridge or evidence log."""
        return {
            "key": self.key,
            "rows": [
                {
                    "app_id": row.app_id,
                    "title": row.title,
                    "score": row.score,
                    "favorite": row.favorite,
                    "position": row.position,
                }
                for row in self.rows
            ],
            "favorite_count": self.favorite_count,
            "status": self.status,
        }


def _iterable(value, label):
    if isinstance(value, (str, bytes, bytearray, dict)):
        raise ProjectionError(label + " must be an iterable of pairs")
    try:
        return iter(value)
    except TypeError:
        raise ProjectionError(label + " must be an iterable") from None


def _normalize_catalog(catalog):
    """Validate (app_id, title) pairs; reject any malformed entry."""
    pairs = []
    seen = set()
    for item in _iterable(catalog, "catalog"):
        if len(pairs) >= MAX_CANDIDATES:
            raise ProjectionError("catalog exceeds entry bound")
        if isinstance(item, (str, bytes, bytearray)):
            raise ProjectionError("catalog entries must be pairs")
        try:
            parts = tuple(item)
        except TypeError:
            raise ProjectionError("catalog entries must be pairs") from None
        if len(parts) != 2:
            raise ProjectionError("catalog entries must be pairs")
        app_id, title = parts
        if not valid_app_id(app_id):
            raise ProjectionError("invalid stable application id")
        if type(title) is not str or not title:
            raise ProjectionError("invalid application title")
        try:
            normalize_name(title)
        except AppSearchError as exc:
            raise ProjectionError(str(exc)) from exc
        if app_id in seen:
            raise ProjectionError("duplicate application id")
        seen.add(app_id)
        pairs.append((app_id, title))
    if not pairs:
        raise ProjectionError("catalog must not be empty")
    return tuple(pairs)


def _normalize_favorites(favorites, catalog_ids):
    """Validate ids and keep the visible subset in favorites display order.

    The raw snapshot itself is bounded by the favorites domain: a real
    ``FavoritesStore`` never holds more than ``MAX_FAVORITES`` ids, so a longer
    caller-supplied snapshot is out of contract and fails closed even when most
    of its ids are not installed.
    """
    kept = []
    seen = set()
    raw_count = 0
    for app_id in _iterable(favorites, "favorites"):
        raw_count += 1
        if raw_count > MAX_FAVORITES:
            raise ProjectionError("favorites exceed entry bound")
        if not valid_app_id(app_id):
            raise ProjectionError("invalid favorite application id")
        if app_id in seen or app_id not in catalog_ids:
            continue
        seen.add(app_id)
        kept.append(app_id)
    return tuple(kept)


def _build_rows(pairs, matches, favorites, *, blank, limit):
    """Build at most ``limit`` projected rows from validated sources.

    A blank query used to materialize a row for every catalog entry and let
    the caller slice the result down to ``limit``. Favorites are now emitted
    first in display order, then catalog rows, stopping as soon as the bounded
    result is full. Ordering, flags and the later agreement checks are unchanged.
    """
    rows = []
    if blank:
        favset = frozenset(favorites)
        by_id = {app_id: (index, title) for index, (app_id, title)
                 in enumerate(pairs) if app_id in favset}
        for app_id in favorites:
            if len(rows) >= limit:
                break
            index, title = by_id[app_id]
            rows.append((app_id, title, ANY, True, index))
        if len(rows) < limit:
            for index, (app_id, title) in enumerate(pairs):
                if app_id in favset:
                    continue
                rows.append((app_id, title, ANY, False, index))
                if len(rows) >= limit:
                    break
    else:
        for match in matches:
            index = match.index
            if not 0 <= index < len(pairs):
                raise ProjectionError("ranking index out of catalog bounds")
            app_id, title = pairs[index]
            # The ranked name must be the title at the catalog position the
            # ranking module reported; otherwise it points at a wrong app.
            if match.name != title:
                raise ProjectionError("ranking and catalog disagree")
            rows.append((app_id, title, match.score,
                         app_id in favorites, index))
        # Favorites lead only among equal scores; a better tier still wins.
        rows.sort(key=lambda row: (-row[2], not row[3], row[4]))
    return rows


def _finalize(key, raw_rows, favorites):
    """Assign positions, verify source agreement and build the record."""
    rows = tuple(
        ProjectedRow(app_id=app_id, title=title, score=score,
                     favorite=favorite, position=position)
        for position, (app_id, title, score, favorite, _index)
        in enumerate(raw_rows)
    )
    favset = frozenset(favorites)
    for row in rows:
        if row.favorite != (row.app_id in favset):
            raise ProjectionError("favorite flag disagrees with favorites")
    favorite_count = sum(1 for row in rows if row.favorite)
    if [row.position for row in rows] != list(range(len(rows))):
        raise ProjectionError("projection positions are not contiguous")
    status = STATUS_READY if rows else STATUS_EMPTY
    return FavoritesProjection(key, rows, favorite_count, status)


def project_results(query, catalog, *, favorites=(), limit=MAX_RESULTS):
    """Project ``catalog`` into one bounded, favorites-aware result list.

    A blank query yields favorites first then the remaining installed apps; a
    non-blank query yields ranked matches with favorites leading equal-score
    ties. Unknown favorites are hidden non-destructively. Invalid types,
    oversized inputs and any ranking/catalog disagreement raise
    ``ProjectionError``. Neither input collection is mutated and nothing is
    launched.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise ProjectionError("invalid result limit")

    try:
        key = normalize_for_search(query)
    except AppSearchError as exc:
        raise ProjectionError(str(exc)) from exc

    pairs = _normalize_catalog(catalog)
    catalog_ids = frozenset(app_id for app_id, _ in pairs)
    favs = _normalize_favorites(favorites, catalog_ids)
    titles = tuple(title for _, title in pairs)

    try:
        matches = rank_matches(query, titles, limit=limit)
    except AppSearchError as exc:
        raise ProjectionError(str(exc)) from exc

    blank = not key
    raw = _build_rows(pairs, matches, favs, blank=blank, limit=limit)
    return _finalize(key, raw, favs)
