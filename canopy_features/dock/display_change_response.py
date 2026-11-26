"""Event-driven Classic display-change response model (pure Python).

No Qt import, no polling, no thread, no I/O and no hardware observation. A
trusted host calls :meth:`DisplayChangeResponse.handle` when a real display
signal arrives; the response returns a bounded relayout plan. This module is
decision logic only and never claims a compiled-Qt or Mint runtime result.
"""
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
import math
import re

from canopy_features.dock.display_geometry_contract import validate_dock_bounds
from canopy_features.reliability.screen_topology_change import (
    EVENT_CONNECT, EVENT_DISCONNECT, EVENT_PRIMARY_CHANGED,
    EVENT_RESOLUTION_CHANGED,
)

ROOT_WIDTH = 1200
ROOT_HEIGHT = 750
MIN_WIDTH = 720
MIN_HEIGHT = 480
MAX_WIDTH = 7680
MAX_HEIGHT = 4320

KIND_RELAYOUT = "relayout"
KIND_HOLD = "hold"
KIND_SUSPEND = "suspend"
KIND_NO_OP = "no_op"

ALLOWED_KINDS = frozenset({
    EVENT_RESOLUTION_CHANGED, EVENT_CONNECT, EVENT_DISCONNECT,
    EVENT_PRIMARY_CHANGED,
})
CONNECTOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
MAX_SCALE = 4.0
MAX_SUBSCRIBERS = 16
MAX_HISTORY = 64

__all__ = [
    "ROOT_WIDTH", "ROOT_HEIGHT", "MIN_WIDTH", "MIN_HEIGHT",
    "MAX_SUBSCRIBERS", "MAX_HISTORY",
    "EVENT_RESOLUTION_CHANGED", "KIND_RELAYOUT", "KIND_HOLD",
    "KIND_SUSPEND", "KIND_NO_OP", "DisplayChangeError",
    "DisplayEvent", "RelayoutPlan", "DisplayChangeResponse",
]


class DisplayChangeError(ValueError):
    """Invalid API argument; never raised for an observed display change."""


@dataclass(frozen=True)
class DisplayEvent:
    """One host-supplied display change, in logical pixels.

    Fields are intentionally typed loosely: a hostile event arrives as data
    and must be refused by :meth:`DisplayChangeResponse.handle`, not by the
    constructor. Trusted producers may construct this value directly.
    """

    kind: object
    connector: object = None
    width: object = None
    height: object = None
    scale: object = 1.0
    previous: object = None


@dataclass(frozen=True)
class RelayoutPlan:
    """Bounded decision produced for one event."""

    sequence: int
    kind: str
    size: tuple
    reason: str


def _field(source, name):
    """Read one event field from a mapping or attribute carrier."""
    if isinstance(source, Mapping):
        return source.get(name)
    return getattr(source, name)


def _coerce_event(value):
    """Build a validated DisplayEvent from a host payload, or fail closed."""
    if not isinstance(value, (DisplayEvent, Mapping)):
        # Attribute carriers are accepted only when they expose all fields.
        if not all(hasattr(value, name) for name in
                   ("kind", "connector", "width", "height", "scale", "previous")):
            raise DisplayChangeError("unsupported display event")
    event = value if isinstance(value, DisplayEvent) else DisplayEvent(
        kind=_field(value, "kind"),
        connector=_field(value, "connector"),
        width=_field(value, "width"),
        height=_field(value, "height"),
        scale=_field(value, "scale"),
        previous=_field(value, "previous"),
    )
    if type(event.kind) is not str or event.kind not in ALLOWED_KINDS:
        raise DisplayChangeError("invalid display event kind")
    if event.connector is not None and (
            type(event.connector) is not str
            or not CONNECTOR.fullmatch(event.connector)):
        raise DisplayChangeError("invalid display connector")
    for name, size, limit in (("width", event.width, MAX_WIDTH),
                              ("height", event.height, MAX_HEIGHT)):
        if event.kind == EVENT_DISCONNECT and size is None:
            continue
        if type(size) is not int or not 1 <= size <= limit:
            raise DisplayChangeError("invalid display " + name)
    scale = event.scale
    if (isinstance(scale, bool) or not isinstance(scale, (int, float))
            or not math.isfinite(scale)
            or not 0 < scale <= MAX_SCALE):
        raise DisplayChangeError("invalid display scale")
    if event.previous is not None and (
            type(event.previous) is not tuple or len(event.previous) != 2
            or any(type(v) is not int or v <= 0 for v in event.previous)):
        raise DisplayChangeError("invalid previous resolution")
    return event


class DisplayChangeResponse:
    """Turns one display event at a time into a safe Classic relayout plan."""

    def __init__(self):
        self._sequence = 0
        self._last_safe_size = (ROOT_WIDTH, ROOT_HEIGHT)
        self._last_signature = None
        self._subscribers = {}
        self._next_token = 1
        self._failed_notifications = 0
        self._history = deque(maxlen=MAX_HISTORY)

    @property
    def last_safe_size(self):
        return self._last_safe_size

    @property
    def history(self):
        return tuple(self._history)

    @property
    def failed_notifications(self):
        return self._failed_notifications

    def subscribe(self, callback):
        """Register a push callback; returns a token for unsubscribe."""
        if not callable(callback):
            raise DisplayChangeError("callback must be callable")
        if len(self._subscribers) >= MAX_SUBSCRIBERS:
            raise DisplayChangeError("subscriber limit reached")
        token = self._next_token
        self._next_token += 1
        self._subscribers[token] = callback
        return token

    def unsubscribe(self, token):
        """Remove one callback; unknown tokens are a no-op."""
        if type(token) is not int:
            raise DisplayChangeError("token must be an int")
        return self._subscribers.pop(token, None) is not None

    def _notify(self, plan):
        for callback in tuple(self._subscribers.values()):
            try:
                callback(plan)
            except Exception:
                # A bad subscriber must never crash a display change.
                self._failed_notifications += 1

    def handle(self, event):
        self._sequence += 1
        try:
            event = _coerce_event(event)
        except Exception:
            # Observed display data is never allowed to crash the shell.
            plan = RelayoutPlan(self._sequence, KIND_HOLD,
                                self._last_safe_size, "invalid_event")
            self._history.append(plan)
            self._notify(plan)
            return plan
        try:
            plan = self._plan(event)
            signature = (event.kind, event.connector, event.width,
                         event.height, event.scale)
            if signature == self._last_signature:
                plan = RelayoutPlan(self._sequence, KIND_NO_OP,
                                    plan.size, "unchanged")
            else:
                self._last_signature = signature
        except Exception:
            plan = RelayoutPlan(self._sequence, KIND_HOLD,
                                self._last_safe_size, "invalid_event")
        self._history.append(plan)
        if plan.kind == KIND_RELAYOUT:
            self._last_safe_size = plan.size
        if plan.kind != KIND_NO_OP:
            self._notify(plan)
        return plan

    def _plan(self, event):
        if event.kind == EVENT_DISCONNECT:
            return RelayoutPlan(self._sequence, KIND_SUSPEND,
                                self._last_safe_size, "no_display")
        if event.width < MIN_WIDTH or event.height < MIN_HEIGHT:
            return RelayoutPlan(self._sequence, KIND_HOLD,
                                self._last_safe_size, "below_minimum")
        size = (min(ROOT_WIDTH, event.width), min(ROOT_HEIGHT, event.height))
        if not validate_dock_bounds(*size).ok:
            return RelayoutPlan(self._sequence, KIND_HOLD,
                                self._last_safe_size, "unsafe_geometry")
        reason = ("resolution_changed" if event.kind == EVENT_RESOLUTION_CHANGED
                  else event.kind)
        return RelayoutPlan(self._sequence, KIND_RELAYOUT, size, reason)

    def handle_recovery_result(self, result):
        """Adapt one frozen ``RecoveryResult`` from the topology model.

        This is the host-facing seam: the trusted producer calls this method
        only when it receives a real screen signal. Nothing here polls or
        observes hardware. Malformed results fall back to a safe hold plan.
        """
        try:
            primary = result.safe_topology.primary
            if primary is None:
                return self.handle(DisplayEvent(EVENT_DISCONNECT))
            kinds = tuple(change.kind for change in result.changes)
            if EVENT_RESOLUTION_CHANGED in kinds:
                kind = EVENT_RESOLUTION_CHANGED
            elif EVENT_PRIMARY_CHANGED in kinds:
                kind = EVENT_PRIMARY_CHANGED
            else:
                kind = EVENT_CONNECT
            return self.handle(DisplayEvent(
                kind, connector=primary.connector,
                width=primary.width, height=primary.height,
                previous=None))
        except Exception:
            return self.handle(None)
