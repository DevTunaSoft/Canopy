"""Pure, bounded desktop-entry-to-catalog ingestion for the Classic launcher.

The host supplies already-parsed ``DesktopEntry`` records paired with validated
desktop ids; this module returns one immutable, deterministic catalog snapshot.
It performs no filesystem access, process launch, polling, cache retention or
visual work, and it never claims a running desktop.

Every input field is validated fail-closed. Hidden and NoDisplay entries are
skipped non-destructively, duplicate ids collapse to the first occurrence, and
the fixed negative claims describe what the emitted snapshot does not contain.
No id, title or category value is copied into ``to_dict``, so untrusted text
cannot reach a log or a host bridge through the diagnostic view.
"""
from dataclasses import dataclass
from typing import Tuple

from canopy_features.apps.launch_argv import DESKTOP_ID
from canopy_features.launcher.desktop_entry_parser import DesktopEntry

MAX_ENTRIES = 1024
MAX_TITLE_CHARS = 256
MAX_CATEGORY_TOKENS = 64

CLAIM_NO_FILESYSTEM_IO = "no_filesystem_io"
CLAIM_NO_PROCESS_LAUNCH = "no_process_launch"
CLAIM_NO_VISUAL_CHANGE = "no_visual_change"
CLAIM_NO_DUPLICATE_IDS_EMITTED = "no_duplicate_ids_emitted"
CLAIM_NO_HIDDEN_ENTRIES_EMITTED = "no_hidden_entries_emitted"
CLAIM_NO_INVALID_ENTRIES_ACCEPTED = "no_invalid_entries_accepted"

FIXED_CLAIMS = (
    CLAIM_NO_DUPLICATE_IDS_EMITTED,
    CLAIM_NO_FILESYSTEM_IO,
    CLAIM_NO_HIDDEN_ENTRIES_EMITTED,
    CLAIM_NO_INVALID_ENTRIES_ACCEPTED,
    CLAIM_NO_PROCESS_LAUNCH,
    CLAIM_NO_VISUAL_CHANGE,
)

__all__ = [
    "CLAIM_NO_DUPLICATE_IDS_EMITTED",
    "CLAIM_NO_FILESYSTEM_IO",
    "CLAIM_NO_HIDDEN_ENTRIES_EMITTED",
    "CLAIM_NO_INVALID_ENTRIES_ACCEPTED",
    "CLAIM_NO_PROCESS_LAUNCH",
    "CLAIM_NO_VISUAL_CHANGE",
    "FIXED_CLAIMS",
    "MAX_CATEGORY_TOKENS",
    "MAX_ENTRIES",
    "MAX_TITLE_CHARS",
    "CatalogIngestError",
    "CatalogRow",
    "LauncherCatalogSnapshot",
    "compose_launcher_catalog",
]


class CatalogIngestError(ValueError):
    """Malformed, oversized or untrusted catalog source input."""


@dataclass(frozen=True)
class CatalogRow:
    """One validated, host-ready catalog entry."""

    app_id: str
    title: str
    categories: Tuple[str, ...]


@dataclass(frozen=True)
class LauncherCatalogSnapshot:
    """One immutable, bounded catalog; diagnostics are counts and claims only."""

    rows: Tuple[CatalogRow, ...]
    raw_count: int = 0
    hidden_count: int = 0
    duplicate_id_count: int = 0
    duplicate_title_count: int = 0
    claims: Tuple[str, ...] = ()

    def to_pairs(self):
        """Bounded ``(app_id, title)`` bridge for launcher_intent_summary."""
        return tuple((row.app_id, row.title) for row in self.rows)

    def to_dict(self):
        """Plain diagnostics mapping; no id, title or category is echoed."""
        return {
            "row_count": len(self.rows),
            "raw_count": self.raw_count,
            "hidden_count": self.hidden_count,
            "duplicate_id_count": self.duplicate_id_count,
            "duplicate_title_count": self.duplicate_title_count,
            "claims": list(self.claims),
        }


def _check_title(title):
    if type(title) is not str or not title or len(title) > MAX_TITLE_CHARS:
        raise CatalogIngestError("invalid application title")
    try:
        title.encode("utf-8", "strict")
    except UnicodeError:
        raise CatalogIngestError("application title is not valid Unicode") from None
    if any(ord(char) < 0x20 or ord(char) == 0x7f for char in title):
        raise CatalogIngestError("application title contains a control character")


def _check_categories(value):
    if type(value) is not tuple or len(value) > MAX_CATEGORY_TOKENS:
        raise CatalogIngestError("invalid application categories")
    if not all(type(token) is str and token for token in value):
        raise CatalogIngestError("invalid application category token")


def compose_launcher_catalog(entries, *, max_entries=MAX_ENTRIES):
    """Build one bounded catalog snapshot from parsed entry records.

    ``entries`` is an iterable of ``(app_id, DesktopEntry)`` pairs. Every source
    is validated before any decision is emitted. Hidden entries and duplicate
    ids are counted, never copied into the result; the first occurrence wins.
    """
    if isinstance(entries, (str, bytes, bytearray, dict)) or not hasattr(entries, "__iter__"):
        raise CatalogIngestError("entries must be an iterable of pairs")
    if type(max_entries) is not int or not 1 <= max_entries <= MAX_ENTRIES:
        raise CatalogIngestError("invalid entry bound")

    rows = []
    seen_ids = set()
    seen_titles = set()
    raw_count = 0
    hidden_count = 0
    duplicate_id_count = 0
    duplicate_title_count = 0

    for item in entries:
        raw_count += 1
        if raw_count > max_entries:
            raise CatalogIngestError("too many catalog entries")
        if isinstance(item, (str, bytes, bytearray)):
            raise CatalogIngestError("catalog entries must be pairs")
        try:
            parts = tuple(item)
        except TypeError:
            raise CatalogIngestError("catalog entries must be pairs") from None
        if len(parts) != 2:
            raise CatalogIngestError("catalog entries must be pairs")
        app_id, record = parts
        if type(app_id) is not str or DESKTOP_ID.fullmatch(app_id) is None:
            raise CatalogIngestError("invalid desktop application id")
        if not isinstance(record, DesktopEntry):
            raise CatalogIngestError("expected an already-parsed DesktopEntry")
        if record.type != "Application":
            raise CatalogIngestError("only Application entries are catalogued")
        _check_title(record.name)
        _check_categories(record.categories)

        if record.hidden or record.no_display:
            hidden_count += 1
            continue
        if app_id in seen_ids:
            duplicate_id_count += 1
            continue
        seen_ids.add(app_id)
        folded = record.name.casefold()
        if folded in seen_titles:
            duplicate_title_count += 1
        else:
            seen_titles.add(folded)
        rows.append(
            CatalogRow(app_id=app_id, title=record.name,
                       categories=tuple(record.categories)))

    return LauncherCatalogSnapshot(
        rows=tuple(rows),
        raw_count=raw_count,
        hidden_count=hidden_count,
        duplicate_id_count=duplicate_id_count,
        duplicate_title_count=duplicate_title_count,
        claims=FIXED_CLAIMS,
    )
