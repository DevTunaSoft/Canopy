"""Bounded activation / minimize / restore contracts at the host-event boundary.

A trusted host pushes already-delivered protocol-v2 ``window.state.changed``
events into a small intake queue. Each event is projected into a bounded
observation of the window state the host published, then folded against a
host-pinned target state using the existing, unchanged
``canopy_features.windows.window_state_capabilities`` transition table and
negotiation record. Every result is decision-only: a later reviewed WM bridge
*may* actuate an offered action, but this module never requests a real window
operation.

Scope and non-claims:
- No new host topic, payload field, protocol version, callback or transport.
  Only the already-documented ``state`` and ``source`` fields are read; any
  other field on the window topic is refused by this consumer.
- No X11/Wayland/WM/compositor call, Qt bridge, QML, visible window, process,
  thread, timer, poll loop, socket, filesystem or environment read.
- No fabricated Mint acceptance or owner visual approval. ``wm_requests`` is
  always 0, ``polling`` is always false, acceptance is ``NOT_ESTABLISHED``,
  observation is ``NOT_PERFORMED`` and screen-reader behavior is ``NOT_RUN``.
- This is not the dock running-indicator source, the workspace behavior
  contract, window-reference validation, focus-intent authorization or a
  compiled-runtime adapter. Those layers are reused only where noted, never
  modified.
"""
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import islice
import re
import unicodedata
from types import MappingProxyType

from canopy_core.host_events import (
    CAPABILITIES_TOPIC,
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    HostEvent,
)
from canopy_features.windows.window_state_capabilities import (
    VALID_TRANSITIONS,
    Negotiation,
    WindowState,
    WindowStateAction,
    WindowStateFeature,
)

__all__ = [
    "ACTIONS", "DEFAULT_SOURCE", "DEFER", "FALLBACK", "KINDS", "MAX_DRAIN",
    "MAX_HISTORY", "MAX_PENDING", "MAX_SEQUENCE", "NO_DECISION", "NO_FACTS",
    "OBSERVED", "OFFER", "OUTCOMES", "REASONS", "REDUNDANT", "REJECTED",
    "SCHEMA", "STATES", "TOPICS", "WINDOW_KEYS", "WINDOW_TOPIC",
    "ActivationBoundary", "ActivationClosed", "ActivationDecision",
    "ActivationError", "ActivationObservation", "from_host_event",
]

WINDOW_TOPIC = "window.state.changed"
TOPICS = frozenset({WINDOW_TOPIC})
if (PROTOCOL_VERSION != 2 or len(HOST_EVENT_TOPICS) != 4
        or CAPABILITIES_TOPIC not in HOST_EVENT_TOPICS
        or not TOPICS.issubset(HOST_EVENT_TOPICS)):  # pragma: no cover
    raise RuntimeError("host event contract changed; activation boundary must be reviewed")

SCHEMA = 1
DEFAULT_SOURCE = "host-events"
MAX_SEQUENCE = 1_000_000_000_000
MAX_PENDING = 16
MAX_DRAIN = 8
MAX_HISTORY = 16
MAX_SOURCE_BYTES = 64
MAX_STATE_BYTES = 16

# Exact consumer allowlist: other documented fields on this topic belong to
# other consumers (crash reports, workspace behavior, notifications) and must
# not be reinterpreted as activation facts.
WINDOW_KEYS = frozenset({"state", "source"})

OBSERVED = "observed"
NO_FACTS = "no_facts"
KINDS = frozenset({OBSERVED, NO_FACTS})

# An offer is a permission to consider a later real bridge request, never an
# executed activation. Redundant/rejected/deferred outcomes offer no action.
OFFER = "offer"
FALLBACK = "fallback"
DEFER = "defer"
REDUNDANT = "redundant"
REJECTED = "rejected"
NO_DECISION = "none"
OUTCOMES = frozenset({OFFER, FALLBACK, DEFER, REDUNDANT, REJECTED})

REASONS = frozenset({
    "no_facts", "already_at_target", "ambiguous_prior_state",
    "no_direct_transition", "capability_granted", "capability_refused",
})
STATUSES = frozenset({"SUPPORTED", "PARTIAL", "UNSUPPORTED"})
STATES = frozenset(state.value for state in WindowState)
ACTIONS = frozenset(action.value for action in WindowStateAction)

ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"
SCREEN_READER_NOT_RUN = "NOT_RUN"
WM_REQUESTS = 0
POLLING_ENABLED = False
MINT_ACCEPTANCE_PROVEN = False
OWNER_VISUAL_APPROVAL = False

# Invert the existing (current state, action) -> resulting state table. This
# derives the only legal activation/minimize/restore actions without a second
# state machine and without editing the merged capability module.
_TRANSITION_ACTION = MappingProxyType({
    (state.value, result.value): action.value
    for (state, action), result in VALID_TRANSITIONS.items()
})
_ACTION_ENUM = MappingProxyType({action.value: action for action in WindowStateAction})

_SOURCE = re.compile(r"[a-z0-9_.:-]{1,64}\Z")
_STATE = re.compile(r"[a-z]{1,16}\Z")
_REASON = re.compile(r"[a-z_]{1,32}\Z")
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_MISSING = object()


class ActivationError(ValueError):
    """Invalid event, context, bound or lifecycle check failed closed."""


class ActivationClosed(RuntimeError):
    """No event, decision or snapshot after explicit cleanup."""


def _bounded_text(value, limit, label, pattern):
    if type(value) is not str or not value:
        raise ActivationError("invalid " + label)
    # Reject control, format, surrogate, private-use, unassigned and line
    # separator categories before any whitespace folding or byte counting.
    if any(unicodedata.category(char) in _UNSAFE_CATEGORIES for char in value):
        raise ActivationError("unsafe " + label)
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError:
        raise ActivationError("invalid UTF-8 " + label) from None
    if size > limit:
        raise ActivationError(label + " exceeds bound")
    if not pattern.fullmatch(value):
        raise ActivationError("invalid " + label)
    return value


def _source(value):
    return _bounded_text(value, MAX_SOURCE_BYTES, "source", _SOURCE)


def _state(value):
    state = _bounded_text(value, MAX_STATE_BYTES, "window state", _STATE)
    if state not in STATES:
        raise ActivationError("unknown window state")
    return state


def _reason(value):
    reason = _bounded_text(value, 32, "reason", _REASON)
    if reason not in REASONS:
        raise ActivationError("unknown decision reason")
    return reason


def _sequence(value):
    if type(value) is not int or not 1 <= value <= MAX_SEQUENCE:
        raise ActivationError("invalid host event sequence")
    return value


def _fields(event):
    if type(event.fields) is not tuple:
        raise ActivationError("host event fields must be a tuple")
    keys = []
    for field in event.fields:
        if (type(field) is not tuple or len(field) != 2
                or type(field[0]) is not str):
            raise ActivationError("malformed host event field")
        if field[0] in keys:
            raise ActivationError("duplicate host event field")
        keys.append(field[0])
    if not set(keys).issubset(WINDOW_KEYS):
        raise ActivationError("unsupported activation event field")
    return event.payload


@dataclass(frozen=True)
class ActivationObservation:
    """One bounded fact projected from a delivered v2 window event."""

    kind: str
    sequence: int
    state: str
    source: str

    def __post_init__(self):
        if type(self.kind) is not str or self.kind not in KINDS:
            raise ActivationError("unknown observation kind")
        _sequence(self.sequence)
        _source(self.source)
        if self.kind == OBSERVED:
            _state(self.state)
        elif type(self.state) is not str or self.state:
            raise ActivationError("missing-facts observation carries a state")

    def to_dict(self):
        """Fresh read-only projection in fixed order."""
        return MappingProxyType({
            "kind": self.kind,
            "sequence": self.sequence,
            "state": self.state,
            "source": self.source,
        })


def from_host_event(event, *, source=DEFAULT_SOURCE):
    """Project one delivered v2 window event into a bounded observation.

    No other host topic, field or protocol version is accepted. Missing state
    is reported explicitly as ``no_facts``; malformed or contradictory facts
    raise ``ActivationError`` instead of inventing a window state.
    """
    if type(event) is not HostEvent:
        raise ActivationError("activation fact requires a delivered HostEvent")
    if event.version != PROTOCOL_VERSION:
        raise ActivationError("unsupported host event protocol version")
    if type(event.topic) is not str or event.topic not in TOPICS:
        raise ActivationError("unsupported activation event topic")
    sequence = _sequence(event.sequence)
    source = _source(source)
    payload = _fields(event)
    if not isinstance(payload, Mapping):
        raise ActivationError("host event payload must be a mapping")

    supplied = payload.get("source", _MISSING)
    if supplied is not _MISSING and supplied != source:
        raise ActivationError("contradictory activation event provenance")

    state = payload.get("state", _MISSING)
    if state is _MISSING:
        return ActivationObservation(NO_FACTS, sequence, "", source)
    return ActivationObservation(OBSERVED, sequence, _state(state), source)


@dataclass(frozen=True)
class ActivationDecision:
    """Immutable decision-only result; every real-world claim is negative."""

    schema: int
    outcome: str
    action: str
    reason: str
    status: str
    kind: str
    sequence: int
    source: str
    observed_state: str
    target_state: str
    acceptance: str
    observation: str
    wm_requests: int
    polling: bool
    mint_acceptance_proven: bool
    owner_visual_approval: bool
    screen_reader: str

    def __post_init__(self):
        if type(self.schema) is not int or self.schema != SCHEMA:
            raise ActivationError("invalid decision schema")
        if type(self.outcome) is not str or self.outcome not in OUTCOMES:
            raise ActivationError("unknown activation outcome")
        _reason(self.reason)
        if type(self.action) is not str:
            raise ActivationError("invalid action token")
        if self.outcome == OFFER:
            if self.action not in ACTIONS:
                raise ActivationError("offer lacks a legal action")
        elif self.action:
            raise ActivationError("non-offer decision carries an action")
        if type(self.status) is not str:
            raise ActivationError("invalid pure negotiation status")
        if self.outcome in (OFFER, FALLBACK):
            if self.status not in STATUSES:
                raise ActivationError("action decision lacks a pure status")
        elif self.status:
            raise ActivationError("non-action decision carries a status")
        if type(self.kind) is not str or self.kind not in KINDS:
            raise ActivationError("unknown observation kind")
        _sequence(self.sequence)
        _source(self.source)
        if self.kind == OBSERVED:
            _state(self.observed_state)
        elif type(self.observed_state) is not str or self.observed_state:
            raise ActivationError("missing facts carries an observed state")
        _state(self.target_state)
        if self.outcome == DEFER and self.kind != NO_FACTS:
            raise ActivationError("deferred decision lacks missing facts")
        self._negative_claim("acceptance", self.acceptance,
                             ACCEPTANCE_NOT_ESTABLISHED)
        self._negative_claim("observation", self.observation,
                             OBSERVATION_NOT_PERFORMED)
        self._negative_claim("screen_reader", self.screen_reader,
                             SCREEN_READER_NOT_RUN)
        if type(self.wm_requests) is not int or self.wm_requests != WM_REQUESTS:
            raise ActivationError("WM requests must be zero")
        if type(self.polling) is not bool or self.polling is not POLLING_ENABLED:
            raise ActivationError("polling must be disabled")
        if (type(self.mint_acceptance_proven) is not bool
                or self.mint_acceptance_proven is not MINT_ACCEPTANCE_PROVEN):
            raise ActivationError("Mint acceptance must not be claimed")
        if (type(self.owner_visual_approval) is not bool
                or self.owner_visual_approval is not OWNER_VISUAL_APPROVAL):
            raise ActivationError("owner visual approval must not be claimed")

    @staticmethod
    def _negative_claim(label, value, expected):
        if type(value) is not str or value != expected:
            raise ActivationError("invalid " + label + " claim")

    def to_dict(self):
        """Fresh read-only view in the fixed shell-facing order."""
        return MappingProxyType({
            "schema": self.schema,
            "outcome": self.outcome,
            "action": self.action,
            "reason": self.reason,
            "status": self.status,
            "kind": self.kind,
            "sequence": self.sequence,
            "source": self.source,
            "observed_state": self.observed_state,
            "target_state": self.target_state,
            "acceptance": self.acceptance,
            "observation": self.observation,
            "wm_requests": self.wm_requests,
            "polling": self.polling,
            "mint_acceptance_proven": self.mint_acceptance_proven,
            "owner_visual_approval": self.owner_visual_approval,
            "screen_reader": self.screen_reader,
        })


class ActivationBoundary:
    """Single-thread, bounded intake and decision fold for activation facts."""

    def __init__(self, *, negotiation, target_state, max_pending=MAX_PENDING,
                 max_drain=MAX_DRAIN, history_limit=MAX_HISTORY,
                 overflow="reject_new", source=DEFAULT_SOURCE):
        if not isinstance(negotiation, Negotiation):
            raise ActivationError("negotiation must be a Negotiation")
        if (type(negotiation.backend) is not str or not negotiation.backend
                or type(negotiation.status) is not str
                or negotiation.status not in STATUSES
                or type(negotiation.granted) is not frozenset
                or any(not isinstance(feature, WindowStateFeature)
                       for feature in negotiation.granted)
                or (negotiation.status == "UNSUPPORTED") != (not negotiation.granted)):
            raise ActivationError("invalid negotiation record")
        for limit, value, ceiling in (
            ("pending bound", max_pending, MAX_PENDING),
            ("drain bound", max_drain, MAX_DRAIN),
            ("history bound", history_limit, MAX_HISTORY),
        ):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ActivationError("invalid " + limit)
        if type(overflow) is not str or overflow not in ("reject_new", "drop_oldest"):
            raise ActivationError("invalid overflow policy")
        self._negotiation = negotiation
        self._target_state = _state(target_state)
        self._max_pending = max_pending
        self._max_drain = max_drain
        self._overflow = overflow
        self._source = _source(source)
        self._queue = deque()
        self._last_sequence = 0
        self._rejection_count = 0
        self._last_rejection = None
        self._history = deque(maxlen=history_limit)
        self._history_cache = None
        self._closed = False

    def _ready(self):
        if self._closed:
            raise ActivationClosed("activation boundary is closed")

    def _reject(self, reason):
        self._rejection_count += 1
        self._last_rejection = reason
        raise ActivationError("activation event rejected: " + reason)

    @property
    def pending(self):
        return len(self._queue)

    @property
    def history(self):
        if self._history_cache is None:
            self._history_cache = tuple(self._history)
        return self._history_cache

    @property
    def rejection_count(self):
        return self._rejection_count

    @property
    def last_rejection(self):
        return self._last_rejection

    @property
    def closed(self):
        return self._closed

    @property
    def target_state(self):
        return self._target_state

    def ingest(self, event):
        """Validate one trusted delivered event into the bounded queue."""
        self._ready()
        try:
            observation = from_host_event(event, source=self._source)
        except ActivationError:
            self._reject("INVALID_EVENT")
        if observation.sequence <= self._last_sequence:
            self._reject("STALE_SEQUENCE")
        if len(self._queue) >= self._max_pending:
            if self._overflow == "drop_oldest":
                self._queue.popleft()
            else:
                self._reject("QUEUE_FULL")
        self._queue.append(observation)
        self._last_sequence = observation.sequence
        return observation.sequence

    def _decide(self, observation):
        if observation.kind == NO_FACTS:
            return ActivationDecision(
                schema=SCHEMA, outcome=DEFER, action="", reason="no_facts",
                status="", kind=observation.kind, sequence=observation.sequence,
                source=observation.source, observed_state="",
                target_state=self._target_state,
                acceptance=ACCEPTANCE_NOT_ESTABLISHED,
                observation=OBSERVATION_NOT_PERFORMED,
                wm_requests=WM_REQUESTS, polling=POLLING_ENABLED,
                mint_acceptance_proven=MINT_ACCEPTANCE_PROVEN,
                owner_visual_approval=OWNER_VISUAL_APPROVAL,
                screen_reader=SCREEN_READER_NOT_RUN,
            )
        observed = observation.state
        target = self._target_state
        action = ("" if observed == target
                  else _TRANSITION_ACTION.get((observed, target), ""))
        status = ""
        if observed == target:
            outcome, reason = REDUNDANT, "already_at_target"
        elif not action:
            outcome = REJECTED
            reason = ("ambiguous_prior_state"
                      if observed == WindowState.MAXIMIZED.value
                      and target == WindowState.MINIMIZED.value
                      else "no_direct_transition")
        else:
            status = self._negotiation.status
            allowed = self._negotiation.allows(_ACTION_ENUM[action])
            if allowed:
                outcome, reason = OFFER, "capability_granted"
            else:
                outcome, reason = FALLBACK, "capability_refused"
                # A refused capability offers no action at all.
                action = ""
        return ActivationDecision(
            schema=SCHEMA, outcome=outcome, action=action, reason=reason,
            status=status, kind=observation.kind, sequence=observation.sequence,
            source=observation.source, observed_state=observed,
            target_state=target,
            acceptance=ACCEPTANCE_NOT_ESTABLISHED,
            observation=OBSERVATION_NOT_PERFORMED,
            wm_requests=WM_REQUESTS, polling=POLLING_ENABLED,
            mint_acceptance_proven=MINT_ACCEPTANCE_PROVEN,
            owner_visual_approval=OWNER_VISUAL_APPROVAL,
            screen_reader=SCREEN_READER_NOT_RUN,
        )

    def drain(self, limit=None):
        """Fold at most ``limit`` queued observations into immutable decisions.

        Decisions are fully built before any queue record is removed, so a
        rejected context cannot lose events or publish a partial history.
        """
        self._ready()
        if limit is None:
            limit = self._max_drain
        if type(limit) is not int or not 1 <= limit <= self._max_drain:
            self._reject("INVALID_LIMIT")
        count = min(limit, len(self._queue))
        if not count:
            return ()
        ready = tuple(islice(self._queue, count))
        results = tuple(self._decide(observation) for observation in ready)
        for _ in range(count):
            self._queue.popleft()
        self._history.extend(results)
        self._history_cache = None
        return results

    def snapshot(self):
        """Read-only shell view with fixed negative claims and no callback."""
        self._ready()
        latest = self._history[-1] if self._history else None
        return MappingProxyType({
            "schema": SCHEMA,
            "outcome": latest.outcome if latest is not None else NO_DECISION,
            "action": latest.action if latest is not None else "",
            "reason": latest.reason if latest is not None else "",
            "status": latest.status if latest is not None else "",
            "sequence": latest.sequence if latest is not None else 0,
            "observed_state": latest.observed_state if latest is not None else "",
            "target_state": self._target_state,
            "pending": len(self._queue),
            "history_count": len(self._history),
            "rejection_count": self._rejection_count,
            "last_rejection": self._last_rejection or "",
            "wm_requests": WM_REQUESTS,
            "polling": POLLING_ENABLED,
            "acceptance": ACCEPTANCE_NOT_ESTABLISHED,
            "observation": OBSERVATION_NOT_PERFORMED,
            "mint_acceptance_proven": MINT_ACCEPTANCE_PROVEN,
            "owner_visual_approval": OWNER_VISUAL_APPROVAL,
            "screen_reader": SCREEN_READER_NOT_RUN,
        })

    def close(self):
        """Drop all queued facts, history and the negotiation reference."""
        if self._closed:
            return
        self._queue.clear()
        self._history.clear()
        self._history_cache = None
        self._negotiation = None
        self._closed = True
