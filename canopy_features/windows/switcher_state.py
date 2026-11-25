"""Deterministic, host-owned keyboard window-switch selection state.

Pure in-memory state machine, not a Qt or OS bridge. It never observes real
windows, binds keys, polls, creates threads/timers, opens sockets or performs
I/O. Callers supply a stable ordered list of opaque window ids and feed it
explicit transition events (begin/next/previous/select/confirm/cancel/remove).

Given the same starting state and the same operation sequence, results are
always identical: there is no clock, randomness or hidden state. This is
selection bookkeeping only. It proves nothing about a working desktop until a
trusted host wires it into real window and keyboard events.
"""
from dataclasses import dataclass

MAX_WINDOWS = 64
MAX_ID_LENGTH = 128


class SwitcherError(ValueError):
    """Invalid window id, bound, or transition for the current state."""


@dataclass(frozen=True)
class SwitchState:
    """Immutable view of the switcher at one instant."""

    active: bool
    current: object
    selected: object
    order: tuple


def _valid_id(value):
    """Accept only bounded, opaque ids: positive ints or short nonempty strs."""
    if type(value) is bool:
        return False
    if type(value) is int:
        return 0 < value <= 1_000_000_000_000
    if type(value) is str:
        return 0 < len(value) <= MAX_ID_LENGTH
    return False


class SwitcherState:
    """Cyclic, wraparound window selection with deterministic window-death rules.

    ``windows`` defines a fixed cyclic order (first to last). ``current`` is
    the focused window id, or None. Selection is stored by window id, so the
    effect of a window dying never depends on hidden indices or iteration
    order of an external container.
    """

    def __init__(self, windows, *, current=None):
        if type(windows) not in (list, tuple):
            raise SwitcherError("windows must be a list or tuple")
        if len(windows) > MAX_WINDOWS:
            raise SwitcherError("too many windows")
        order = []
        seen = set()
        for window in windows:
            if not _valid_id(window):
                raise SwitcherError("invalid window id")
            if window in seen:
                raise SwitcherError("duplicate window id")
            seen.add(window)
            order.append(window)
        if current is not None:
            if not _valid_id(current) or current not in seen:
                raise SwitcherError("current must be a tracked window id")
        self._order = tuple(order)
        self._current = current
        self._selected = None
        self._active = False

    # Immutable value view; safe to hand to callers.
    def snapshot(self):
        return SwitchState(self._active, self._current, self._selected,
                           self._order)

    @property
    def active(self):
        return self._active

    @property
    def current(self):
        return self._current

    @property
    def selected(self):
        return self._selected

    @property
    def order(self):
        return self._order

    def _require_active(self):
        if not self._active:
            raise SwitcherError("no active selection")

    def begin(self):
        """Start a selection cycle, highlighting the focused window.

        Returns the highlighted id, or None when there are no windows. An
        empty switcher stays inactive; it is a graceful no-op, not an error.
        """
        if not self._order:
            self._active = False
            self._selected = None
            return None
        self._active = True
        self._selected = (self._current if self._current in self._order
                          else self._order[0])
        return self._selected

    def next(self):
        """Move selection one step forward, wrapping last to first."""
        self._require_active()
        return self._step(1)

    def previous(self):
        """Move selection one step backward, wrapping first to last."""
        self._require_active()
        return self._step(-1)

    def _step(self, delta):
        order = self._order
        if not order:  # defensive: active implies a nonempty order
            self._selected = None
            return None
        try:
            index = order.index(self._selected)
        except ValueError:
            index = 0
        self._selected = order[(index + delta) % len(order)]
        return self._selected

    def select(self, window_id):
        """Jump selection directly to a tracked window id."""
        self._require_active()
        if window_id not in self._order:
            raise SwitcherError("unknown window id")
        self._selected = window_id
        return window_id

    def confirm(self):
        """Commit the highlighted window as focused and end the cycle."""
        self._require_active()
        chosen = self._selected
        if chosen is not None:
            self._current = chosen
        self._active = False
        self._selected = None
        return chosen

    def cancel(self):
        """End the cycle without changing focus; return the focused id."""
        self._require_active()
        self._active = False
        self._selected = None
        return self._current

    def focus(self, window_id):
        """Record an external focus change while no cycle is active."""
        if self._active:
            raise SwitcherError("cannot change focus during selection")
        if window_id is not None and window_id not in self._order:
            raise SwitcherError("unknown window id")
        self._current = window_id
        return window_id

    def remove(self, window_id):
        """Handle window death. Return True if it was tracked, else False.

        The dead window leaves the cycle. If it was selected, selection moves
        to the successor that shifts into its slot, wrapping to the first
        when the last window dies. The same rule repairs focus if the dead
        window was current. Losing the final window deactivates cleanly.
        """
        if not _valid_id(window_id):
            raise SwitcherError("invalid window id")
        if window_id not in self._order:
            return False
        index = self._order.index(window_id)
        new_order = self._order[:index] + self._order[index + 1:]

        def survivor():
            if not new_order:
                return None
            return new_order[index % len(new_order)]

        selected_died = self._selected == window_id
        self._order = new_order

        if self._current is not None and self._current not in new_order:
            self._current = survivor()

        if self._active:
            if selected_died:
                self._selected = survivor()
            if not new_order:
                self._active = False
                self._selected = None
                self._current = None
        else:
            self._selected = None
        return True
