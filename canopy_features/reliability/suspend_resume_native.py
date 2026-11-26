"""Bounded native host-event path for fail-closed suspend/resume availability.

This is the host-boundary adapter *beyond* the pure decision layer in
``canopy_features.reliability.suspend_resume_contracts``. A trusted host pushes
already-delivered ``canopy_core.host_events.HostEvent`` values (or an existing
reconciled ``SessionState``) into a bounded intake queue; this module drains
them through the unchanged pure decision layer and exposes a read-only,
fail-closed availability decision. It performs **no** real suspend or resume,
no D-Bus, no process/window action, no filesystem or network I/O, and starts no
thread, timer or poll loop.

Fail-closed invariants:

* Nothing is available until a confirmed ``active`` observation is drained and
  any pending re-observation is acknowledged. The default state is
  ``UNAVAILABLE`` with reason ``unknown-host-state``.
* Losing trust in the event boundary (explicit host-unavailable signal, intake
  overflow, or close) clears the intake and degrades the folded decision to an
  unknown snapshot. A rejected or dropped event can never leave a stale
  ``active`` phase in place. Recovery requires a fresh confirmed observation
  and an explicit re-observation acknowledgment.
* Every intake, drain and batch is bounded by construction. ``submit_many``
  consumes at most ``max_batch`` items, so an endless iterator cannot pin the
  host callback. Every public entry point translates hostile caller types into
  this module's domain error; no payload string is ever rendered or logged.

Existing contracts reused (nothing new is invented): protocol v2
``HostEvent`` and the ``session.state.changed`` topic from
``canopy_core.host_events``, the reconciled ``SessionState`` from
``lock_session_events``, and the immutable decision records from
``suspend_resume_contracts``. No protocol version, topic or payload field is
added.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import islice
from types import MappingProxyType

from canopy_core.host_events import PROTOCOL_VERSION, HostEvent, HostEventError
from canopy_features.reliability import suspend_resume_contracts as _decisions
from canopy_features.reliability.lock_session_events import SessionState

__all__ = [
    "MAX_PENDING", "MAX_DRAIN", "MAX_BATCH", "MAX_HISTORY",
    "QUEUED", "DROPPED_OLDEST", "REJECTED", "OVERFLOW_POLICIES",
    "REASON_HOST_UNAVAILABLE", "REASON_CLOSED", "REASON_RESUME_PENDING",
    "REASON_INVALID_OPERATION", "AVAILABLE", "UNAVAILABLE", "OPERATIONS",
    "DISCLOSURES", "SuspendResumeNativeError", "NativeDecision",
    "IntakeResult", "BatchResult", "DrainReport", "SuspendResumeNativePath",
]

# Bounds are hard ceilings: a caller may lower them, never raise them.
MAX_PENDING = 32
MAX_DRAIN = 16
MAX_BATCH = MAX_PENDING
MAX_HISTORY = 32

QUEUED = "queued"
DROPPED_OLDEST = "dropped_oldest"
REJECTED = "rejected"
OVERFLOW_POLICIES = frozenset({QUEUED, DROPPED_OLDEST, REJECTED})

# Overflow policies select what happens to the newest event when the intake
# queue is full. Both are fail-closed: either way the boundary is marked
# unavailable, because an unqueued state observation cannot be trusted.
POLICIES = frozenset({"reject_new", "drop_oldest"})

REASON_HOST_UNAVAILABLE = "host-boundary-unavailable"
REASON_CLOSED = "native-path-closed"
REASON_RESUME_PENDING = _decisions.REASON_RESUME_PENDING
REASON_INVALID_OPERATION = _decisions.REASON_INVALID_OPERATION

AVAILABLE = _decisions.AVAILABLE
UNAVAILABLE = _decisions.UNAVAILABLE
OPERATIONS = _decisions.OPERATIONS

# Stable, caller-independent disclosures. No observed payload value is ever
# interpolated into these strings.
DISCLOSURES = MappingProxyType({
    **dict(_decisions.DISCLOSURES),
    REASON_HOST_UNAVAILABLE: "Unavailable — host event boundary unavailable",
    REASON_CLOSED: "Unavailable — native path closed",
})


class SuspendResumeNativeError(HostEventError):
    """Invalid caller input, wrong event type/topic or misuse of the path."""


@dataclass(frozen=True)
class NativeDecision:
    """Whether a presentation may *offer* an operation, and why.

    The native path emits its own record so its extra fail-closed reasons stay
    disclosable without mutating the pure decision layer.
    """

    available: bool
    reason: str

    def __post_init__(self):
        if type(self.available) is not bool or type(self.reason) is not str \
                or self.reason not in DISCLOSURES:
            raise SuspendResumeNativeError("invalid native decision")

    @property
    def disclosure(self):
        return DISCLOSURES[self.reason]

    def to_dict(self):
        return {
            "available": self.available,
            "reason": self.reason,
            "disclosure": self.disclosure,
        }


@dataclass(frozen=True)
class IntakeResult:
    """Outcome of one ``submit`` call."""

    accepted: bool
    status: str
    sequence: int

    def __post_init__(self):
        if (type(self.accepted) is not bool or type(self.status) is not str
                or self.status not in (QUEUED, DROPPED_OLDEST, REJECTED)
                or type(self.sequence) is not int or self.sequence < 0):
            raise SuspendResumeNativeError("invalid intake result")


@dataclass(frozen=True)
class BatchResult:
    """Bounded accounting for one ``submit_many`` call."""

    consumed: int
    queued: int
    rejected: int
    stopped: bool

    def __post_init__(self):
        for name in ("consumed", "queued", "rejected"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise SuspendResumeNativeError("invalid batch count")
        if type(self.stopped) is not bool or self.queued + self.rejected != self.consumed:
            raise SuspendResumeNativeError("inconsistent batch accounting")


@dataclass(frozen=True)
class DrainReport:
    """Bounded accounting for one ``drain`` call."""

    processed: int
    ignored: int
    pending: int
    phase: str
    availability: str

    def __post_init__(self):
        for name in ("processed", "ignored", "pending"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise SuspendResumeNativeError("invalid drain count")
        if type(self.phase) is not str or type(self.availability) is not str \
                or self.availability not in (AVAILABLE, UNAVAILABLE):
            raise SuspendResumeNativeError("invalid drain report")


def _deny(reason):
    return NativeDecision(False, reason)


class SuspendResumeNativePath:
    """Bounded, immutable-decision host boundary for suspend/resume.

    Every observation is folded into a new pure ``SuspendResumeContracts``
    snapshot. This object never mutates a published snapshot, never executes
    an operation and never reaches outside the caller-supplied event stream.
    """

    def __init__(self, *, max_pending=MAX_PENDING, max_drain=MAX_DRAIN,
                 overflow_policy="reject_new"):
        if (type(max_pending) is not int
                or not 1 <= max_pending <= MAX_PENDING):
            raise SuspendResumeNativeError("invalid pending bound")
        if (type(max_drain) is not int or not 1 <= max_drain <= MAX_DRAIN):
            raise SuspendResumeNativeError("invalid drain bound")
        if (type(overflow_policy) is not str
                or overflow_policy not in POLICIES):
            raise SuspendResumeNativeError("unsupported overflow policy")
        self._max_pending = max_pending
        self._max_drain = max_drain
        self._max_batch = max_pending
        self._overflow_policy = overflow_policy
        self._pending = deque()
        self._decisions = _decisions.empty()
        self._boundary_ok = True
        self._closed = False
        self._reobservation_required = False
        self._history = deque(maxlen=MAX_HISTORY)
        self._counts = dict(submitted=0, accepted=0, rejected=0, dropped=0,
                            drained=0, ignored=0, boundary_losses=0,
                            session_observations=0, reobservations=0)

    # -- caller guards ---------------------------------------------------
    def _mutable(self):
        if self._closed:
            raise SuspendResumeNativeError("native path is closed")
        if not self._boundary_ok:
            raise SuspendResumeNativeError("host event boundary is unavailable")

    @staticmethod
    def _check_event(event):
        # Exact type: a forged subclass cannot override ``payload`` and smuggle
        # an unvalidated state into the pure decision layer.
        if type(event) is not HostEvent:
            raise SuspendResumeNativeError("observation requires a HostEvent")
        if event.topic != _decisions.SESSION_TOPIC:
            raise SuspendResumeNativeError("unsupported host event topic")
        if event.version != PROTOCOL_VERSION:
            raise SuspendResumeNativeError("unsupported host event version")
        if type(event.sequence) is not int or event.sequence < 0:
            raise SuspendResumeNativeError("invalid host event sequence")

    # -- boundary trust --------------------------------------------------
    def _lose_boundary(self, marker):
        """Fail closed: drop queued events and forget any active phase."""
        if self._boundary_ok:
            self._counts["boundary_losses"] += 1
            self._history.append(marker)
        self._boundary_ok = False
        self._reobservation_required = True
        self._pending.clear()
        # Keep sequence monotonic after the reset: a late event from before
        # the loss cannot resurrect the old phase.
        self._decisions = _decisions.SuspendResumeContracts(
            sequence=self._decisions.sequence)

    def mark_host_unavailable(self):
        """Trusted signal that the host event stream can no longer be trusted."""
        if self._closed:
            raise SuspendResumeNativeError("native path is closed")
        self._lose_boundary("host-unavailable")

    def mark_host_available(self):
        """Reopen intake only; availability stays denied until re-observed."""
        if self._closed:
            raise SuspendResumeNativeError("native path is closed")
        if self._boundary_ok:
            return False
        self._boundary_ok = True
        return True

    def close(self):
        """Irreversible fail-closed cleanup of all queued and folded state."""
        if self._closed:
            return
        self._lose_boundary("closed")
        self._closed = True

    # -- intake ----------------------------------------------------------
    def submit(self, event):
        """Queue one validated host event, with a bounded overflow fallback."""
        self._mutable()
        self._check_event(event)
        self._counts["submitted"] += 1
        if len(self._pending) < self._max_pending:
            self._pending.append(event)
            self._counts["accepted"] += 1
            return IntakeResult(True, QUEUED, event.sequence)
        if self._overflow_policy == "reject_new":
            self._counts["rejected"] += 1
            self._lose_boundary("intake-overflow")
            return IntakeResult(False, REJECTED, event.sequence)
        self._pending.popleft()
        self._counts["accepted"] += 1
        self._counts["dropped"] += 1
        self._lose_boundary("intake-overflow")
        return IntakeResult(True, DROPPED_OLDEST, event.sequence)

    def submit_many(self, events):
        """Consume at most ``max_pending`` items from a caller iterable.

        ``itertools.islice`` bounds consumption before any item is read, so an
        endless generator cannot pin the host callback. Scalar/mapping inputs
        are rejected with the domain error instead of a raw ``TypeError``.
        """
        self._mutable()
        if (isinstance(events, (str, bytes, bytearray, Mapping))
                or not isinstance(events, Iterable)):
            raise SuspendResumeNativeError("event batch must be an iterable")
        consumed = queued = 0
        stopped = False
        for event in islice(events, self._max_batch):
            consumed += 1
            try:
                result = self.submit(event)
            except SuspendResumeNativeError:
                # A boundary loss mid-batch is a stop, not a caller error that
                # should discard the accounting gathered so far.
                stopped = True
                break
            if result.accepted:
                queued += 1
        return BatchResult(consumed, queued, consumed - queued, stopped)

    def observe_session_state(self, state):
        """Fold an existing reconciled ``SessionState`` directly.

        Exact type gate: a forged subclass cannot supply a trusted label.
        """
        self._mutable()
        if type(state) is not SessionState:
            raise SuspendResumeNativeError("session observation requires SessionState")
        self._decisions = self._decisions.from_session_state(state)
        self._counts["session_observations"] += 1
        return self._decisions

    # -- folding ---------------------------------------------------------
    def drain(self, limit=None):
        """Fold at most ``limit`` queued events through the pure decision layer."""
        self._mutable()
        if limit is None:
            limit = self._max_drain
        if type(limit) is not int or not 1 <= limit <= MAX_DRAIN:
            raise SuspendResumeNativeError("invalid drain limit")
        processed = ignored = 0
        for _ in range(min(limit, len(self._pending))):
            event = self._pending.popleft()
            before = self._decisions
            try:
                self._decisions = before.observe(event)
            except _decisions.SuspendResumeError:
                self._lose_boundary("invalid-event-at-drain")
                break
            if (self._decisions.sequence == before.sequence
                    and self._decisions.phase == before.phase):
                ignored += 1
            else:
                processed += 1
        self._counts["drained"] += processed
        self._counts["ignored"] += ignored
        return DrainReport(processed, ignored, len(self._pending),
                           self._decisions.phase, self.availability)

    def resume_ready(self):
        """Acknowledge a re-observed desktop; never driven by an event alone."""
        self._mutable()
        if self._decisions.phase == _decisions.PHASE_RESUME_PENDING:
            self._decisions = self._decisions.resume_ready()
            self._reobservation_required = False
            self._counts["reobservations"] += 1
            return self._decisions
        if (self._reobservation_required
                and self._decisions.phase == _decisions.PHASE_ACTIVE):
            # A fresh confirmed-active observation arrived after a boundary
            # loss; the trusted caller now acknowledges re-observation.
            self._reobservation_required = False
            self._counts["reobservations"] += 1
            return self._decisions
        raise SuspendResumeNativeError("no observed resume awaiting re-observation")

    # -- decisions -------------------------------------------------------
    @property
    def availability(self):
        if self._closed or not self._boundary_ok or self._reobservation_required:
            return UNAVAILABLE
        return self._decisions.availability

    @property
    def reason(self):
        if self._closed:
            return REASON_CLOSED
        if not self._boundary_ok:
            return REASON_HOST_UNAVAILABLE
        if self._reobservation_required:
            return REASON_RESUME_PENDING
        return self._decisions.decide("read_status").reason

    @property
    def disclosure(self):
        return DISCLOSURES[self.reason]

    def decide(self, operation):
        """Fail-closed availability decision; this never executes anything."""
        if self._closed:
            return _deny(REASON_CLOSED)
        if not self._boundary_ok:
            return _deny(REASON_HOST_UNAVAILABLE)
        if self._reobservation_required:
            return _deny(REASON_RESUME_PENDING)
        decision = self._decisions.decide(operation)
        return NativeDecision(decision.available, decision.reason)

    @property
    def stats(self):
        return MappingProxyType(dict(self._counts))

    def view(self):
        """Read-only, deterministic projection with fixed key order."""
        return MappingProxyType({
            "boundary": "available" if self._boundary_ok else "unavailable",
            "closed": self._closed,
            "reobservation_required": self._reobservation_required,
            "pending": len(self._pending),
            "overflow_policy": self._overflow_policy,
            "phase": self._decisions.phase,
            "availability": self.availability,
            "reason": self.reason,
            "disclosure": self.disclosure,
            "history": tuple(self._history),
            "counts": MappingProxyType(dict(self._counts)),
        })

    def to_dict(self):
        snapshot = self.view()
        return {key: (dict(value) if isinstance(value, Mapping) else value)
                for key, value in snapshot.items()}
