"""Bounded, offline model of display connect/disconnect recovery events.

Pure-Python state model. It never imports Qt, opens a socket, starts a thread
or service, polls a display, or touches real hardware. A trusted host calls
:meth:`ScreenTopologyModel.apply` with an observed topology snapshot when a
real screen event arrives. This module only decides what changed and what a
shell should do to recover; it does not prove any desktop behavior. Future
integration must wire it into the compiled Qt application's screen signals.
"""
from collections import deque
from dataclasses import dataclass
import re

MAX_MONITORS = 16
MAX_CONNECTOR_LEN = 64
MAX_WIDTH = 7680
MAX_HEIGHT = 4320
MAX_HISTORY = 64

SUPPORTED_RESOLUTIONS = frozenset({
    (640, 480), (800, 600), (1024, 768), (1280, 720),
    (1366, 768), (1440, 900), (1600, 900), (1920, 1080),
    (2560, 1440), (3840, 2160),
})

CONNECTOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")

EVENT_CONNECT = "connect"
EVENT_DISCONNECT = "disconnect"
EVENT_RESOLUTION_CHANGED = "resolution_changed"
EVENT_PRIMARY_CHANGED = "primary_changed"

ACTION_NO_OP = "no_op"
ACTION_RELAYOUT = "relayout"
ACTION_REANCHOR_PRIMARY = "reanchor_primary"
ACTION_CLAMP_RESOLUTION = "clamp_resolution"
ACTION_SUSPEND = "suspend"
ACTION_RESUME = "resume"

__all__ = [
    "MAX_MONITORS", "SUPPORTED_RESOLUTIONS", "TopologyError",
    "Monitor", "Topology", "Change", "RecoveryAction", "RecoveryResult",
    "ScreenTopologyModel", "nearest_supported_resolution",
    "EVENT_CONNECT", "EVENT_DISCONNECT", "EVENT_RESOLUTION_CHANGED",
    "EVENT_PRIMARY_CHANGED", "ACTION_NO_OP", "ACTION_RELAYOUT",
    "ACTION_REANCHOR_PRIMARY", "ACTION_CLAMP_RESOLUTION",
    "ACTION_SUSPEND", "ACTION_RESUME",
]


class TopologyError(ValueError):
    """Invalid monitor, topology, or model configuration."""


def nearest_supported_resolution(width, height):
    """Return nearest supported (width, height) by pixel distance.

    Ties break on the sorted resolution tuple, so the result is deterministic.
    """
    return min(
        SUPPORTED_RESOLUTIONS,
        key=lambda size: (abs(size[0] - width) + abs(size[1] - height), size),
    )


@dataclass(frozen=True)
class Monitor:
    """One observed display; geometry is validated but not hardware-verified."""

    connector: str
    width: int
    height: int
    primary: bool = False

    def __post_init__(self):
        if (type(self.connector) is not str
                or not CONNECTOR.fullmatch(self.connector)):
            raise TopologyError("invalid monitor connector")
        if (type(self.width) is not int or type(self.height) is not int
                or not 1 <= self.width <= MAX_WIDTH
                or not 1 <= self.height <= MAX_HEIGHT):
            raise TopologyError("invalid monitor geometry")
        if type(self.primary) is not bool:
            raise TopologyError("primary flag must be bool")

    @property
    def resolution(self):
        return (self.width, self.height)

    @property
    def supported(self):
        return self.resolution in SUPPORTED_RESOLUTIONS

    def clamped(self):
        """Return a copy using the nearest supported resolution."""
        width, height = nearest_supported_resolution(self.width, self.height)
        return Monitor(self.connector, width, height, self.primary)


@dataclass(frozen=True, init=False)
class Topology:
    """A bounded, deduplicated, connector-sorted set of monitors."""

    monitors: tuple

    def __init__(self, monitors=()):
        if type(monitors) not in (tuple, list):
            raise TopologyError("monitors must be a sequence")
        if len(monitors) > MAX_MONITORS:
            raise TopologyError("too many monitors")
        if any(not isinstance(monitor, Monitor) for monitor in monitors):
            raise TopologyError("topology entries must be Monitor instances")
        items = tuple(sorted(monitors, key=lambda m: m.connector))
        seen = set()
        for monitor in items:
            if monitor.connector in seen:
                raise TopologyError("duplicate monitor connector")
            seen.add(monitor.connector)
        if sum(1 for monitor in items if monitor.primary) > 1:
            raise TopologyError("at most one primary monitor")
        object.__setattr__(self, "monitors", items)

    @property
    def is_empty(self):
        return not self.monitors

    @property
    def connectors(self):
        return frozenset(m.connector for m in self.monitors)

    @property
    def primary(self):
        for monitor in self.monitors:
            if monitor.primary:
                return monitor
        return None


@dataclass(frozen=True)
class Change:
    """A single observed difference between two topologies."""

    kind: str
    connector: str
    detail: tuple = ()


@dataclass(frozen=True)
class RecoveryAction:
    """An advisory shell action; execution belongs to the host, not this model."""

    kind: str
    detail: tuple = ()


@dataclass(frozen=True)
class RecoveryResult:
    """Deterministic recovery decision for one observed topology snapshot."""

    sequence: int
    changes: tuple
    actions: tuple
    safe_topology: Topology

    @property
    def action_kinds(self):
        return tuple(action.kind for action in self.actions)


class ScreenTopologyModel:
    """Reactive, single-owner recovery model with a bounded event history.

    State changes only when :meth:`apply` is called by the trusted host. There
    is no timer, background loop or automatic observation of real displays.
    """

    def __init__(self, history_limit=16):
        if type(history_limit) is not int or not 1 <= history_limit <= MAX_HISTORY:
            raise TopologyError("invalid history limit")
        self._history_limit = history_limit
        self._sequence = 0
        self._current = None
        self._history = deque(maxlen=history_limit)

    @property
    def current(self):
        return self._current

    @property
    def history(self):
        """Immutable tuple snapshot of the bounded recent results."""
        return tuple(self._history)

    def apply(self, topology):
        """Apply one observed snapshot and return its RecoveryResult."""
        if not isinstance(topology, Topology):
            raise TopologyError("apply expects a Topology")
        previous = self._current
        changes = self._diff(previous, topology)
        safe = self._safe_topology(topology)
        actions = self._decide(previous, topology, changes)
        self._sequence += 1
        result = RecoveryResult(self._sequence, changes, actions, safe)
        self._current = topology
        self._history.append(result)
        return result

    def reset(self):
        """Drop all observed state; the caller owns any real re-initialization."""
        self._current = None
        self._history.clear()
        self._sequence = 0

    @staticmethod
    def _diff(previous, current):
        changes = []
        if previous is None:
            for monitor in current.monitors:
                changes.append(Change(EVENT_CONNECT, monitor.connector))
            return tuple(changes)
        before = {m.connector: m for m in previous.monitors}
        after = {m.connector: m for m in current.monitors}
        for connector in sorted(before):
            if connector not in after:
                changes.append(Change(EVENT_DISCONNECT, connector))
        for connector in sorted(after):
            if connector not in before:
                changes.append(Change(EVENT_CONNECT, connector))
                continue
            old, new = before[connector], after[connector]
            if old.resolution != new.resolution:
                changes.append(Change(EVENT_RESOLUTION_CHANGED, connector,
                                      (old.resolution, new.resolution)))
            if old.primary != new.primary:
                changes.append(Change(EVENT_PRIMARY_CHANGED, connector,
                                      (old.primary, new.primary)))
        return tuple(changes)

    @staticmethod
    def _safe_topology(topology):
        """Clamp unsupported resolutions and guarantee one primary when non-empty."""
        if topology.is_empty:
            return Topology(())
        items = []
        primary_seen = False
        for monitor in topology.monitors:
            candidate = monitor if monitor.supported else monitor.clamped()
            if candidate.primary:
                if primary_seen:
                    candidate = Monitor(candidate.connector, candidate.width,
                                        candidate.height, False)
                else:
                    primary_seen = True
            items.append(candidate)
        if not primary_seen:
            first = items[0]
            items[0] = Monitor(first.connector, first.width, first.height, True)
        return Topology(items)

    @staticmethod
    def _decide(previous, current, changes):
        if current.is_empty:
            return (RecoveryAction(ACTION_SUSPEND),)
        actions = []
        unsupported = tuple(sorted(m.connector for m in current.monitors
                                   if not m.supported))
        if unsupported:
            actions.append(RecoveryAction(ACTION_CLAMP_RESOLUTION, unsupported))
        if previous is None or previous.is_empty:
            actions.extend((RecoveryAction(ACTION_RESUME),
                            RecoveryAction(ACTION_REANCHOR_PRIMARY),
                            RecoveryAction(ACTION_RELAYOUT)))
            return tuple(actions)
        reanchor = any(c.kind == EVENT_PRIMARY_CHANGED for c in changes)
        old_primary = previous.primary.connector if previous.primary else None
        if old_primary is not None and any(
                c.kind == EVENT_DISCONNECT and c.connector == old_primary
                for c in changes):
            reanchor = True
        if reanchor:
            actions.append(RecoveryAction(ACTION_REANCHOR_PRIMARY))
        if changes:
            actions.append(RecoveryAction(ACTION_RELAYOUT))
        return tuple(actions) or (RecoveryAction(ACTION_NO_OP),)
