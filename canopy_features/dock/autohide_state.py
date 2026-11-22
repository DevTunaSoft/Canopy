"""Pure state machine for optional, user-controlled dock auto-hide.

This module is deliberately inert. It has no Qt dependency, no timers, no
polling, no threads, no network, no filesystem access and no background
service. A host feeds it discrete events and reads one derived ``visible``
flag. Every transition is a pure function of an immutable state plus an
event, so the same input always yields the same output.

This is not a working desktop feature. A compiled Qt host must still wire
real pointer/focus/modal signals into :func:`transition` and apply the
resulting ``visible`` value to the QML dock. It does not change the frozen
Classic dock geometry, artwork or QML.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class AutoHideMode(Enum):
    """User-controlled opt-in. OFF keeps the dock permanently visible."""

    OFF = "off"
    ON = "on"


class DockEvent(Enum):
    """Discrete host signals; no value carries untrusted payload data."""

    ENABLE_AUTO_HIDE = "enable_auto_hide"
    DISABLE_AUTO_HIDE = "disable_auto_hide"
    POINTER_ENTER_REVEAL_ZONE = "pointer_enter_reveal_zone"
    POINTER_LEAVE_REVEAL_ZONE = "pointer_leave_reveal_zone"
    FOCUS_GAINED = "focus_gained"
    FOCUS_LOST = "focus_lost"
    MODAL_OPENED = "modal_opened"
    MODAL_CLOSED = "modal_closed"


@dataclass(frozen=True)
class DockVisibility:
    """Bounded, immutable snapshot. No history list and no growing state."""

    mode: AutoHideMode = AutoHideMode.OFF
    revealed: bool = False
    focused: bool = True
    modal_active: bool = False

    def __post_init__(self):
        if not isinstance(self.mode, AutoHideMode):
            raise TypeError("mode must be an AutoHideMode")
        for name in ("revealed", "focused", "modal_active"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(name + " must be a bool")
        if self.revealed and (self.mode is AutoHideMode.OFF
                              or not self.focused or self.modal_active):
            raise ValueError("revealed requires auto-hide on, focus and no modal")

    @property
    def visible(self) -> bool:
        """Derived, never stored: opt-out wins, else temporary reveal wins."""
        return self.mode is AutoHideMode.OFF or self.revealed


def initial_state() -> DockVisibility:
    """Auto-hide is opt-in, so the default dock stays visible."""
    return DockVisibility()


def transition(state: DockVisibility, event: DockEvent) -> DockVisibility:
    """Return the next immutable state. Never mutate ``state`` or global data.

    Rules of interest to a host:

    * Focus loss always retracts a revealed dock, so stale reveals cannot
      linger after the user switches away.
    * A modal window retracts the dock and blocks pointer-triggered reveals
      until the modal closes.
    * With auto-hide off the dock is permanently visible, including while a
      modal overlay is present.
    """
    if not isinstance(state, DockVisibility):
        raise TypeError("state must be a DockVisibility")
    if not isinstance(event, DockEvent):
        raise TypeError("event must be a DockEvent")

    if event is DockEvent.ENABLE_AUTO_HIDE:
        if state.mode is AutoHideMode.ON:
            return state
        return replace(state, mode=AutoHideMode.ON, revealed=False)
    if event is DockEvent.DISABLE_AUTO_HIDE:
        if state.mode is AutoHideMode.OFF:
            return state
        return replace(state, mode=AutoHideMode.OFF, revealed=False)
    if event is DockEvent.POINTER_ENTER_REVEAL_ZONE:
        may_reveal = (state.mode is AutoHideMode.ON and state.focused
                      and not state.modal_active)
        return replace(state, revealed=may_reveal)
    if event is DockEvent.POINTER_LEAVE_REVEAL_ZONE:
        return replace(state, revealed=False)
    if event is DockEvent.FOCUS_LOST:
        return replace(state, focused=False, revealed=False)
    if event is DockEvent.FOCUS_GAINED:
        return replace(state, focused=True)
    if event is DockEvent.MODAL_OPENED:
        return replace(state, modal_active=True, revealed=False)
    if event is DockEvent.MODAL_CLOSED:
        return replace(state, modal_active=False, revealed=False)
    raise ValueError("unhandled DockEvent")  # no member falls through
