"""Normalize one read-only X11 window inventory snapshot.

This module is pure and offline: it never opens an X11 connection, starts an
external process, polls, keeps history, or starts background work. The caller
supplies an adapter for raw ``wmctrl -l`` style lines, or supplies none when no
display is available. Nothing here proves a live desktop, Qt integration, or
Linux Mint acceptance.
"""
from dataclasses import dataclass
import re
from typing import Optional, Protocol, Sequence, Tuple

MAX_WINDOWS = 256
MAX_LINE_BYTES = 512
MAX_TITLE_CHARS = 120
MAX_DESKTOP = 65535

_ID = re.compile(r"0[xX][0-9a-fA-F]{1,16}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")

_OK = "OK"
_NO_ADAPTER = "NO_ADAPTER"
_INVALID_ADAPTER = "INVALID_ADAPTER"
_ADAPTER_ERROR = "ADAPTER_ERROR"
_DISPLAY_UNAVAILABLE = "DISPLAY_UNAVAILABLE"


@dataclass(frozen=True)
class RawInventory:
    """One caller-supplied read of raw inventory lines."""

    lines: Sequence[str] = ()
    display_available: bool = True


@dataclass(frozen=True)
class Window:
    window_id: str
    desktop: int
    title: str


@dataclass(frozen=True)
class InventorySnapshot:
    windows: Tuple[Window, ...]
    stale_ids: Tuple[str, ...]
    status: str
    rejected_lines: int
    truncated: bool

    @property
    def available(self) -> bool:
        return self.status == _OK

    @property
    def ids(self) -> Tuple[str, ...]:
        """Canonical live IDs, ready to pass as the next ``known_ids``."""
        return tuple(window.window_id for window in self.windows)


class InventoryAdapter(Protocol):
    """Read-only source implemented by trusted host code."""

    def read_inventory(self) -> RawInventory:
        ...


def _canonical_id(value):
    if type(value) is int:
        if 0 < value <= 0xFFFFFFFFFFFFFFFF:
            return f"0x{value:08x}"
        return None
    if type(value) is str:
        text = value.strip()
        if _ID.fullmatch(text):
            return f"0x{int(text, 16):08x}"
    return None


def _known_ids(known_ids, max_windows):
    if known_ids is None:
        known_ids = ()
    if type(known_ids) not in (list, tuple, set, frozenset):
        raise TypeError("known_ids must be a list, tuple, set or frozenset")
    result = set()
    for index, value in enumerate(known_ids):
        if index >= max_windows:
            break
        canonical = _canonical_id(value)
        if canonical is not None:
            result.add(canonical)
    return result


def _check_bounds(max_windows, max_line_bytes):
    if type(max_windows) is not int or not 1 <= max_windows <= MAX_WINDOWS:
        raise ValueError("invalid window bound")
    if type(max_line_bytes) is not int or not 1 <= max_line_bytes <= MAX_LINE_BYTES:
        raise ValueError("invalid line byte bound")


def _parse_line(line, max_line_bytes):
    if type(line) is not str:
        return None
    try:
        encoded = line.encode("utf-8", "strict")
    except UnicodeError:
        return None
    if len(encoded) > max_line_bytes:
        return None
    fields = line.split(maxsplit=3)
    if len(fields) != 4:
        return None
    window_id = _canonical_id(fields[0])
    if window_id is None:
        return None
    desktop_text = fields[1]
    if not (desktop_text == "-1"
            or desktop_text.isascii() and desktop_text.isdigit()):
        return None
    try:
        desktop = int(desktop_text, 10)
    except ValueError:
        return None
    if not -1 <= desktop <= MAX_DESKTOP:
        return None
    title = _SPACES.sub(" ", _CONTROL.sub(" ", fields[3])).strip()
    return Window(window_id, desktop, title[:MAX_TITLE_CHARS])


def _sorted_ids(values):
    return tuple(sorted(values, key=lambda value: int(value, 16)))


def _unavailable(known, status):
    # No snapshot means every previously live window is now stale, so a
    # consumer can clear running indicators without keeping its own history.
    return InventorySnapshot((), _sorted_ids(known), status, 0, False)


def _normalize(lines, known, max_windows, max_line_bytes):
    if type(lines) not in (list, tuple):
        raise TypeError("lines must be a list or tuple")
    by_id = {}
    rejected = 0
    truncated = False
    scan_limit = max_windows * 4
    for index, line in enumerate(lines):
        if index >= scan_limit:
            truncated = True
            break
        window = _parse_line(line, max_line_bytes)
        if window is None or window.window_id in by_id:
            rejected += 1
            continue
        if len(by_id) >= max_windows:
            truncated = True
            continue
        by_id[window.window_id] = window
    windows = tuple(sorted(by_id.values(),
                           key=lambda window: int(window.window_id, 16)))
    stale = _sorted_ids(known - set(by_id))
    return InventorySnapshot(windows, stale, _OK, rejected, truncated)


def normalize_inventory(lines, *, known_ids=(), max_windows=MAX_WINDOWS,
                        max_line_bytes=MAX_LINE_BYTES):
    """Normalize raw ``wmctrl -l`` lines: ID, desktop, host, title."""
    _check_bounds(max_windows, max_line_bytes)
    known = _known_ids(known_ids, max_windows)
    return _normalize(lines, known, max_windows, max_line_bytes)


def collect(adapter: Optional[InventoryAdapter], *, known_ids=(),
            max_windows=MAX_WINDOWS, max_line_bytes=MAX_LINE_BYTES):
    """Read at most one snapshot from an optional read-only adapter."""
    _check_bounds(max_windows, max_line_bytes)
    known = _known_ids(known_ids, max_windows)
    if adapter is None:
        return _unavailable(known, _NO_ADAPTER)
    reader = getattr(adapter, "read_inventory", None)
    if not callable(reader):
        return _unavailable(known, _INVALID_ADAPTER)
    try:
        raw = reader()
    except Exception:
        # Never copy adapter exception text: it may carry credentials.
        return _unavailable(known, _ADAPTER_ERROR)
    if not isinstance(raw, RawInventory) or type(raw.lines) not in (list, tuple):
        return _unavailable(known, _INVALID_ADAPTER)
    if not raw.display_available:
        return _unavailable(known, _DISPLAY_UNAVAILABLE)
    return _normalize(raw.lines, known, max_windows, max_line_bytes)
