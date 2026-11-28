"""Bounded native host-event path for logout/shutdown session controls.

This module is the host-boundary adapter *beyond* the pure, fail-closed
decision layer in :mod:`canopy_features.system.session_controls`. A trusted
host pushes already-delivered protocol-v2 ``HostEvent`` values (or an existing
reconciled ``SessionState``) into a bounded intake queue; this module drains
them, keeps a fail-closed session view, and folds that view into the unchanged
session-control decision. It performs **no** logout, reboot, shutdown, process
spawn, D-Bus call, credential read, filesystem or network I/O. It starts no
thread, timer, poll loop or subscription and never emits an event.

Fail-closed invariants:

* Nothing is offerable until a fresh ``active`` session observation has been
  drained and any owed re-observation has been explicitly acknowledged. The
  initial view is ``unknown`` with reason ``no-host-observation``.
* Losing trust in the event boundary (explicit host-unavailable signal, an
  invalid observation, intake overflow or close) clears the queue and degrades
  the folded view to ``unknown``. A rejected or dropped event cannot leave a
  stale ``active`` phase in place, and the observed sequence stays monotonic
  so a late event cannot resurrect the old view.
* Every intake, drain and batch is bounded by construction. ``submit_many``
  consumes at most ``max_batch`` items, so a hostile iterator cannot pin the
  host callback. All public entry points translate hostile caller types into
  this module's domain error; no payload string is interpolated into a
  disclosure, log line or snapshot.

Existing contracts are reused, never extended: protocol v2 ``HostEvent`` and
the ``session.state.changed`` topic from ``canopy_core.host_events``, the
``state`` token vocabulary and reason codes from
``canopy_features.system.quick_controls_state``, and the immutable decision
records and raw-command refusal from
``canopy_features.system.session_controls``. No protocol version, topic or
payload field is added here.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import islice
from types import MappingProxyType

from canopy_core.host_events import PROTOCOL_VERSION, HostEvent, HostEventError
from canopy_features.system import quick_controls_state as _qcs
from canopy_features.system import session_controls as _controls

__all__ = [
    "MAX_PENDING", "MAX_DRAIN", "MAX_BATCH", "MAX_HISTORY",
    "QUEUED", "DROPPED_OLDEST", "REJECTED", "OVERFLOW_POLICIES",
    "SESSION_STATUS", "STATUS_ACTIVE",
    "REASON_OK", "REASON_NO_HOST_OBSERVATION", "REASON_HOST_UNAVAILABLE",
    "REASON_CLOSED", "REASON_REOBSERVATION", "REASON_SESSION_NOT_ACTIVE",
    "REASON_INVALID_ACTION", "REASON_INVALID_GRANT", "REASON_UNCONFIRMED",
    "REASON_BRIDGE_DISABLED", "REASON_NO_HOST_INTERFACE",
    "REASON_RAW_COMMAND_REFUSED", "DISCLOSURES", "NO_COMMAND",
    "AVAILABLE", "UNAVAILABLE", "SESSION_EXECUTION_NOT_RUN",
    "PROTOCOL_VERSION", "SESSION_TOPIC",
    "SessionControlsNativeError", "NativeDecision", "IntakeResult",
    "BatchResult", "DrainReport", "SessionControlsNativePath",
]

# Hard ceilings: callers may lower them, never raise them.
MAX_PENDING = 32
MAX_DRAIN = 16
MAX_BATCH = MAX_PENDING
MAX_HISTORY = 32

QUEUED = "queued"
DROPPED_OLDEST = "dropped_oldest"
REJECTED = "rejected"
OVERFLOW_POLICIES = frozenset({"reject_new", "drop_oldest"})

SESSION_TOPIC = _controls.SESSION_TOPIC
SESSION_STATUS = frozenset(_qcs.STATUS_TOKENS["session"])
STATUS_ACTIVE = "active"
STATUS_UNKNOWN = "unknown"
_PRIVILEGED_STATUSES = frozenset({"locked", "suspended"})

AVAILABLE = _qcs.AVAILABLE
UNAVAILABLE = _qcs.UNAVAILABLE
# This path only decides; a privileged session change is never executed here.
SESSION_EXECUTION_NOT_RUN = _qcs.EXECUTION_NOT_RUN
NO_COMMAND = _controls.NO_COMMAND

REASON_OK = _controls.REASON_OK
REASON_NO_HOST_OBSERVATION = _qcs.REASON_NO_HOST_OBSERVATION
REASON_HOST_UNAVAILABLE = "host-boundary-unavailable"
REASON_CLOSED = "native-path-closed"
REASON_REOBSERVATION = "session-needs-reobservation"
REASON_SESSION_NOT_ACTIVE = "session-not-active"
REASON_INVALID_ACTION = _controls.REASON_INVALID_ACTION
REASON_INVALID_GRANT = _controls.REASON_INVALID_GRANT
REASON_UNCONFIRMED = _controls.REASON_UNCONFIRMED
REASON_BRIDGE_DISABLED = _controls.REASON_BRIDGE_DISABLED
REASON_NO_HOST_INTERFACE = _controls.REASON_NO_HOST_INTERFACE
REASON_RAW_COMMAND_REFUSED = _controls.REASON_RAW_COMMAND_REFUSED

# Stable, caller-independent disclosures. A hostile observed value is never
# rendered into these strings.
DISCLOSURES = MappingProxyType({
    **dict(_controls.DISCLOSURES),
    REASON_NO_HOST_OBSERVATION: _qcs.DISCLOSURES[_qcs.REASON_NO_HOST_OBSERVATION],
    REASON_HOST_UNAVAILABLE: "Unavailable — host event boundary unavailable",
    REASON_CLOSED: "Unavailable — native path closed",
    REASON_REOBSERVATION: "Unavailable — session needs re-observation",
    REASON_SESSION_NOT_ACTIVE: "Unavailable — session is not active",
})


class SessionControlsNativeError(HostEventError):
    """Invalid caller input, wrong event type, or misuse of the native path."""


@dataclass(frozen=True)
class NativeDecision:
    """Whether a presentation may *offer* a privileged action, and why.

    It emits its own record so the extra fail-closed reasons stay disclosable
    without mutating the pure decision layer. ``allowed`` is never execution.
    """

    allowed: bool
    reason: str
    action: str = ""
    interface: str = ""
    path: object = None

    def __post_init__(self):
        if type(self.allowed) is not bool or type(self.reason) is not str \
                or self.reason not in DISCLOSURES:
            raise SessionControlsNativeError("invalid native decision")
        if type(self.action) is not str or (
                self.action and self.action not in _controls.ACTIONS):
            raise SessionControlsNativeError("invalid decision action")
        if type(self.interface) is not str or (
                self.interface and self.interface not in _controls.NATIVE_INTERFACES):
            raise SessionControlsNativeError("invalid decision interface")
        if self.path is not None and type(self.path) is not _controls.NativePath:
            raise SessionControlsNativeError("invalid decision path")
        if self.allowed != (self.path is not None):
            raise SessionControlsNativeError("decision and path disagree")

    @property
    def disclosure(self):
        return DISCLOSURES[self.reason]

    @property
    def execution_label(self):
        """Truthful label: every decision here stays NOT_RUN by this module."""
        return SESSION_EXECUTION_NOT_RUN

    def to_dict(self):
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "disclosure": self.disclosure,
            "action": self.action,
            "interface": self.interface,
            "path": self.path.to_dict() if self.path is not None else None,
            "execution": "host-only-not-performed" if self.allowed
                         else "not-performed",
            "execution_label": self.execution_label,
            "executed": False,
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
            raise SessionControlsNativeError("invalid intake result")


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
                raise SessionControlsNativeError("invalid batch count")
        if type(self.stopped) is not bool or self.queued + self.rejected != self.consumed:
            raise SessionControlsNativeError("inconsistent batch accounting")


@dataclass(frozen=True)
class DrainReport:
    """Bounded accounting for one ``drain`` call."""

    processed: int
    ignored: int
    pending: int
    status: str
    availability: str
    reason: str

    def __post_init__(self):
        for name in ("processed", "ignored", "pending"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise SessionControlsNativeError("invalid drain count")
        if (type(self.status) is not str or self.status not in SESSION_STATUS
                or type(self.availability) is not str
                or self.availability not in (AVAILABLE, UNAVAILABLE)
                or type(self.reason) is not str or self.reason not in DISCLOSURES):
            raise SessionControlsNativeError("invalid drain report")


def _deny(reason, action="", interface=""):
    return NativeDecision(False, reason, action, interface)


class SessionControlsNativePath:
    """Bounded, immutable-decision host boundary for privileged session actions.

    Callers may submit events and drain them; this object never looks for work
    on its own, never executes an action and never reaches outside the
    caller-supplied event stream.
    """

    def __init__(self, *, max_pending=MAX_PENDING, max_drain=MAX_DRAIN,
                 overflow_policy="reject_new"):
        if type(max_pending) is not int or not 1 <= max_pending <= MAX_PENDING:
            raise SessionControlsNativeError("invalid pending bound")
        if type(max_drain) is not int or not 1 <= max_drain <= MAX_DRAIN:
            raise SessionControlsNativeError("invalid drain bound")
        if type(overflow_policy) is not str or overflow_policy not in OVERFLOW_POLICIES:
            raise SessionControlsNativeError("unsupported overflow policy")
        self._max_pending = max_pending
        self._max_drain = max_drain
        self._max_batch = max_pending
        self._overflow_policy = overflow_policy
        self._pending = deque()
        self._status = STATUS_UNKNOWN
        self._sequence = None
        self._boundary_ok = True
        self._closed = False
        self._reobservation_required = False
        self._history = deque(maxlen=MAX_HISTORY)
        self._counts = dict(
            submitted=0, accepted=0, rejected=0, dropped=0, drained=0,
            ignored=0, boundary_losses=0, observations=0, stale=0,
            reobservations=0,
        )

    # -- caller guards ---------------------------------------------------
    def _mutable(self):
        if self._closed:
            raise SessionControlsNativeError("native path is closed")
        if not self._boundary_ok:
            raise SessionControlsNativeError("host event boundary is unavailable")

    @staticmethod
    def _check_event(event):
        # Exact type: a forged subclass cannot override ``payload`` and smuggle
        # an unvalidated status into the folded session view.
        if type(event) is not HostEvent:
            raise SessionControlsNativeError("observation requires a HostEvent")
        if event.topic != SESSION_TOPIC:
            raise SessionControlsNativeError("unsupported host event topic")
        if event.version != PROTOCOL_VERSION:
            raise SessionControlsNativeError("unsupported host event version")
        if type(event.sequence) is not int or event.sequence < 0:
            raise SessionControlsNativeError("invalid host event sequence")

    # -- boundary trust --------------------------------------------------
    def _lose_boundary(self, marker):
        """Fail closed: drop queued events and forget any active view."""
        if self._boundary_ok:
            self._counts["boundary_losses"] += 1
            self._history.append(marker)
        self._boundary_ok = False
        self._reobservation_required = True
        self._pending.clear()
        self._status = STATUS_UNKNOWN
        # Keep the last sequence: a late event from before the loss cannot
        # resurrect the old view after intake is reopened.

    def mark_host_unavailable(self):
        """Trusted signal that the host event stream can no longer be trusted."""
        if self._closed:
            raise SessionControlsNativeError("native path is closed")
        self._lose_boundary("host-unavailable")

    def mark_host_available(self):
        """Reopen intake only; offers stay denied until re-observation."""
        if self._closed:
            raise SessionControlsNativeError("native path is closed")
        if self._boundary_ok:
            return False
        self._boundary_ok = True
        return True

    def close(self):
        """Irreversible fail-closed cleanup of queued and folded state."""
        if self._closed:
            return
        self._lose_boundary("closed")
        self._closed = True

    # -- intake ----------------------------------------------------------
    def submit(self, event):
        """Queue one validated host event, with a bounded overflow fallback."""
        self._mutable()
        try:
            self._check_event(event)
        except SessionControlsNativeError:
            self._lose_boundary("invalid-event")
            raise
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
        """Consume at most ``max_batch`` items from a caller iterable."""
        self._mutable()
        if (isinstance(events, (str, bytes, bytearray, Mapping))
                or not isinstance(events, Iterable)):
            raise SessionControlsNativeError("event batch must be an iterable")
        consumed = queued = 0
        stopped = False
        for event in islice(events, self._max_batch):
            consumed += 1
            try:
                result = self.submit(event)
            except SessionControlsNativeError:
                stopped = True
                break
            if result.accepted:
                queued += 1
        return BatchResult(consumed, queued, consumed - queued, stopped)

    # -- folding ---------------------------------------------------------
    def _fold(self, event):
        """Fold one event into the bounded session view; return True if new."""
        if self._sequence is not None and event.sequence <= self._sequence:
            self._counts["stale"] += 1
            return False
        try:
            payload = event.payload
        except Exception:
            self._lose_boundary("invalid-observation")
            return False
        status = payload.get("state") if isinstance(payload, Mapping) else None
        if (type(status) is not str or not status
                or status not in SESSION_STATUS):
            self._lose_boundary("invalid-observation")
            return False
        previous = self._status
        self._sequence = event.sequence
        self._status = status
        self._counts["observations"] += 1
        if status == STATUS_ACTIVE and previous in _PRIVILEGED_STATUSES:
            # Returning from a locked/suspended session requires a fresh,
            # explicitly acknowledged re-observation before any offer.
            self._reobservation_required = True
        return True

    def drain(self, limit=None):
        """Fold at most ``limit`` queued events through the session contract."""
        self._mutable()
        if limit is None:
            limit = self._max_drain
        if type(limit) is not int or not 1 <= limit <= MAX_DRAIN:
            raise SessionControlsNativeError("invalid drain limit")
        processed = ignored = 0
        for _ in range(min(limit, len(self._pending))):
            event = self._pending.popleft()
            if self._fold(event):
                processed += 1
            else:
                ignored += 1
            if not self._boundary_ok:
                break
        self._counts["drained"] += processed
        self._counts["ignored"] += ignored
        return DrainReport(processed, ignored, len(self._pending),
                           self._status, self.availability, self.reason)

    def observe_session_state(self, state):
        """Fold an existing reconciled ``SessionState`` directly.

        Exact type gate: a forged subclass cannot supply a trusted label. This
        is a trusted host input, not an event, so it does not change the intake
        queue or the event sequence.
        """
        self._mutable()
        from canopy_features.reliability.lock_session_events import SessionState
        if type(state) is not SessionState:
            raise SessionControlsNativeError(
                "session observation requires SessionState")
        if state.suspended:
            status = "suspended"
        elif state.locked:
            status = "locked"
        else:
            status = STATUS_ACTIVE
        previous = self._status
        self._status = status
        self._counts["observations"] += 1
        if status == STATUS_ACTIVE and previous in _PRIVILEGED_STATUSES:
            self._reobservation_required = True
        return self.view()

    def reobserve_ready(self):
        """Explicit trusted acknowledgement; never driven by an event alone."""
        self._mutable()
        if self._reobservation_required:
            self._reobservation_required = False
            self._counts["reobservations"] += 1
        return self.view()

    # -- decisions -------------------------------------------------------
    @property
    def status(self):
        return self._status

    @property
    def availability(self):
        """Availability of the *boundary*, independent of any action grant."""
        if (self._closed or not self._boundary_ok
                or self._reobservation_required or self._status != STATUS_ACTIVE):
            return UNAVAILABLE
        return AVAILABLE

    @property
    def reason(self):
        if self._closed:
            return REASON_CLOSED
        if not self._boundary_ok:
            return REASON_HOST_UNAVAILABLE
        if self._reobservation_required:
            return REASON_REOBSERVATION
        if self._status == STATUS_UNKNOWN:
            return REASON_NO_HOST_OBSERVATION
        if self._status != STATUS_ACTIVE:
            return REASON_SESSION_NOT_ACTIVE
        return REASON_OK

    @property
    def disclosure(self):
        return DISCLOSURES[self.reason]

    def decide(self, action, capability, confirmation,
               command_candidate=NO_COMMAND):
        """Fail-closed decision; this never executes or describes an action."""
        if self._closed:
            return _deny(REASON_CLOSED)
        if not self._boundary_ok:
            return _deny(REASON_HOST_UNAVAILABLE)
        if self._reobservation_required:
            return _deny(REASON_REOBSERVATION)
        if self._status == STATUS_UNKNOWN:
            return _deny(REASON_NO_HOST_OBSERVATION)
        if self._status != STATUS_ACTIVE:
            return _deny(REASON_SESSION_NOT_ACTIVE)
        try:
            result = _controls.evaluate_native_path(
                action, capability=capability, confirmation=confirmation,
                command_candidate=command_candidate)
        except _controls.SessionControlsError as exc:
            raise SessionControlsNativeError(str(exc)) from None
        return NativeDecision(result.allowed, result.reason, result.action,
                              result.interface, result.path)

    @property
    def stats(self):
        return MappingProxyType(dict(self._counts))

    def view(self):
        """Read-only deterministic projection with fixed key order."""
        return MappingProxyType({
            "boundary": "available" if self._boundary_ok else "unavailable",
            "closed": self._closed,
            "reobservation_required": self._reobservation_required,
            "status": self._status,
            "sequence": self._sequence,
            "pending": len(self._pending),
            "overflow_policy": self._overflow_policy,
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
