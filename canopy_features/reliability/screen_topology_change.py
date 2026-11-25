"""Offline model of display connect/disconnect recovery events.

This module models recovery *decisions* for display topology changes. It reads
only monitor snapshots supplied by a trusted caller: it never queries Qt, X11,
Wayland, D-Bus, the filesystem or hardware, and it never polls, sleeps or
starts a background service. No desktop state changes here. A future reviewed
Qt/session adapter must feed real signals into ``observe`` and prove window
relocation, compositor behavior and lifecycle cleanup before this model can
contribute to user-facing reliability (for example reliability gate R008).

Events are published through the existing bounded ``canopy_core.host_events``
primitive on the ``session.state.changed`` topic. That primitive supplies
monotonic sequence numbers, immutable payloads, trust allowlisting,
single-thread ownership and fail-closed cleanup; this module adds only the
display-specific planning and bounded history.
"""
from collections import deque
from dataclasses import dataclass

from canopy_core.host_events import HostEvents, HostEventsClosed

MAX_MONITORS = 16
MAX_HISTORY = 32
MAX_ID_LENGTH = 64
MAX_DIMENSION = 8192

DEFAULT_SUPPORTED_RESOLUTIONS = frozenset({
    (640, 480), (1024, 768), (1280, 720), (1920, 1080),
    (2560, 1440), (3840, 2160),
})

ACTIONS = frozenset({
    "no_monitor", "connect", "disconnect", "reconfigure",
    "resolution_changed", "resolution_fallback", "stable",
})
DISPLAY_STATES = frozenset({"safe", "active", "reconfigured"})


@dataclass(frozen=True)
class Monitor:
    """One connected display reported by a trusted caller."""
    monitor_id: str
    width: int
    height: int

    def __post_init__(self):
        if (not isinstance(self.monitor_id, str)
                or not self.monitor_id.strip()
                or len(self.monitor_id) > MAX_ID_LENGTH):
            raise ValueError("invalid monitor id")
        for value in (self.width, self.height):
            if (type(value) is not int
                    or not 1 <= value <= MAX_DIMENSION):
                raise ValueError("invalid monitor resolution")


@dataclass(frozen=True)
class RecoveryEvent:
    """Immutable, bounded result of one observed topology snapshot."""
    sequence: int
    action: str
    display_state: str
    monitor_count: int
    added: tuple
    removed: tuple
    changed: tuple
    fallback: tuple
    relocate_windows: bool
    safe_mode: bool


def _nearest_supported(width, height, supported):
    """Deterministic nearest supported resolution by pixel area then size."""
    return min(
        supported,
        key=lambda r: (abs(r[0] * r[1] - width * height),
                       abs(r[0] - width) + abs(r[1] - height), r[0], r[1]),
    )


def _validate_supported(supported):
    if (not isinstance(supported, (frozenset, set, tuple, list))
            or not supported):
        raise ValueError("supported resolutions must be a non-empty collection")
    result = []
    for pair in supported:
        if (not isinstance(pair, tuple) or len(pair) != 2
                or any(type(v) is not int or not 1 <= v <= MAX_DIMENSION
                       for v in pair)):
            raise ValueError("invalid supported resolution")
        result.append(pair)
    return frozenset(result)


def _normalize(monitors):
    """Bound and validate one caller snapshot without keeping caller objects."""
    if monitors is None:
        return ()
    if isinstance(monitors, (str, bytes, dict)):
        raise ValueError("monitors must be an iterable of Monitor objects")
    result = []
    seen = set()
    for index, item in enumerate(monitors):
        if index >= MAX_MONITORS:
            raise ValueError("monitor count exceeds bound")
        if not isinstance(item, Monitor):
            raise ValueError("each monitor must be a Monitor object")
        if item.monitor_id in seen:
            raise ValueError("duplicate monitor id")
        seen.add(item.monitor_id)
        result.append(item)
    return tuple(result)


class ScreenTopologyRecovery:
    """Bounded, event-driven model of display recovery decisions.

    ``observe`` is called only when a trusted host adapter reports a topology
    change. There is no timer, poll loop, thread, process, network or file
    access. History and accepted monitor count are hard bounded.
    """

    def __init__(self, *, supported=DEFAULT_SUPPORTED_RESOLUTIONS,
                 history=MAX_HISTORY):
        if type(history) is not int or not 1 <= history <= MAX_HISTORY:
            raise ValueError("invalid history bound")
        self._supported = _validate_supported(supported)
        self._previous = None
        self._history = deque(maxlen=history)
        self._host_events = deque(maxlen=history)
        recorded = self._host_events.append

        def record(event):
            recorded(event)

        self._callback = record
        self._bus = HostEvents({"session.state.changed": [record]})
        self._token = self._bus.subscribe("session.state.changed", record)

    def _plan(self, monitors):
        """Compute the next decision from current and previous snapshots."""
        previous = self._previous or ()
        current_ids = {m.monitor_id: (m.width, m.height) for m in monitors}
        previous_ids = {m.monitor_id: (m.width, m.height) for m in previous}
        added = tuple(sorted(current_ids.keys() - previous_ids.keys()))
        removed = tuple(sorted(previous_ids.keys() - current_ids.keys()))
        changed = tuple(sorted(
            name for name in current_ids.keys() & previous_ids.keys()
            if current_ids[name] != previous_ids[name]
        ))
        fallback = tuple(
            (m.monitor_id,) + _nearest_supported(
                m.width, m.height, self._supported)
            for m in monitors
            if (m.width, m.height) not in self._supported
        )
        relocate = bool(removed) and bool(monitors)
        if not monitors:
            action, display_state, safe = "no_monitor", "safe", True
        elif fallback:
            action, display_state, safe = (
                "resolution_fallback", "reconfigured", False)
        elif added and removed:
            action, display_state, safe = "reconfigure", "reconfigured", False
        elif added:
            action, display_state, safe = "connect", "active", False
        elif removed:
            action, display_state, safe = "disconnect", "reconfigured", False
        elif changed:
            action, display_state, safe = (
                "resolution_changed", "reconfigured", False)
        else:
            action, display_state, safe = "stable", "active", False
        return RecoveryEvent(
            0, action, display_state, len(monitors), added, removed, changed,
            fallback, relocate, safe,
        )

    def observe(self, monitors):
        """Record one topology snapshot and return its recovery decision."""
        if self._bus.closed:
            raise HostEventsClosed("screen topology model is closed")
        snapshot = _normalize(monitors)
        decision = self._plan(snapshot)
        result = self._bus.emit("session.state.changed", {
            "topology_action": decision.action,
            "display_state": decision.display_state,
            "monitor_count": decision.monitor_count,
            "added_count": len(decision.added),
            "removed_count": len(decision.removed),
            "fallback_count": len(decision.fallback),
            "relocate_windows": decision.relocate_windows,
            "safe_mode": decision.safe_mode,
        })
        committed = RecoveryEvent(
            result.event.sequence, decision.action, decision.display_state,
            decision.monitor_count, decision.added, decision.removed,
            decision.changed, decision.fallback, decision.relocate_windows,
            decision.safe_mode,
        )
        self._previous = snapshot
        self._history.append(committed)
        return committed

    def events(self):
        """Return a read-only tuple of the most recent bounded decisions."""
        return tuple(self._history)

    def host_events(self):
        """Return the published host events, newest history bounded."""
        return tuple(self._host_events)

    def close(self):
        """Release all references and fail closed for later observations."""
        if self._bus.closed:
            return
        self._bus.unsubscribe(self._token)
        self._bus.close()
        self._history.clear()
        self._host_events.clear()

    @property
    def closed(self):
        return self._bus.closed
