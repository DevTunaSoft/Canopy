"""Fail-closed network disconnect/reconnect status contract.

This is a pure, single-thread, in-memory reconciler for host code that already
receives network facts through the existing host-event boundary. It reuses
``canopy_core.host_events`` (v2 ``capabilities.report`` topic,
``network_connected`` field) and the fixed network tokens of
``canopy_features.system.quick_controls_state``. It adds no event topic, no
host-event field name, no UI token and no new transport.

Transition tokens are fixed and host-independent::

    unknown --connect--> connected
    unknown --disconnect--> disconnected
    unknown --unavailable--> unavailable
    disconnected|unavailable --connect--> reconnected
    reconnected|connected --connect--> connected
    any --disconnect--> disconnected
    any --unavailable--> unavailable

``reconnected`` is emitted only for the first trusted connect observation
after an outage; steady-state connectivity stays ``connected``. A missing or
untrusted network fact is ``unavailable`` rather than a guess of ``False``.

Safety boundary: no sockets, network access, timers, polling, threads,
processes, credentials, environment reads, clock, Qt, D-Bus or filesystem
I/O. Observations are supplied by trusted host code; this module never probes
the host and never claims real connectivity, Mint acceptance or visual
approval. All input is validated before any state changes and all output
views are immutable with bounded retained history.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
import re
from types import MappingProxyType

from canopy_core.host_events import (
    CAPABILITIES_TOPIC,
    PROTOCOL_VERSION,
    HostEvent,
    HostEventError,
)
from canopy_features.system.quick_controls_state import (
    AVAILABLE,
    STATUS_TOKENS,
    UNAVAILABLE as QC_UNAVAILABLE,
    Observation,
)

__all__ = [
    "CONNECT",
    "CONNECTED",
    "DEFAULT_SOURCE",
    "DISCONNECT",
    "DISCONNECTED",
    "DUPLICATE",
    "KINDS",
    "MAX_HISTORY",
    "MAX_SOURCE_BYTES",
    "NETWORK_FIELD",
    "REDUNDANT",
    "RECONNECTED",
    "STALE",
    "STATUSES",
    "TOPIC",
    "TRANSITION",
    "UNAVAILABLE",
    "UNKNOWN",
    "NetworkObservation",
    "NetworkReconnectClosed",
    "NetworkReconnectError",
    "NetworkStatusView",
    "Outcome",
    "Reconciler",
    "from_host_event",
]


class NetworkReconnectError(HostEventError):
    """Invalid observation, envelope, provenance, bound or caller state."""


class NetworkReconnectClosed(RuntimeError):
    """No observations after explicit cleanup."""


# Existing host-event contract: no topic or field is invented here.
TOPIC = CAPABILITIES_TOPIC
NETWORK_FIELD = "network_connected"
DEFAULT_SOURCE = "host-events"

# Observation kinds and committed status tokens are fixed vocabulary.
CONNECT = "connect"
DISCONNECT = "disconnect"
UNAVAILABLE = "unavailable"
KINDS = frozenset({CONNECT, DISCONNECT, UNAVAILABLE})

UNKNOWN = "unknown"
DISCONNECTED = "disconnected"
RECONNECTED = "reconnected"
CONNECTED = "connected"
STATUSES = frozenset({UNKNOWN, UNAVAILABLE, DISCONNECTED,
                      RECONNECTED, CONNECTED})

# Outcome codes mirror the existing lock/session reconciler conventions.
TRANSITION = "TRANSITION"
DUPLICATE = "DUPLICATE"
STALE = "STALE"
REDUNDANT = "REDUNDANT"
OUTCOMES = frozenset({TRANSITION, DUPLICATE, STALE, REDUNDANT})

MAX_HISTORY = 64
MAX_SOURCE_BYTES = 64
_SOURCE = re.compile(r"[a-z0-9_.:-]{1,64}\Z")

# The UI projection must remain a subset of the already documented tokens.
_UI_TOKEN = MappingProxyType({
    UNKNOWN: "unknown",
    UNAVAILABLE: "unknown",
    DISCONNECTED: "disconnected",
    RECONNECTED: "connected",
    CONNECTED: "connected",
})
if (set(_UI_TOKEN.values()) - STATUS_TOKENS["network"]
        or set(_UI_TOKEN) - STATUSES):  # pragma: no cover - contract guard
    raise RuntimeError("quick-controls network token contract changed")


def _source(value):
    if type(value) is not str:
        raise NetworkReconnectError("observation source must be a string")
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError:
        raise NetworkReconnectError("invalid observation source") from None
    if not 1 <= size <= MAX_SOURCE_BYTES or not _SOURCE.fullmatch(value):
        raise NetworkReconnectError("invalid observation source")
    return value


@dataclass(frozen=True)
class NetworkObservation:
    """One trusted, bounded network fact supplied by the host event loop.

    ``sequence`` is the existing ``HostEvent.sequence`` (or a host-owned
    monotonic counter for callers without a bus). It is mandatory so late and
    replayed facts can be refused deterministically. No free-form status text
    is accepted: only the three fixed kinds above can enter the reconciler.
    """

    kind: str
    sequence: int
    source: str = DEFAULT_SOURCE

    def __post_init__(self):
        if type(self.kind) is not str or self.kind not in KINDS:
            raise NetworkReconnectError("unknown network observation kind")
        if type(self.sequence) is not int or self.sequence < 1:
            raise NetworkReconnectError("observation sequence must be positive")
        _source(self.source)


@dataclass(frozen=True)
class Outcome:
    """Result of one observation; ``previous``/``current`` are committed."""

    status: str
    event: NetworkObservation
    previous: str
    current: str

    def __post_init__(self):
        if self.status not in OUTCOMES:
            raise NetworkReconnectError("unknown reconciliation outcome")
        if (type(self.event) is not NetworkObservation
                or self.previous not in STATUSES
                or self.current not in STATUSES):
            raise NetworkReconnectError("invalid reconciliation outcome")

    @property
    def transitioned(self):
        return self.status == TRANSITION


@dataclass(frozen=True)
class NetworkStatusView:
    """Immutable, bounded status projection with fixed tokens only."""

    status: str
    previous_status: str
    transition_count: int
    observed: bool
    source: str

    def __post_init__(self):
        if (type(self.status) is not str or self.status not in STATUSES
                or type(self.previous_status) is not str
                or self.previous_status not in STATUSES):
            raise NetworkReconnectError("invalid network status token")
        if type(self.transition_count) is not int or self.transition_count < 0:
            raise NetworkReconnectError("invalid transition count")
        if type(self.observed) is not bool or self.observed != (
                self.status != UNKNOWN):
            raise NetworkReconnectError("observation flag contradicts status")
        if self.source != "none":
            _source(self.source)

    @property
    def quick_controls_status(self):
        """Existing network token only; never a module-private token."""
        return _UI_TOKEN[self.status]

    @property
    def availability(self):
        """Display availability derived from connectivity, not a control grant."""
        if self.status in (CONNECTED, RECONNECTED):
            return AVAILABLE
        return QC_UNAVAILABLE

    def to_dict(self):
        """Fresh immutable mapping with a stable, documented key order."""
        return MappingProxyType({
            "status": self.status,
            "previous_status": self.previous_status,
            "transition_count": self.transition_count,
            "observed": self.observed,
            "source": self.source,
            "quick_controls_status": self.quick_controls_status,
            "availability": self.availability,
        })

    def to_event_payload(self):
        """Payload for the existing bus; only already-documented fields.

        The network fact is omitted for ``unknown``/``unavailable`` so no
        reader can mistake a missing fact for ``False``. This is a status
        notice, not a shell capability report and not an acceptance claim.
        """
        payload = {"status": self.status, "source": self.source}
        if self.status in (CONNECTED, RECONNECTED):
            payload[NETWORK_FIELD] = True
        elif self.status == DISCONNECTED:
            payload[NETWORK_FIELD] = False
        elif NETWORK_FIELD in payload:  # pragma: no cover - defensive
            raise NetworkReconnectError("status contradicts network fact")
        return payload

    def as_observation(self):
        """Reuse the existing quick-controls Observation value object."""
        return Observation("network", self.quick_controls_status, self.source)


class Reconciler:
    """Single-thread, bounded reconciler. Call only from the host event loop."""

    def __init__(self, *, history_limit=16):
        if (type(history_limit) is not int
                or not 1 <= history_limit <= MAX_HISTORY):
            raise NetworkReconnectError("invalid history bound")
        self._status = UNKNOWN
        self._previous = UNKNOWN
        self._transitions = 0
        self._source = "none"
        self._last_sequence = 0
        self._seen = deque()
        self._seen_set = set()
        self._history = deque(maxlen=history_limit)
        self._history_cache = None
        self._closed = False

    def _ready(self):
        if self._closed:
            raise NetworkReconnectClosed("network reconciler is closed")

    @property
    def status(self):
        return self._status

    @property
    def previous(self):
        return self._previous

    @property
    def transition_count(self):
        return self._transitions

    @property
    def last_sequence(self):
        return self._last_sequence

    @property
    def history(self):
        """Immutable tuple of the most recent transitions (bounded)."""
        if self._history_cache is None:
            self._history_cache = tuple(self._history)
        return self._history_cache

    @property
    def closed(self):
        return self._closed

    def view(self):
        return NetworkStatusView(self._status, self._previous,
                                 self._transitions, self._status != UNKNOWN,
                                 self._source)

    def observe(self, observation):
        """Apply one trusted observation and return its deterministic outcome."""
        self._ready()
        if type(observation) is not NetworkObservation:
            raise NetworkReconnectError("observe() requires a NetworkObservation")
        fingerprint = (observation.kind, observation.sequence,
                       observation.source)
        if fingerprint in self._seen_set:
            return Outcome(DUPLICATE, observation, self._status, self._status)
        if observation.sequence <= self._last_sequence:
            # Stale and conflicting same-sequence facts are rejected without
            # consuming a dedup slot or changing committed state.
            return Outcome(STALE, observation, self._status, self._status)
        self._seen.append(fingerprint)
        self._seen_set.add(fingerprint)
        if len(self._seen) > MAX_HISTORY:
            self._seen_set.discard(self._seen.popleft())
        self._last_sequence = observation.sequence
        self._source = observation.source
        current = self._next(self._status, observation.kind)
        if current == self._status:
            return Outcome(REDUNDANT, observation, self._status, current)
        self._previous = self._status
        self._status = current
        self._transitions += 1
        outcome = Outcome(TRANSITION, observation, self._previous, current)
        self._history.append(outcome)
        self._history_cache = None
        return outcome

    def close(self):
        """Fail-closed cleanup: release retained facts and history."""
        self._seen.clear()
        self._seen_set.clear()
        self._history.clear()
        self._history_cache = None
        self._closed = True

    @staticmethod
    def _next(status, kind):
        if kind == DISCONNECT:
            return DISCONNECTED
        if kind == UNAVAILABLE:
            return UNAVAILABLE
        if status in (DISCONNECTED, UNAVAILABLE):
            return RECONNECTED
        return CONNECTED


def from_host_event(event, *, source=DEFAULT_SOURCE):
    """Project a delivered v2 host event into a bounded observation.

    Only the already-documented ``capabilities.report`` topic and
    ``network_connected`` bool are read. A missing field yields the graceful
    ``unavailable`` kind; a malformed field, wrong envelope or contradictory
    provenance fails closed instead of inventing connectivity.
    """
    if type(event) is not HostEvent:
        raise NetworkReconnectError("network fact requires a delivered HostEvent")
    if event.version != PROTOCOL_VERSION:
        raise NetworkReconnectError("unsupported host event protocol version")
    if type(event.topic) is not str or event.topic != TOPIC:
        raise NetworkReconnectError("unsupported network status topic")
    if type(event.sequence) is not int or event.sequence < 1:
        raise NetworkReconnectError("invalid host event sequence")
    payload = event.payload
    if not isinstance(payload, Mapping):
        raise NetworkReconnectError("host event payload must be a mapping")
    _source(source)
    try:
        supplied = payload.get("source")
        if supplied is not None and supplied != source:
            raise NetworkReconnectError("contradictory network status provenance")
        present = NETWORK_FIELD in payload
        value = payload[NETWORK_FIELD] if present else None
    except (KeyError, TypeError):
        raise NetworkReconnectError("unreadable network status payload") from None
    if not present:
        kind = UNAVAILABLE
    elif type(value) is bool:
        kind = CONNECT if value else DISCONNECT
    else:
        raise NetworkReconnectError("network_connected must be an exact bool")
    return NetworkObservation(kind, event.sequence, source)
