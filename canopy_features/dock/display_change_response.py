"""Event-driven Classic display-change response model (pure Python).

No Qt import, no polling, no thread, no I/O and no hardware observation. A
trusted host calls :meth:`DisplayChangeResponse.handle` when a real display
signal arrives; the response returns a bounded relayout plan. This module is
decision logic only and never claims a compiled-Qt or Mint runtime result.
"""
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
import re

from canopy_features.dock.display_geometry_contract import validate_dock_bounds
from canopy_features.dock.display_scaling_contract import (
    EVENT_DPI_CHANGED, MAX_SCALE, REASON_LOGICAL_DPI_CHANGED,
    REASON_LOGICAL_SIZE_UNCHANGED, DisplayScalingError, validate_scale,
    logical_size_from_physical,
)
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

EVENT_MONITOR_ATTACHED = "monitor_attached"
EVENT_MONITOR_DETACHED = "monitor_detached"
REASON_MONITOR_ATTACHED = "connect"
REASON_MONITOR_DETACHED = "disconnect"

SOURCE_KSCREEN_CONFIG_CHANGED = "kscreen.configChanged"
SOURCE_KWIN_SCREENS_CHANGED = "kwin.screensChanged"
SOURCE_QT_LOGICAL_DPI_CHANGED = "qt.logicalDpiChanged"
NATIVE_SOURCES = frozenset({
    SOURCE_KSCREEN_CONFIG_CHANGED, SOURCE_KWIN_SCREENS_CHANGED,
    SOURCE_QT_LOGICAL_DPI_CHANGED,
})
MAX_NATIVE_SCREENS = 16
MAX_NATIVE_FIELD = 80

ALLOWED_KINDS = frozenset({
    EVENT_RESOLUTION_CHANGED, EVENT_CONNECT, EVENT_DISCONNECT,
    EVENT_PRIMARY_CHANGED, EVENT_DPI_CHANGED,
    EVENT_MONITOR_ATTACHED, EVENT_MONITOR_DETACHED,
})
CONNECTOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
MAX_SUBSCRIBERS = 16
MAX_HISTORY = 64

__all__ = [
    "ROOT_WIDTH", "ROOT_HEIGHT", "MIN_WIDTH", "MIN_HEIGHT",
    "MAX_SCALE", "MAX_SUBSCRIBERS", "MAX_HISTORY", "MAX_NATIVE_SCREENS",
    "EVENT_RESOLUTION_CHANGED", "EVENT_DPI_CHANGED",
    "EVENT_MONITOR_ATTACHED", "EVENT_MONITOR_DETACHED",
    "SOURCE_KSCREEN_CONFIG_CHANGED", "SOURCE_KWIN_SCREENS_CHANGED",
    "SOURCE_QT_LOGICAL_DPI_CHANGED", "NATIVE_SOURCES",
    "KIND_RELAYOUT", "KIND_HOLD",
    "KIND_SUSPEND", "KIND_NO_OP", "DisplayChangeError",
    "DisplayScalingError", "DisplayEvent", "RelayoutPlan",
    "DisplayChangeResponse",
]


class DisplayChangeError(DisplayScalingError):
    """Invalid API argument; never raised for an observed display change."""


@dataclass(frozen=True)
class DisplayEvent:
    """One host-supplied display change.

    For resolution/connect/primary events ``width``/``height`` are logical
    pixels. For ``EVENT_DPI_CHANGED`` they are physical monitor pixels and
    ``scale`` is the device scale used to derive the logical layout.
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
        if event.kind in (EVENT_DISCONNECT, EVENT_MONITOR_DETACHED) \
                and size is None:
            continue
        if type(size) is not int or not 1 <= size <= limit:
            raise DisplayChangeError("invalid display " + name)
    validate_scale(event.scale)
    if event.previous is not None and (
            type(event.previous) is not tuple or len(event.previous) != 2
            or any(type(v) is not int or v <= 0 for v in event.previous)):
        raise DisplayChangeError("invalid previous resolution")
    return event


def _native_field_set(value, allowed):
    """Read one bounded native payload without accepting unknown fields."""
    if not isinstance(value, Mapping):
        raise DisplayChangeError("native payload must be a mapping")
    for name in value:
        if type(name) is not str or name not in allowed:
            raise DisplayChangeError("unexpected native payload field")
    return value


def _native_connector(value):
    if type(value) is not str or not CONNECTOR.fullmatch(value):
        raise DisplayChangeError("invalid native connector")
    return value


def _native_dimension(value, limit):
    if type(value) is not int or not 1 <= value <= limit:
        raise DisplayChangeError("invalid native dimension")
    return value


def _native_payload(payload):
    """Normalize one trusted KWin/KScreen push payload, or fail closed.

    ``payload`` is data from the host, never an observation performed here.
    The returned footprint is a hashable, bounded topology signature used only
    for duplicate suppression; it is never used to resize anything.
    """
    source = payload.get("source") if isinstance(payload, Mapping) else None
    if type(source) is not str or source not in NATIVE_SOURCES:
        raise DisplayChangeError("unsupported native display source")

    if source == SOURCE_KSCREEN_CONFIG_CHANGED:
        fields = _native_field_set(payload, {"source", "outputs"})
        raw = fields.get("outputs")
        if type(raw) not in (tuple, list) or len(raw) > MAX_NATIVE_SCREENS:
            raise DisplayChangeError("invalid KScreen output list")
        records = []
        for item in raw:
            output = _native_field_set(
                item, {"connector", "width", "height", "scale", "primary"})
            connector = _native_connector(output.get("connector"))
            width = _native_dimension(output.get("width"), MAX_WIDTH)
            height = _native_dimension(output.get("height"), MAX_HEIGHT)
            scale = validate_scale(output.get("scale", 1.0))
            primary = output.get("primary", False)
            if type(primary) is not bool:
                raise DisplayChangeError("invalid primary flag")
            records.append((connector, width, height, scale, primary))
        records.sort()
        connectors = tuple(record[0] for record in records)
        if len(set(connectors)) != len(connectors):
            raise DisplayChangeError("duplicate KScreen connector")
        primaries = tuple(record for record in records if record[4])
        if bool(connectors) != bool(primaries) or len(primaries) > 1:
            raise DisplayChangeError("invalid KScreen primary topology")
        primary = primaries[0] if primaries else None
        size = (primary[1], primary[2]) if primary else None
        scale = primary[3] if primary else 1.0
        footprint = tuple(record[:4] for record in records)
        return source, connectors, size, scale, footprint

    if source == SOURCE_KWIN_SCREENS_CHANGED:
        fields = _native_field_set(
            payload, {"source", "screens", "primary", "width", "height",
                      "scale"})
        raw = fields.get("screens")
        if type(raw) not in (tuple, list) or len(raw) > MAX_NATIVE_SCREENS:
            raise DisplayChangeError("invalid KWin screen list")
        connectors = tuple(sorted(_native_connector(name) for name in raw))
        if len(set(connectors)) != len(connectors):
            raise DisplayChangeError("duplicate KWin connector")
        primary = fields.get("primary")
        scale = validate_scale(fields.get("scale", 1.0))
        if connectors:
            if type(primary) is not str or primary not in connectors:
                raise DisplayChangeError("invalid KWin primary")
            size = (_native_dimension(fields.get("width"), MAX_WIDTH),
                    _native_dimension(fields.get("height"), MAX_HEIGHT))
            footprint = tuple(
                (name, size[0], size[1], scale) if name == primary
                else (name, None, None, scale) for name in connectors)
        else:
            if primary is not None or "width" in fields or "height" in fields:
                raise DisplayChangeError("empty KWin topology carries size")
            size = None
            footprint = ()
        return source, connectors, size, scale, footprint

    fields = _native_field_set(
        payload, {"source", "connector", "width", "height", "scale"})
    connector = _native_connector(fields.get("connector"))
    size = (_native_dimension(fields.get("width"), MAX_WIDTH),
            _native_dimension(fields.get("height"), MAX_HEIGHT))
    scale = validate_scale(fields.get("scale", 1.0))
    return source, (connector,), size, scale, ((connector,) + size + (scale,),)


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
        self._last_native_screens = ()
        self._last_native_scale = 1.0

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
        """Handle one trusted display event supplied by the host."""
        return self._dispatch(event)

    def _dispatch(self, event, extra_signature=None,
                  logical_size_unchanged=False):
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
            if extra_signature is not None:
                # A native push owns one cross-kind signature: the same
                # footprint must not relayout again just because the topology
                # delta classification changed (attach -> steady -> detach).
                signature = extra_signature
            if ((event.kind == EVENT_DPI_CHANGED or logical_size_unchanged)
                    and plan.kind == KIND_RELAYOUT
                    and plan.size == self._last_safe_size):
                # A DPI signal that resolves to the same logical layout must
                # not trigger another bounded relayout cycle.
                plan = RelayoutPlan(self._sequence, KIND_NO_OP,
                                    plan.size, REASON_LOGICAL_SIZE_UNCHANGED)
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

    def handle_native_change(self, payload):
        """Consume ONE trusted KWin/KScreen push payload, or fail closed.

        The trusted host calls this only from a real KScreen ``configChanged``,
        KWin ``screensChanged`` or Qt logical-DPI signal. It never registers a
        second listener, never polls and never opens a connection: the only
        state updated is this instance's bounded last-snapshot footprint.
        """
        try:
            source, connectors, size, scale, footprint = _native_payload(payload)
            if source == SOURCE_QT_LOGICAL_DPI_CHANGED:
                event = DisplayEvent(
                    EVENT_DPI_CHANGED, connector=connectors[0] if connectors
                    else None, width=size[0], height=size[1], scale=scale)
                return self._dispatch(event, (source, footprint))

            if source == SOURCE_KWIN_SCREENS_CHANGED:
                logical = size
            else:
                logical = logical_size_from_physical(size[0], size[1], scale) \
                    if size is not None else None
            if connectors and logical is None:
                raise DisplayChangeError("missing native primary geometry")

            if not connectors:
                event = DisplayEvent(EVENT_MONITOR_DETACHED)
            elif not self._last_native_screens:
                event = DisplayEvent(EVENT_RESOLUTION_CHANGED,
                                     width=logical[0], height=logical[1])
            elif any(name not in self._last_native_screens
                     for name in connectors):
                event = DisplayEvent(EVENT_MONITOR_ATTACHED,
                                     width=logical[0], height=logical[1])
            elif any(name not in connectors
                     for name in self._last_native_screens):
                event = DisplayEvent(EVENT_MONITOR_DETACHED,
                                     width=logical[0], height=logical[1])
            elif (source == SOURCE_KSCREEN_CONFIG_CHANGED
                  and size is not None
                  and scale != self._last_native_scale):
                event = DisplayEvent(
                    EVENT_DPI_CHANGED, width=size[0], height=size[1],
                    scale=scale)
            else:
                event = DisplayEvent(EVENT_RESOLUTION_CHANGED,
                                     width=logical[0], height=logical[1])

            signature = (source, footprint, connectors)
            steady = connectors == self._last_native_screens
            scale_changed = scale != self._last_native_scale
            plan = self._dispatch(
                event, signature,
                logical_size_unchanged=(
                    source == SOURCE_KWIN_SCREENS_CHANGED
                    and steady and scale_changed))
            self._last_native_screens = connectors
            self._last_native_scale = scale
            return plan
        except Exception:
            # A malformed push never crashes the shell and never mutates the
            # remembered topology snapshot.
            return self.handle(None)

    def _bounded_relayout(self, event, reason):
        """Clamp one logical size and refuse any unsafe dock geometry."""
        if event.width < MIN_WIDTH or event.height < MIN_HEIGHT:
            return RelayoutPlan(self._sequence, KIND_HOLD,
                                self._last_safe_size, "below_minimum")
        size = (min(ROOT_WIDTH, event.width), min(ROOT_HEIGHT, event.height))
        if not validate_dock_bounds(*size).ok:
            return RelayoutPlan(self._sequence, KIND_HOLD,
                                self._last_safe_size, "unsafe_geometry")
        return RelayoutPlan(self._sequence, KIND_RELAYOUT, size, reason)

    def _plan(self, event):
        if event.kind == EVENT_DISCONNECT:
            return RelayoutPlan(self._sequence, KIND_SUSPEND,
                                self._last_safe_size, "no_display")
        if event.kind == EVENT_MONITOR_DETACHED:
            if event.width is None or event.height is None:
                return RelayoutPlan(self._sequence, KIND_SUSPEND,
                                    self._last_safe_size, "no_display")
            return self._bounded_relayout(event, REASON_MONITOR_DETACHED)
        if event.kind == EVENT_MONITOR_ATTACHED:
            return self._bounded_relayout(event, REASON_MONITOR_ATTACHED)
        if event.kind == EVENT_DPI_CHANGED:
            logical = logical_size_from_physical(
                event.width, event.height, event.scale)
            if logical[0] < MIN_WIDTH or logical[1] < MIN_HEIGHT:
                return RelayoutPlan(self._sequence, KIND_HOLD,
                                    self._last_safe_size, "below_minimum")
            size = (min(ROOT_WIDTH, logical[0]), min(ROOT_HEIGHT, logical[1]))
            if not validate_dock_bounds(*size, scale=event.scale).ok:
                return RelayoutPlan(self._sequence, KIND_HOLD,
                                    self._last_safe_size, "unsafe_geometry")
            return RelayoutPlan(self._sequence, KIND_RELAYOUT, size,
                                REASON_LOGICAL_DPI_CHANGED)
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

    def handle_logical_dpi_change(self, physical_width, physical_height,
                                  scale, connector=None):
        """Host seam for one logical-DPI change; hostile inputs are held.

        The trusted producer calls this only on a real DPI signal. Nothing
        here polls, samples hardware, resizes a window or changes a binding.
        """
        return self.handle(DisplayEvent(
            EVENT_DPI_CHANGED, connector=connector, width=physical_width,
            height=physical_height, scale=scale))

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
