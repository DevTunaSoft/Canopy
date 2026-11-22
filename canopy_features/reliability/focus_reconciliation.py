"""Deterministic focus-selection recovery for a bounded set of windows.

Offline, event-driven state model. Focus is tracked by stable window identity,
never by a positional index, so a window that disappears cannot leave a stale
selection pointing at a different window. The host calls add/remove/focus/next/
previous as real events arrive; there is no polling, thread, socket, timer or
privileged operation here.

Scope: this is a pure-Python state model, not a Qt bridge, compositor or live
desktop session. The compiled Qt application must wire it in before any real
keyboard focus or window-death behavior is claimed.
"""

from dataclasses import dataclass
from typing import Optional, Union

DEFAULT_MAX_WINDOWS = 256
MAX_ID_BYTES = 256

WindowId = Union[str, int]


class FocusError(ValueError):
    """Invalid window id, unknown window, or capacity exceeded."""


@dataclass(frozen=True)
class FocusResult:
    """Outcome of one focus operation; immutable so callers cannot corrupt it."""

    previous: Optional[WindowId]
    current: Optional[WindowId]
    reason: str
    changed: bool


class FocusSelection:
    """Ordered, bounded focus model with deterministic window-death recovery."""

    def __init__(self, windows=(), *, max_windows: int = DEFAULT_MAX_WINDOWS):
        if type(max_windows) is not int or not 1 <= max_windows <= DEFAULT_MAX_WINDOWS:
            raise FocusError("max_windows must be an int between 1 and 256")
        self._max = max_windows
        self._order: list = []
        self._live = set()
        self._focus: Optional[WindowId] = None
        for window in windows:
            self.add(window)

    @staticmethod
    def _validate(window: WindowId) -> None:
        if type(window) is str:
            try:
                encoded = window.encode("utf-8", "strict")
            except UnicodeError as exc:
                raise FocusError("invalid window id encoding") from exc
            if len(encoded) > MAX_ID_BYTES:
                raise FocusError("window id exceeds bound")
            return
        if type(window) is int:
            return
        raise FocusError("window id must be a str or int")

    @property
    def focus(self) -> Optional[WindowId]:
        return self._focus

    @property
    def windows(self) -> tuple:
        return tuple(self._order)

    def __len__(self) -> int:
        return len(self._order)

    def add(self, window: WindowId) -> FocusResult:
        """Add a live window; focus the first one added."""
        self._validate(window)
        if window in self._live:
            return FocusResult(self._focus, self._focus, "already-present", False)
        if len(self._order) >= self._max:
            raise FocusError("window capacity reached")
        previous = self._focus
        self._live.add(window)
        self._order.append(window)
        if previous is None:
            self._focus = window
            return FocusResult(previous, window, "focused-first", True)
        return FocusResult(previous, self._focus, "added", False)

    def remove(self, window: WindowId) -> FocusResult:
        """Window death. If it held focus, move to a deterministic survivor."""
        self._validate(window)
        if window not in self._live:
            return FocusResult(self._focus, self._focus, "already-absent", False)
        previous = self._focus
        index = self._order.index(window)
        self._order.pop(index)
        self._live.discard(window)
        if previous != window:
            return FocusResult(previous, self._focus, "removed-unfocused", False)
        if not self._order:
            self._focus = None
            return FocusResult(previous, None, "focus-lost-empty", True)
        # Match the QML GridView model: the item that shifts into the vacated
        # slot inherits focus; when the last item dies, wrap to the new last.
        if index < len(self._order):
            self._focus = self._order[index]
            reason = "recovered-next"
        else:
            self._focus = self._order[-1]
            reason = "recovered-previous"
        return FocusResult(previous, self._focus, reason, True)

    def focus_window(self, window: WindowId) -> FocusResult:
        """Explicitly select a live window."""
        self._validate(window)
        if window not in self._live:
            raise FocusError("window not present")
        previous = self._focus
        if previous == window:
            return FocusResult(previous, window, "unchanged", False)
        self._focus = window
        return FocusResult(previous, window, "selected", True)

    def next(self) -> FocusResult:
        """Repeatable 'next window' shortcut; wraps at the end."""
        return self._step(1)

    def previous(self) -> FocusResult:
        """Repeatable 'previous window' shortcut; wraps at the start."""
        return self._step(-1)

    def _step(self, delta: int) -> FocusResult:
        previous = self._focus
        if not self._order:
            self._focus = None
            return FocusResult(previous, None, "empty", False)
        if self._focus is None:
            self._focus = self._order[0] if delta > 0 else self._order[-1]
        else:
            index = self._order.index(self._focus)
            self._focus = self._order[(index + delta) % len(self._order)]
        return FocusResult(previous, self._focus, "cycled", self._focus != previous)
