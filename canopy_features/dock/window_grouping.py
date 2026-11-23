"""Offline, bounded grouping of trusted desktop windows for dock tiles.

The host owns window enumeration and supplies VERIFIED window descriptors plus
a trusted ``desktop_id -> dock_label`` allowlist (built from the host's existing
GIO launcher catalog; see ``prototype/classic/SystemAppLauncher.cpp``). This
module never enumerates windows, reads X/Wayland properties, spawns processes,
polls or opens sockets. It is deterministic and uses bounded memory only.

A desktop ID absent from the allowlist is never guessed: that window is
reported in ``unmapped`` so the host may render a neutral fallback. Repeated
sightings of the same window ID are folded into one group and reported in
``duplicates`` (first occurrence wins). Outputs are immutable tuples in stable,
first-seen order.
"""
from collections.abc import Mapping
from dataclasses import dataclass

MAX_WINDOWS = 256
MAX_GROUPS = 64
MAX_ID_BYTES = 256


class WindowGroupingError(ValueError):
    """Invalid descriptor, untrusted input or exceeded resource bound."""


@dataclass(frozen=True)
class WindowRecord:
    """One host-verified window.

    ``window_id`` is an opaque, hashable token unique among live windows (for
    example an XID integer or a Wayland handle string). ``desktop_id`` is the
    resolved desktop application id, e.g. ``org.gnome.Nautilus.desktop``.
    """
    window_id: object
    desktop_id: str


@dataclass(frozen=True)
class WindowGroup:
    """All distinct windows that belong to one trusted dock tile."""
    desktop_id: str
    dock_label: str
    window_ids: tuple


@dataclass(frozen=True)
class GroupingResult:
    """Groups plus the windows the host must handle explicitly."""
    groups: tuple
    unmapped: tuple
    duplicates: tuple


def _valid_text(value):
    if type(value) is not str or not value:
        return False
    try:
        return len(value.encode("utf-8", "strict")) <= MAX_ID_BYTES
    except UnicodeError:
        return False


def _check_bound(value, name, ceiling):
    if type(value) is not int or not 1 <= value <= ceiling:
        raise WindowGroupingError("invalid " + name + " bound")


def group_windows_by_desktop_id(windows, trusted_map, *,
                                max_windows=MAX_WINDOWS,
                                max_groups=MAX_GROUPS):
    """Group verified windows by desktop ID using a trusted allowlist.

    ``trusted_map`` maps each allowed desktop ID to its dock label. The host
    derives it from its own launcher catalog so no desktop-ID list is duplicated
    here. Returns ``GroupingResult``; unknown desktop IDs become ``unmapped``
    and repeated window IDs become ``duplicates``.
    """
    if not isinstance(trusted_map, Mapping):
        raise WindowGroupingError("trusted_map must be a mapping")
    _check_bound(max_windows, "max_windows", MAX_WINDOWS)
    _check_bound(max_groups, "max_groups", MAX_GROUPS)

    allowlist = {}
    for desktop_id, dock_label in trusted_map.items():
        if not _valid_text(desktop_id) or not _valid_text(dock_label):
            raise WindowGroupingError("invalid trusted map entry")
        allowlist[desktop_id] = dock_label

    if (isinstance(windows, (str, bytes, Mapping))
            or not hasattr(windows, "__iter__")):
        raise WindowGroupingError("windows must be an iterable of WindowRecord")

    seen = set()
    duplicates = []
    unmapped = []
    groups = {}  # desktop_id -> window_ids, insertion order is deterministic
    count = 0

    for record in windows:
        count += 1
        if count > max_windows:
            raise WindowGroupingError("window count exceeds bound")
        if not isinstance(record, WindowRecord):
            raise WindowGroupingError("each window must be a WindowRecord")
        try:
            hash(record.window_id)
        except TypeError as exc:
            raise WindowGroupingError("window_id must be hashable") from exc
        if not _valid_text(record.desktop_id):
            raise WindowGroupingError("invalid window desktop_id")

        if record.window_id in seen:
            duplicates.append(record.window_id)
            continue
        seen.add(record.window_id)

        label = allowlist.get(record.desktop_id)
        if label is None:
            unmapped.append(record)
            continue

        if record.desktop_id not in groups:
            if len(groups) >= max_groups:
                raise WindowGroupingError("group count exceeds bound")
            groups[record.desktop_id] = []
        groups[record.desktop_id].append(record.window_id)

    result_groups = tuple(
        WindowGroup(desktop_id=desktop_id,
                    dock_label=allowlist[desktop_id],
                    window_ids=tuple(window_ids))
        for desktop_id, window_ids in groups.items()
    )
    return GroupingResult(groups=result_groups,
                          unmapped=tuple(unmapped),
                          duplicates=tuple(duplicates))
