"""One immutable, no-echo dock window-group preview for a host.

Pure state module: it composes the already-tested
``window_grouping.group_windows_by_desktop_id`` with ``dock_pinned_items`` into
one bounded fail-closed preview. It never reads geometry, QML, artwork or a
running desktop, never enumerates windows itself, and never launches anything.

The record carries counts and fixed negative claims only. Window ids, desktop
ids and dock labels are never copied into it or its ``to_dict`` bridge.
"""
from dataclasses import dataclass
from typing import Tuple

from canopy_features.dock.dock_pinned_items import PinnedItems
from canopy_features.dock.window_grouping import (
    GroupingResult,
    WindowGroup,
    WindowRecord,
    WindowGroupingError,
    group_windows_by_desktop_id,
)

STATUS_READY = "READY"
STATUS_DENIED = "DENIED"

REASON_OK = "ok"
REASON_INVALID_INPUT = "invalid_input"
REASON_UNPINNED_GROUP = "unpinned_group"
REASON_SOURCE_DISAGREEMENT = "source_disagreement"

CLAIM_NO_WINDOW_IDS_ECHOED = "no_window_ids_echoed"
CLAIM_NO_DESKTOP_IDS_ECHOED = "no_desktop_ids_echoed"
CLAIM_NO_LABELS_ECHOED = "no_labels_echoed"
CLAIM_NO_GEOMETRY_READ = "no_geometry_read"
CLAIM_NO_PROCESS_LAUNCHED = "no_process_launched"
CLAIM_NO_VISUAL_CHANGE = "no_visual_change"

FIXED_CLAIMS = (
    CLAIM_NO_DESKTOP_IDS_ECHOED,
    CLAIM_NO_GEOMETRY_READ,
    CLAIM_NO_LABELS_ECHOED,
    CLAIM_NO_PROCESS_LAUNCHED,
    CLAIM_NO_VISUAL_CHANGE,
    CLAIM_NO_WINDOW_IDS_ECHOED,
)

__all__ = [
    "CLAIM_NO_DESKTOP_IDS_ECHOED",
    "CLAIM_NO_GEOMETRY_READ",
    "CLAIM_NO_LABELS_ECHOED",
    "CLAIM_NO_PROCESS_LAUNCHED",
    "CLAIM_NO_VISUAL_CHANGE",
    "CLAIM_NO_WINDOW_IDS_ECHOED",
    "FIXED_CLAIMS",
    "REASON_INVALID_INPUT",
    "REASON_OK",
    "REASON_SOURCE_DISAGREEMENT",
    "REASON_UNPINNED_GROUP",
    "STATUS_DENIED",
    "STATUS_READY",
    "WindowGroupPreview",
    "compose_window_group_preview",
]


@dataclass(frozen=True)
class WindowGroupPreview:
    """One bounded host preview; denials carry no source material.

    ``claims`` is the fixed tuple of negative claims only on a READY preview.
    Every count is a number, never a copied id or label.
    """

    status: str
    reason: str
    group_count: int = 0
    window_count: int = 0
    unmapped_count: int = 0
    duplicate_count: int = 0
    claims: Tuple[str, ...] = ()

    @property
    def ready(self):
        return self.status == STATUS_READY

    def to_dict(self):
        """Plain bounded mapping for a host bridge or evidence log."""
        return {
            "status": self.status,
            "reason": self.reason,
            "group_count": self.group_count,
            "window_count": self.window_count,
            "unmapped_count": self.unmapped_count,
            "duplicate_count": self.duplicate_count,
            "claims": list(self.claims),
        }


def _deny(reason):
    return WindowGroupPreview(STATUS_DENIED, reason)


def _result_ok(result):
    """Verify the tested grouping output shape without echoing any of it."""
    if not isinstance(result, GroupingResult):
        return False
    if (type(result.groups) is not tuple
            or type(result.unmapped) is not tuple
            or type(result.duplicates) is not tuple):
        return False
    for group in result.groups:
        if not isinstance(group, WindowGroup):
            return False
        if (type(group.desktop_id) is not str
                or type(group.dock_label) is not str
                or type(group.window_ids) is not tuple):
            return False
    return all(isinstance(record, WindowRecord) for record in result.unmapped)


def compose_window_group_preview(
    windows, trusted_map, pinned, *, max_windows=None, max_groups=None,
):
    """Compose one no-echo dock window-group preview; enumerate nothing.

    ``windows`` and ``trusted_map`` feed the tested grouping module; every
    resulting dock label must also be present in the host's pinned snapshot.
    No window id, desktop id or label is copied into the returned record.
    """
    if not isinstance(pinned, PinnedItems) or type(pinned.items) is not tuple:
        return _deny(REASON_INVALID_INPUT)
    options = {}
    if max_windows is not None:
        options["max_windows"] = max_windows
    if max_groups is not None:
        options["max_groups"] = max_groups
    try:
        result = group_windows_by_desktop_id(windows, trusted_map, **options)
    except (WindowGroupingError, TypeError, ValueError):
        return _deny(REASON_INVALID_INPUT)

    if not _result_ok(result):
        return _deny(REASON_SOURCE_DISAGREEMENT)
    if any(group.dock_label not in pinned.items for group in result.groups):
        return _deny(REASON_UNPINNED_GROUP)

    return WindowGroupPreview(
        status=STATUS_READY,
        reason=REASON_OK,
        group_count=len(result.groups),
        window_count=sum(len(group.window_ids) for group in result.groups),
        unmapped_count=len(result.unmapped),
        duplicate_count=len(result.duplicates),
        claims=FIXED_CLAIMS,
    )
