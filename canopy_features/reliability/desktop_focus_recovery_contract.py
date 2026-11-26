"""Fail-closed desktop focus/session recovery after a shell restart.

This is a pure, single-thread, in-memory source contract. It reconciles facts
that trusted host code has *already* delivered through the existing
``canopy_core.host_events`` v2 boundary:

* ``capabilities.report`` -- the host-owned ``needs_recovery`` and
  ``has_active_pack`` booleans mark the restart/recovery condition;
* ``session.state.changed`` -- the documented ``state`` field confirms an
  active, locked or suspended desktop session;
* ``window.state.changed`` -- the documented ``window_count`` field confirms
  whether there is a window worth focusing.

No topic, payload field, protocol version, UI token or transport is added to
the host-event contract. This module never emits, subscribes, focuses a window,
starts a shell, probes a desktop, reads the environment or performs I/O. It
produces only an immutable *offer* decision for a later trusted host adapter;
``focus_actuated`` and every other real-world claim are always False.

Fail-closed defaults: with no recovery report the status is ``cold`` and the
decision is ``no_restore``. Missing facts become ``unavailable`` observations
that cannot unlock a restore. Malformed, contradictory, unknown or reordered
facts are refused without changing committed state.
"""
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
import re
import unicodedata
from types import MappingProxyType

from canopy_core.host_events import (
    CAPABILITIES_TOPIC,
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    HostEvent,
    HostEventError,
)

__all__ = [
    "AWAITING_SESSION", "AWAITING_WINDOWS", "CAPABILITY_TOPIC",
    "CLEARED", "COLD", "DEFERRED", "DEFAULT_SOURCE", "DUPLICATE",
    "KINDS", "MAX_HISTORY", "MAX_SEQUENCE", "MAX_SEEN", "MAX_SOURCE_BYTES",
    "MAX_WINDOW_COUNT", "NO_RESTORE", "OFFER_RESTORE",
    "REDUNDANT", "RESTART", "RESTORE_READY", "SESSION_ACTIVE",
    "SESSION_INACTIVE", "SESSION_TOPIC", "STALE", "STATUSES", "TOPICS",
    "TRANSITION", "UNAVAILABLE", "WINDOW_TOPIC", "WINDOWS_EMPTY",
    "WINDOWS_READY", "RecoveryContractClosed", "RecoveryContractError",
    "RecoveryObservation", "RecoveryView", "Outcome", "Reconciler",
    "from_host_event",
]


class RecoveryContractError(HostEventError):
    """Invalid event, observation, provenance, bound or caller state."""


class RecoveryContractClosed(RuntimeError):
    """No observations after explicit cleanup."""


# Existing host-event contract only. The guard fails closed if a coordinating
# change ever alters that contract underneath this adapter.
SESSION_TOPIC = "session.state.changed"
WINDOW_TOPIC = "window.state.changed"
CAPABILITY_TOPIC = CAPABILITIES_TOPIC
TOPICS = frozenset({SESSION_TOPIC, WINDOW_TOPIC, CAPABILITY_TOPIC})
if (PROTOCOL_VERSION != 2 or len(HOST_EVENT_TOPICS) != 4
        or not TOPICS.issubset(HOST_EVENT_TOPICS)):  # pragma: no cover
    raise RuntimeError("host event contract changed; recovery must be reviewed")

DEFAULT_SOURCE = "host-events"
SCHEMA = 1
MAX_SEQUENCE = 1_000_000_000_000
MAX_SOURCE_BYTES = 64
MAX_WINDOW_COUNT = 1_000_000
MAX_COMPONENT_COUNT = 64
MAX_VALUE_BYTES = 512
MAX_SEEN = 64
MAX_HISTORY = 16
_SOURCE = re.compile(r"[a-z0-9_.:-]{1,64}\Z")
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})

# Observation vocabulary: only facts a trusted host can supply.
RESTART = "restart"
CLEARED = "cleared"
SESSION_ACTIVE = "session_active"
SESSION_INACTIVE = "session_inactive"
WINDOWS_READY = "windows_ready"
WINDOWS_EMPTY = "windows_empty"
UNAVAILABLE = "unavailable"
KINDS = frozenset({RESTART, CLEARED, SESSION_ACTIVE, SESSION_INACTIVE,
                   WINDOWS_READY, WINDOWS_EMPTY, UNAVAILABLE})

# Committed, host-independent status tokens.
COLD = "cold"
AWAITING_SESSION = "awaiting_session"
AWAITING_WINDOWS = "awaiting_windows"
DEFERRED = "deferred"
RESTORE_READY = "restore_ready"
STATUSES = frozenset({COLD, AWAITING_SESSION, AWAITING_WINDOWS,
                      DEFERRED, RESTORE_READY})

NO_RESTORE = "no_restore"
OFFER_RESTORE = "offer_restore"

# Outcome tokens mirror the existing reliability reconcilers.
TRANSITION = "TRANSITION"
DUPLICATE = "DUPLICATE"
STALE = "STALE"
REDUNDANT = "REDUNDANT"
OUTCOMES = frozenset({TRANSITION, DUPLICATE, STALE, REDUNDANT})

_SESSION_STATES = {"active": SESSION_ACTIVE,
                   "locked": SESSION_INACTIVE,
                   "suspended": SESSION_INACTIVE}
_SESSION_KEYS = frozenset({"state", "source"})
_WINDOW_KEYS = frozenset({"window_count", "state", "source"})
_CAPABILITY_KEYS = frozenset({
    "status", "schema", "component_count", "component_codes",
    "has_active_pack", "needs_recovery", "negative_claims", "source",
})
_MISSING = object()


def _source(value):
    if type(value) is not str:
        raise RecoveryContractError("observation source must be a string")
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError:
        raise RecoveryContractError("invalid observation source") from None
    if not 1 <= size <= MAX_SOURCE_BYTES or not _SOURCE.fullmatch(value):
        raise RecoveryContractError("invalid observation source")
    return value


def _bounded_text(value, limit, label):
    if type(value) is not str or not value:
        raise RecoveryContractError("invalid " + label)
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError:
        raise RecoveryContractError("invalid " + label) from None
    if size > limit:
        raise RecoveryContractError(label + " exceeds bound")
    if any(unicodedata.category(char) in _UNSAFE_CATEGORIES for char in value):
        raise RecoveryContractError("unsafe " + label)
    return value


def _flag(value):
    """Strict bool projection; a missing value is never guessed."""
    if type(value) is not bool:
        raise RecoveryContractError("capability flag must be an exact bool")
    return value


@dataclass(frozen=True)
class RecoveryObservation:
    """One trusted, bounded recovery fact supplied by the host event loop.

    ``sequence`` is the existing ``HostEvent.sequence``. It is mandatory so
    late, replayed and pre-restart facts can be refused deterministically.
    """

    kind: str
    sequence: int
    source: str = DEFAULT_SOURCE

    def __post_init__(self):
        if type(self.kind) is not str or self.kind not in KINDS:
            raise RecoveryContractError("unknown recovery observation kind")
        if (type(self.sequence) is not int
                or not 1 <= self.sequence <= MAX_SEQUENCE):
            raise RecoveryContractError("invalid observation sequence")
        _source(self.source)


@dataclass(frozen=True)
class Outcome:
    """Result of one observation; ``previous``/``current`` are committed."""

    status: str
    event: RecoveryObservation
    previous: str
    current: str

    def __post_init__(self):
        if type(self.status) is not str or self.status not in OUTCOMES:
            raise RecoveryContractError("unknown reconciliation outcome")
        if type(self.event) is not RecoveryObservation:
            raise RecoveryContractError("outcome requires an observation")
        if (type(self.previous) is not str
                or self.previous not in STATUSES
                or type(self.current) is not str
                or self.current not in STATUSES):
            raise RecoveryContractError("invalid reconciliation status")

    @property
    def transitioned(self):
        return self.status == TRANSITION


@dataclass(frozen=True)
class RecoveryView:
    """Immutable decision projection with hardcoded negative claims."""

    status: str
    previous_status: str
    transition_count: int
    restart_seen: bool
    session_ready: bool
    window_ready: bool
    source: str
    decision: str

    def __post_init__(self):
        if (type(self.status) is not str or self.status not in STATUSES
                or type(self.previous_status) is not str
                or self.previous_status not in STATUSES):
            raise RecoveryContractError("invalid recovery status token")
        if (type(self.transition_count) is not int
                or self.transition_count < 0):
            raise RecoveryContractError("invalid transition count")
        for flag in (self.restart_seen, self.session_ready, self.window_ready):
            if type(flag) is not bool:
                raise RecoveryContractError("recovery view flags must be bools")
        _source(self.source)
        expected = OFFER_RESTORE if self.status == RESTORE_READY else NO_RESTORE
        if type(self.decision) is not str or self.decision != expected:
            raise RecoveryContractError("decision disagrees with status")
        if self.status == COLD and any(
                (self.restart_seen, self.session_ready, self.window_ready)):
            raise RecoveryContractError("cold status carries recovery facts")
        if self.status == RESTORE_READY and not all(
                (self.restart_seen, self.session_ready, self.window_ready)):
            raise RecoveryContractError("restore status lacks required facts")

    def to_dict(self):
        """Fresh read-only record in fixed order; no real-world claim escapes."""
        return MappingProxyType({
            "schema": SCHEMA,
            "status": self.status,
            "decision": self.decision,
            "previous_status": self.previous_status,
            "transition_count": self.transition_count,
            "restart_seen": self.restart_seen,
            "session_ready": self.session_ready,
            "window_ready": self.window_ready,
            "source": self.source,
            "focus_actuated": False,
            "window_focused": False,
            "shell_running": False,
            "desktop_session_started": False,
            "mint_acceptance_proven": False,
            "owner_visual_approval": False,
            "measurement_performed": False,
        })


class Reconciler:
    """Single-thread, bounded reconciler. Call only from the host event loop."""

    def __init__(self, *, history_limit=MAX_HISTORY):
        if (type(history_limit) is not int
                or not 1 <= history_limit <= MAX_HISTORY):
            raise RecoveryContractError("invalid history bound")
        self._status = COLD
        self._previous = COLD
        self._transitions = 0
        self._last_sequence = 0
        self._source = "none"
        self._restart_sequence = 0
        self._session_sequence = 0
        self._window_sequence = 0
        self._session_ready = False
        self._window_ready = False
        self._seen = deque()
        self._seen_set = set()
        self._history = deque(maxlen=history_limit)
        self._history_cache = None
        self._closed = False

    def _ready(self):
        if self._closed:
            raise RecoveryContractClosed("recovery reconciler is closed")

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
        if self._history_cache is None:
            self._history_cache = tuple(self._history)
        return self._history_cache

    @property
    def closed(self):
        return self._closed

    def view(self):
        return RecoveryView(
            self._status, self._previous, self._transitions,
            self._status != COLD, self._session_ready, self._window_ready,
            self._source,
            OFFER_RESTORE if self._status == RESTORE_READY else NO_RESTORE,
        )

    def _reset_facts(self):
        self._restart_sequence = 0
        self._session_sequence = 0
        self._window_sequence = 0
        self._session_ready = False
        self._window_ready = False
        self._source = "none"

    def _advance(self, observation):
        """Apply one accepted fact and return the resulting committed status."""
        kind = observation.kind
        if kind == RESTART:
            self._reset_facts()
            self._restart_sequence = observation.sequence
            self._source = observation.source
            self._session_ready = False
            self._window_ready = False
            return AWAITING_SESSION
        if kind == CLEARED:
            self._reset_facts()
            return COLD
        if (self._restart_sequence == 0
                or observation.sequence <= self._restart_sequence):
            # Pre-restart facts cannot describe the restarted desktop.
            return self._status
        if kind == UNAVAILABLE:
            # A missing field is not a ready fact and never retracts one.
            return self._status
        if (self._status == RESTORE_READY
                and kind in (SESSION_ACTIVE, WINDOWS_READY)):
            # A repeated positive fact does not re-offer a restore.
            return self._status
        self._source = observation.source
        if kind in (SESSION_ACTIVE, SESSION_INACTIVE):
            self._session_sequence = observation.sequence
            self._session_ready = kind == SESSION_ACTIVE
            if kind == SESSION_INACTIVE:
                return DEFERRED
            if (self._window_ready
                    and self._window_sequence > self._session_sequence):
                return RESTORE_READY
            return AWAITING_WINDOWS
        self._window_sequence = observation.sequence
        self._window_ready = kind == WINDOWS_READY
        if kind == WINDOWS_EMPTY:
            return DEFERRED
        if self._session_ready:
            return RESTORE_READY
        if self._status == DEFERRED:
            # A locked/suspended session is not re-armed by window activity.
            return DEFERRED
        return AWAITING_SESSION

    def observe(self, observation):
        """Apply one trusted observation and return its deterministic outcome."""
        self._ready()
        if type(observation) is not RecoveryObservation:
            raise RecoveryContractError("observe() requires a RecoveryObservation")
        fingerprint = (observation.kind, observation.sequence,
                       observation.source)
        if fingerprint in self._seen_set:
            return Outcome(DUPLICATE, observation, self._status, self._status)
        if observation.sequence <= self._last_sequence:
            # Rejected facts consume no dedup slot and cannot regress state.
            return Outcome(STALE, observation, self._status, self._status)
        self._seen.append(fingerprint)
        self._seen_set.add(fingerprint)
        if len(self._seen) > MAX_SEEN:
            self._seen_set.discard(self._seen.popleft())
        self._last_sequence = observation.sequence
        previous = self._status
        current = self._advance(observation)
        if current == previous:
            return Outcome(REDUNDANT, observation, previous, current)
        self._previous = previous
        self._status = current
        self._transitions += 1
        outcome = Outcome(TRANSITION, observation, previous, current)
        self._history.append(outcome)
        self._history_cache = None
        return outcome

    def close(self):
        """Fail-closed cleanup: release retained facts and refuse later input."""
        self._reset_facts()
        self._seen.clear()
        self._seen_set.clear()
        self._history.clear()
        self._history_cache = None
        self._last_sequence = 0
        self._previous = COLD
        self._status = COLD
        self._transitions = 0
        self._closed = True


def _envelope(event, source):
    if type(event) is not HostEvent:
        raise RecoveryContractError("recovery fact requires a delivered HostEvent")
    if event.version != PROTOCOL_VERSION:
        raise RecoveryContractError("unsupported host event protocol version")
    if type(event.topic) is not str or event.topic not in TOPICS:
        raise RecoveryContractError("unsupported recovery event topic")
    if (type(event.sequence) is not int
            or not 1 <= event.sequence <= MAX_SEQUENCE):
        raise RecoveryContractError("invalid host event sequence")
    payload = event.payload
    if not isinstance(payload, Mapping):
        raise RecoveryContractError("host event payload must be a mapping")
    _source(source)
    supplied = payload.get("source", _MISSING)
    if supplied is not _MISSING and supplied != source:
        raise RecoveryContractError("contradictory recovery event provenance")
    if (event.topic == SESSION_TOPIC
            and not _SESSION_KEYS.issuperset(payload)):
        raise RecoveryContractError("unsupported session event field")
    if (event.topic == WINDOW_TOPIC
            and not _WINDOW_KEYS.issuperset(payload)):
        raise RecoveryContractError("unsupported window event field")
    if (event.topic == CAPABILITY_TOPIC
            and not _CAPABILITY_KEYS.issuperset(payload)):
        raise RecoveryContractError("unsupported capability event field")
    return payload


def _capability_kind(payload):
    status = payload.get("status", _MISSING)
    if type(status) is not str or status != "CAPABILITY_REPORT":
        raise RecoveryContractError("invalid capability report status")
    schema = payload.get("schema", _MISSING)
    if type(schema) is not int or schema != SCHEMA:
        raise RecoveryContractError("unsupported capability report schema")
    count = payload.get("component_count", _MISSING)
    if (type(count) is not int
            or not 0 <= count <= MAX_COMPONENT_COUNT):
        raise RecoveryContractError("invalid capability component count")
    for key in ("component_codes", "negative_claims"):
        value = payload.get(key, _MISSING)
        if value is not _MISSING:
            _bounded_text(value, MAX_VALUE_BYTES, "capability " + key)
    needs = payload.get("needs_recovery", _MISSING)
    active = payload.get("has_active_pack", _MISSING)
    if needs is _MISSING or active is _MISSING:
        return UNAVAILABLE
    needs = _flag(needs)
    active = _flag(active)
    if needs and active:
        # A host cannot simultaneously report an active presentation and a
        # recovery-required restart. Refuse the whole record.
        raise RecoveryContractError("contradictory capability recovery flags")
    return RESTART if needs else CLEARED


def _session_kind(payload):
    state = payload.get("state", _MISSING)
    if state is _MISSING:
        return UNAVAILABLE
    if type(state) is not str or state not in _SESSION_STATES:
        raise RecoveryContractError("unsupported session state token")
    return _SESSION_STATES[state]


def _window_kind(payload):
    if "state" in payload:
        _bounded_text(payload["state"], MAX_SOURCE_BYTES, "window state")
    count = payload.get("window_count", _MISSING)
    if count is _MISSING:
        return UNAVAILABLE
    if (type(count) is not int
            or not 0 <= count <= MAX_WINDOW_COUNT):
        raise RecoveryContractError("invalid window count")
    return WINDOWS_READY if count else WINDOWS_EMPTY


def from_host_event(event, *, source=DEFAULT_SOURCE):
    """Project one delivered v2 host event into a bounded recovery observation.

    Only the three already-documented topics and their existing fields are
    read. A missing fact yields ``unavailable``; malformed, unknown or
    contradictory facts raise ``RecoveryContractError`` instead of inventing
    a recovery decision. Nothing is emitted, subscribed or observed live.
    """
    payload = _envelope(event, source)
    if event.topic == CAPABILITY_TOPIC:
        kind = _capability_kind(payload)
    elif event.topic == SESSION_TOPIC:
        kind = _session_kind(payload)
    else:
        kind = _window_kind(payload)
    return RecoveryObservation(kind, event.sequence, source)
