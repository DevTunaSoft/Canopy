"""Bounded workspace behavior contracts at the existing host-event boundary.

A trusted host pushes already-delivered protocol-v2 ``window.state.changed``
events into a small queue; this module projects each event into a bounded
observation and folds it through the existing, unchanged
``workspace_state_contract`` decision layer. It is decision-only: no window
manager, compositor, Qt bridge, process, socket, filesystem, clock, thread,
timer or poll loop is used, and no callback or real operation is executed.

No host-event topic, payload field or protocol version is added. Only the
already-documented ``state``, ``window_count`` and ``source`` fields are read,
and an event carrying any other field is refused. Every produced decision
carries hardcoded negative claims: zero WM requests, polling disabled, no
acceptance established and no observation performed. This module is not a
Mint runtime, compiled-UI, accessibility or visual-approval claim.
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
from canopy_features.windows import workspace_state_contract as decisions
from canopy_features.windows.window_state_capabilities import Negotiation
from canopy_features.windows.workspace_inventory import WorkspaceInventory

__all__ = [
    "CAPABILITIES_TOPIC", "DEFER", "DEFAULT_SOURCE", "FALLBACK", "KINDS",
    "MAX_DRAIN", "MAX_HISTORY", "MAX_PENDING", "MAX_SEQUENCE",
    "NO_DECISION", "NO_FACTS", "OBSERVED", "OUTCOMES", "SCHEMA",
    "SWITCH_OFFER", "TOPICS", "WINDOW_EMPTY", "WINDOW_KEYS", "WINDOW_TOPIC",
    "WorkspaceBehaviorBoundary", "WorkspaceBehaviorClosed",
    "WorkspaceBehaviorDecision", "WorkspaceBehaviorError",
    "WorkspaceEventObservation", "from_host_event",
]

WINDOW_TOPIC = "window.state.changed"
TOPICS = frozenset({WINDOW_TOPIC})
if (PROTOCOL_VERSION != 2 or len(HOST_EVENT_TOPICS) != 4
        or not TOPICS.issubset(HOST_EVENT_TOPICS)):  # pragma: no cover
    raise RuntimeError("host event contract changed; workspace boundary must be reviewed")

SCHEMA = 1
DEFAULT_SOURCE = "host-events"
MAX_SEQUENCE = 1_000_000_000_000
MAX_PENDING = 16
MAX_DRAIN = 8
MAX_HISTORY = 16
MAX_WINDOW_COUNT = 1_000_000
MAX_SOURCE_BYTES = 64
MAX_ID_BYTES = 64

# Observation vocabulary: only facts a trusted host may publish on the
# existing window event topic.
OBSERVED = "observed"
NO_FACTS = "no_facts"
WINDOW_EMPTY = "windows_empty"
KINDS = frozenset({OBSERVED, NO_FACTS, WINDOW_EMPTY})

# Decision outcomes: an offer is never an executed switch.
SWITCH_OFFER = "switch_offer"
FALLBACK = "fallback"
DEFER = "defer"
NO_DECISION = "none"
OUTCOMES = frozenset({SWITCH_OFFER, FALLBACK, DEFER})

# Exact field allowlist. Existing host payloads carry other documented fields
# on this topic (for example pid/exit_code for crash reporting); those events
# belong to other consumers and must not be reinterpreted as workspace facts.
WINDOW_KEYS = frozenset({"state", "window_count", "source"})

_SOURCE = re.compile(r"[a-z0-9_.:-]{1,64}\Z")
_WORKSPACE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_MISSING = object()


class WorkspaceBehaviorError(ValueError):
    """Invalid event, context, bound or lifecycle check failed closed."""


class WorkspaceBehaviorClosed(RuntimeError):
    """No event or decision after explicit cleanup."""


def _bounded_text(value, limit, label, pattern=None):
    if type(value) is not str or not value:
        raise WorkspaceBehaviorError("invalid " + label)
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError:
        raise WorkspaceBehaviorError("invalid " + label) from None
    if size > limit:
        raise WorkspaceBehaviorError(label + " exceeds bound")
    if any(unicodedata.category(char) in _UNSAFE_CATEGORIES for char in value):
        raise WorkspaceBehaviorError("unsafe " + label)
    if pattern is not None and not pattern.fullmatch(value):
        raise WorkspaceBehaviorError("invalid " + label)
    return value


def _source(value):
    return _bounded_text(value, MAX_SOURCE_BYTES, "source", _SOURCE)


def _workspace_id(value):
    return _bounded_text(value, MAX_ID_BYTES, "workspace id", _WORKSPACE_ID)


def _workspace_count(value):
    # exact int: bool passes an isinstance check and would forge a count.
    if type(value) is not int or not 0 <= value <= MAX_WINDOW_COUNT:
        raise WorkspaceBehaviorError("invalid window count")
    return value


def _sequence(value):
    if type(value) is not int or not 1 <= value <= MAX_SEQUENCE:
        raise WorkspaceBehaviorError("invalid host event sequence")
    return value


def _fields(event):
    if type(event.fields) is not tuple:
        raise WorkspaceBehaviorError("host event fields must be a tuple")
    keys = []
    for field in event.fields:
        if (type(field) is not tuple or len(field) != 2
                or type(field[0]) is not str):
            raise WorkspaceBehaviorError("malformed host event field")
        if field[0] in keys:
            raise WorkspaceBehaviorError("duplicate host event field")
        keys.append(field[0])
    if not set(keys).issubset(WINDOW_KEYS):
        raise WorkspaceBehaviorError("unsupported workspace event field")
    return event.payload


@dataclass(frozen=True)
class WorkspaceEventObservation:
    """One bounded fact projected from an existing v2 host event."""

    kind: str
    sequence: int
    target: str
    window_count: int
    source: str

    def __post_init__(self):
        if type(self.kind) is not str or self.kind not in KINDS:
            raise WorkspaceBehaviorError("unknown observation kind")
        _sequence(self.sequence)
        _source(self.source)
        _workspace_count(self.window_count)
        if self.target:
            _workspace_id(self.target)
        if self.kind == OBSERVED and not self.target:
            raise WorkspaceBehaviorError("observed kind needs a workspace target")
        if self.kind != OBSERVED and self.target:
            raise WorkspaceBehaviorError("non-observed kind carries a target")

    def to_dict(self):
        """Fresh read-only projection in fixed order."""
        return MappingProxyType({
            "kind": self.kind,
            "sequence": self.sequence,
            "target": self.target,
            "window_count": self.window_count,
            "source": self.source,
        })


@dataclass(frozen=True)
class WorkspaceBehaviorDecision:
    """Immutable, decision-only result; every real-world claim is negative."""

    schema: int
    outcome: str
    reason: str
    status: str
    kind: str
    sequence: int
    source: str
    active: str
    target: str
    window_count: int
    acceptance: str
    observation: str
    wm_requests: int
    polling: bool

    def __post_init__(self):
        if self.schema != SCHEMA:
            raise WorkspaceBehaviorError("invalid decision schema")
        if type(self.outcome) is not str or self.outcome not in OUTCOMES:
            raise WorkspaceBehaviorError("unknown behavior outcome")
        if type(self.reason) is not str or not self.reason:
            raise WorkspaceBehaviorError("invalid decision reason")
        if type(self.status) is not str or (self.status and
                                            self.status not in (
                                                decisions.STATUS_NATIVE,
                                                decisions.STATUS_FALLBACK)):
            raise WorkspaceBehaviorError("invalid decision status")
        if type(self.kind) is not str or self.kind not in KINDS:
            raise WorkspaceBehaviorError("invalid observation kind")
        _sequence(self.sequence)
        _source(self.source)
        _workspace_id(self.active)
        if self.target:
            _workspace_id(self.target)
        _workspace_count(self.window_count)
        self._negative_claim("acceptance", self.acceptance,
                             decisions.ACCEPTANCE_NOT_ESTABLISHED)
        self._negative_claim("observation", self.observation,
                             decisions.OBSERVATION_NOT_PERFORMED)
        if type(self.wm_requests) is not int or self.wm_requests != 0:
            raise WorkspaceBehaviorError("WM requests must be zero")
        if type(self.polling) is not bool or self.polling:
            raise WorkspaceBehaviorError("polling must be disabled")
        if self.outcome == DEFER and self.status:
            raise WorkspaceBehaviorError("deferred decision carries a switch status")
        if self.outcome in (SWITCH_OFFER, FALLBACK) and not self.status:
            raise WorkspaceBehaviorError("switch decision lacks a pure status")

    @staticmethod
    def _negative_claim(label, value, expected):
        if type(value) is not str or value != expected:
            raise WorkspaceBehaviorError("invalid " + label + " claim")

    def to_dict(self):
        """Fresh read-only view in the fixed shell-facing order."""
        return MappingProxyType({
            "schema": self.schema,
            "outcome": self.outcome,
            "reason": self.reason,
            "status": self.status,
            "kind": self.kind,
            "sequence": self.sequence,
            "source": self.source,
            "active": self.active,
            "target": self.target,
            "window_count": self.window_count,
            "acceptance": self.acceptance,
            "observation": self.observation,
            "wm_requests": self.wm_requests,
            "polling": self.polling,
        })


def from_host_event(event, *, source=DEFAULT_SOURCE):
    """Project one delivered v2 window event into a bounded observation.

    No other host topic, field or protocol version is accepted. Missing facts
    are explicitly reported as ``no_facts``; malformed or contradictory facts
    raise ``WorkspaceBehaviorError`` instead of inventing a workspace target.
    """
    if type(event) is not HostEvent:
        raise WorkspaceBehaviorError("workspace fact requires a delivered HostEvent")
    if event.version != PROTOCOL_VERSION:
        raise WorkspaceBehaviorError("unsupported host event protocol version")
    if type(event.topic) is not str or event.topic not in TOPICS:
        raise WorkspaceBehaviorError("unsupported workspace event topic")
    sequence = _sequence(event.sequence)
    source = _source(source)
    payload = _fields(event)
    if not isinstance(payload, Mapping):
        raise WorkspaceBehaviorError("host event payload must be a mapping")

    supplied = payload.get("source", _MISSING)
    if supplied is not _MISSING and supplied != source:
        raise WorkspaceBehaviorError("contradictory workspace event provenance")

    state = payload.get("state", _MISSING)
    count = payload.get("window_count", _MISSING)
    target = _workspace_id(state) if state is not _MISSING else ""
    windows = _workspace_count(count) if count is not _MISSING else 0
    if target and windows == 0:
        raise WorkspaceBehaviorError("workspace target contradicts empty window count")
    if target:
        kind = OBSERVED
    elif count is _MISSING:
        kind = NO_FACTS
    elif windows == 0:
        kind = WINDOW_EMPTY
    else:
        kind = NO_FACTS
    return WorkspaceEventObservation(kind, sequence, target, windows, source)


class WorkspaceBehaviorBoundary:
    """Single-thread, bounded intake and decision fold for workspace events."""

    def __init__(self, *, workspace, active, negotiation, capabilities,
                 max_pending=MAX_PENDING, max_drain=MAX_DRAIN,
                 history_limit=MAX_HISTORY, overflow="reject_new",
                 source=DEFAULT_SOURCE):
        if not isinstance(workspace, WorkspaceInventory) or type(workspace.workspaces) is not tuple:
            raise WorkspaceBehaviorError("workspace must be a WorkspaceInventory")
        active = _workspace_id(active)
        if not isinstance(negotiation, Negotiation):
            raise WorkspaceBehaviorError("negotiation must be a Negotiation")
        if (type(negotiation.backend) is not str or not negotiation.backend
                or type(negotiation.status) is not str
                or negotiation.status not in ("SUPPORTED", "PARTIAL", "UNSUPPORTED")
                or type(negotiation.granted) is not frozenset):
            raise WorkspaceBehaviorError("invalid negotiation record")
        if type(capabilities) is not frozenset or not capabilities.issubset(
                decisions.CAPABILITIES):
            raise WorkspaceBehaviorError("invalid workspace capability set")
        for limit, value, ceiling in (
            ("pending bound", max_pending, MAX_PENDING),
            ("drain bound", max_drain, MAX_DRAIN),
            ("history bound", history_limit, MAX_HISTORY),
        ):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise WorkspaceBehaviorError("invalid " + limit)
        if type(overflow) is not str or overflow not in ("reject_new", "drop_oldest"):
            raise WorkspaceBehaviorError("invalid overflow policy")
        source = _source(source)
        self._workspace = workspace
        self._active = active
        self._negotiation = negotiation
        self._capabilities = capabilities
        self._max_pending = max_pending
        self._max_drain = max_drain
        self._overflow = overflow
        self._source = source
        self._queue = deque()
        self._last_sequence = 0
        self._rejection_count = 0
        self._last_rejection = None
        self._history = deque(maxlen=history_limit)
        self._history_cache = None
        self._closed = False

    def _ready(self):
        if self._closed:
            raise WorkspaceBehaviorClosed("workspace behavior boundary is closed")

    def _reject(self, reason):
        self._rejection_count += 1
        self._last_rejection = reason
        raise WorkspaceBehaviorError("workspace event rejected: " + reason)

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

    def ingest(self, event):
        """Validate one trusted event into the bounded queue; return sequence."""
        self._ready()
        try:
            observation = from_host_event(event, source=self._source)
        except WorkspaceBehaviorError:
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
        kind = observation.kind
        if kind in (NO_FACTS, WINDOW_EMPTY):
            status = ""
            if kind == NO_FACTS:
                outcome, reason = DEFER, NO_FACTS
            else:
                outcome, reason = DEFER, WINDOW_EMPTY
        else:
            try:
                pure = decisions.decide(
                    self._workspace, self._active, observation.target,
                    negotiation=self._negotiation,
                    capabilities=self._capabilities,
                )
            except decisions.WorkspaceContractError as exc:
                raise WorkspaceBehaviorError("workspace context rejected") from exc
            status = pure.status
            outcome = SWITCH_OFFER if pure.native_allowed else FALLBACK
            reason = pure.reason
        return WorkspaceBehaviorDecision(
            schema=SCHEMA,
            outcome=outcome,
            reason=reason,
            status=status,
            kind=kind,
            sequence=observation.sequence,
            source=observation.source,
            active=self._active,
            target=observation.target,
            window_count=observation.window_count,
            acceptance=decisions.ACCEPTANCE_NOT_ESTABLISHED,
            observation=decisions.OBSERVATION_NOT_PERFORMED,
            wm_requests=decisions.WM_REQUESTS,
            polling=decisions.POLLING_ENABLED,
        )

    def drain(self, limit=None):
        """Fold at most ``limit`` queued observations into immutable decisions.

        Decisions are fully built before any record is removed, so a rejected
        context cannot lose queued events or publish a partial history.
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
            "status": latest.status if latest is not None else "",
            "sequence": latest.sequence if latest is not None else 0,
            "pending": len(self._queue),
            "history_count": len(self._history),
            "rejection_count": self._rejection_count,
            "last_rejection": self._last_rejection or "",
            "wm_requests": 0,
            "polling": False,
            "acceptance": decisions.ACCEPTANCE_NOT_ESTABLISHED,
            "observation": decisions.OBSERVATION_NOT_PERFORMED,
            "mint_acceptance_proven": False,
            "owner_visual_approval": False,
        })

    def close(self):
        """Drop queued facts, history and context; later calls fail closed."""
        if self._closed:
            return
        self._queue.clear()
        self._history.clear()
        self._history_cache = None
        self._workspace = None
        self._negotiation = None
        self._capabilities = frozenset()
        self._last_sequence = 0
        self._last_rejection = None
        self._closed = True
