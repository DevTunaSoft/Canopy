"""Offline model of accessible dock keyboard focus order.

Pure-Python, event-driven state helper for the Classic dock. It computes which
dock item owns keyboard focus after a navigation action and returns a small,
immutable description of that transition. It does NOT read or change dock
geometry, QML, artwork, Qt widgets, input devices or a running desktop.

Callers own the key events and apply the returned transition (for example, to
move a QML focus highlight). This module starts no timers or threads, polls
nothing, performs no I/O and keeps only the bounded item list given by trusted
application code.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

MAX_ITEMS = 64
DEFAULT_TRANSITION_MS = 120


class DockFocusError(ValueError):
    """Invalid dock item list or navigation request."""


@dataclass(frozen=True)
class FocusTransition:
    """Result of one keyboard focus action.

    ``duration_ms`` is the suggested focus-highlight animation length. It is
    always 0 for reduced motion and for actions that do not move focus; this
    model never animates anything itself.
    """

    from_id: Optional[str]
    to_id: Optional[str]
    moved: bool
    wrapped: bool
    duration_ms: int

    @property
    def active_id(self):
        """Id of the focused dock item after the action (None if none)."""
        return self.to_id


class DockFocusOrder:
    """Ordered, bounded keyboard focus model for dock items.

    Items are opaque, unique, non-empty string ids in the same visual order as
    the existing dock Repeater model. Focus is tracked by id, never by pixel
    coordinate or geometry constant, so dock layout stays frozen and owned
    elsewhere.
    """

    def __init__(self, items, *, wrap=True, reduced_motion=False):
        if type(wrap) is not bool or type(reduced_motion) is not bool:
            raise DockFocusError("wrap and reduced_motion must be bool")
        self._wrap = wrap
        self._reduced_motion = reduced_motion
        self._items = self._normalize(items)
        self._focused_id = None

    @staticmethod
    def _normalize(items):
        if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
            raise DockFocusError("items must be an ordered sequence of string ids")
        if len(items) > MAX_ITEMS:
            raise DockFocusError("dock item limit exceeded")
        normalized = []
        seen = set()
        for item in items:
            if type(item) is not str or not item:
                raise DockFocusError("dock item ids must be non-empty strings")
            if item in seen:
                raise DockFocusError("duplicate dock item id")
            seen.add(item)
            normalized.append(item)
        return tuple(normalized)

    @property
    def items(self):
        """Immutable snapshot of the focus order (left to right)."""
        return self._items

    @property
    def focused_id(self):
        return self._focused_id

    @property
    def wrap(self):
        return self._wrap

    @property
    def reduced_motion(self):
        return self._reduced_motion

    def _transition(self, old, *, wrapped=False):
        new = self._focused_id
        moved = old != new
        duration = (0 if self._reduced_motion or not moved
                    else DEFAULT_TRANSITION_MS)
        return FocusTransition(old, new, moved, wrapped, duration)

    def focus(self, item_id):
        """Focus a known item by id; unknown ids are rejected, not guessed."""
        if type(item_id) is not str or item_id not in self._items:
            raise DockFocusError("unknown dock item id")
        old = self._focused_id
        self._focused_id = item_id
        return self._transition(old)

    def focus_first(self):
        """Home-key behaviour."""
        return self._focus_index(0)

    def focus_last(self):
        """End-key behaviour."""
        return self._focus_index(len(self._items) - 1)

    def _focus_index(self, index):
        old = self._focused_id
        if self._items:
            self._focused_id = self._items[index]
        return self._transition(old)

    def clear_focus(self):
        old = self._focused_id
        self._focused_id = None
        return self._transition(old)

    def next(self):
        """Move focus one item right (Tab/Right-arrow behaviour)."""
        return self._step(1)

    def previous(self):
        """Move focus one item left (Shift-Tab/Left-arrow behaviour)."""
        return self._step(-1)

    def _step(self, direction):
        old = self._focused_id
        count = len(self._items)
        if not count:
            return self._transition(old)
        if old is None:
            self._focused_id = self._items[0] if direction > 0 else self._items[-1]
            return self._transition(old)

        target = self._items.index(old) + direction
        wrapped = False
        if target < 0:
            if self._wrap:
                target = count - 1
                wrapped = True
            else:
                target = 0
        elif target >= count:
            if self._wrap:
                target = 0
                wrapped = True
            else:
                target = count - 1
        self._focused_id = self._items[target]
        return self._transition(old, wrapped=wrapped)

    def set_items(self, items):
        """Replace the order after a bounded dock-item change.

        Focus is kept when its id still exists; otherwise it is cleared rather
        than pointing at an unrelated item. No geometry is consulted.
        """
        old = self._focused_id
        self._items = self._normalize(items)
        if old not in self._items:
            self._focused_id = None
        return self._transition(old)
