"""Fail-closed suspend/resume source contracts at the host-event boundary.

This module is a *decision* layer, not an executor. A trusted host passes an
already-delivered ``canopy_core.host_events.HostEvent`` on the existing
``session.state.changed`` topic, or an existing reconciled
``lock_session_events.SessionState``. The module returns an immutable,
bounded availability decision for host-interaction operations. It performs no
real suspend or resume, no D-Bus, no process or window action, no filesystem or
network I/O, and starts no thread, timer or poll loop.

Fail-closed rule: an operation is available only while the host is confirmed
active. Suspended, locked, resuming-but-not-reobserved, and unknown states all
report ``UNAVAILABLE`` with a stable reason and a caller-independent disclosure.
A resume event alone never re-enables anything: the trusted caller must first
re-observe the desktop and acknowledge it with :meth:`resume_ready`. No method
here changes the host; the caller owns any eventual action.

Existing contracts reused (nothing new is invented):
- ``canopy_core.host_events`` -- protocol v2 ``HostEvent`` and the existing
  ``session.state.changed`` topic, including its ``state`` field vocabulary.
- ``canopy_features.reliability.lock_session_events.SessionState`` -- the
  reconciled fail-closed session state is accepted directly.
- ``canopy_features.system.quick_controls_state`` -- supplies the canonical
  session state token set; this module guards against drift instead of
  redefining it.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from canopy_core.host_events import (
    PROTOCOL_VERSION, TOPICS as _HOST_TOPICS, HostEvent, HostEventError)
from canopy_features.reliability.lock_session_events import SessionState
from canopy_features.system.quick_controls_state import STATUS_TOKENS

__all__ = [
    "SESSION_TOPIC", "SESSION_STATES", "PHASES", "PHASE_UNKNOWN",
    "PHASE_ACTIVE", "PHASE_LOCKED", "PHASE_SUSPENDED",
    "PHASE_RESUME_PENDING", "OPERATIONS", "AVAILABLE", "UNAVAILABLE",
    "REASON_OK", "REASON_SUSPENDED", "REASON_LOCKED",
    "REASON_RESUME_PENDING", "REASON_UNKNOWN", "REASON_INVALID_OPERATION",
    "DISCLOSURES", "DEFAULT_SOURCE", "MAX_HISTORY",
    "SuspendResumeError", "Decision", "SuspendResumeContracts", "empty",
]

SESSION_TOPIC = "session.state.changed"
SESSION_STATES = frozenset(STATUS_TOKENS["session"])
if SESSION_TOPIC not in _HOST_TOPICS or SESSION_STATES != STATUS_TOKENS["session"]:
    raise RuntimeError("host event session contract changed")

PHASE_UNKNOWN = "unknown"
PHASE_ACTIVE = "active"
PHASE_LOCKED = "locked"
PHASE_SUSPENDED = "suspended"
PHASE_RESUME_PENDING = "resume_pending"
PHASES = frozenset({PHASE_UNKNOWN, PHASE_ACTIVE, PHASE_LOCKED,
                    PHASE_SUSPENDED, PHASE_RESUME_PENDING})

# Bounded, enumerated host-interaction operations. This is a decision surface
# only: none of these operations can be performed by this module.
OPERATIONS = frozenset({
    "read_status", "open_settings", "focus_window", "launch_app",
})

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"

REASON_OK = "ok"
REASON_SUSPENDED = "host-suspended"
REASON_LOCKED = "host-locked"
REASON_RESUME_PENDING = "resume-needs-reobservation"
REASON_UNKNOWN = "unknown-host-state"
REASON_INVALID_OPERATION = "invalid-operation"

# Stable, caller-independent text. No payload string can reach a presentation.
DISCLOSURES = MappingProxyType({
    REASON_OK: "Available",
    REASON_SUSPENDED: "Unavailable — host is suspended",
    REASON_LOCKED: "Unavailable — host session is locked",
    REASON_RESUME_PENDING: "Unavailable — awaiting desktop re-observation",
    REASON_UNKNOWN: "Unavailable — host state unknown",
    REASON_INVALID_OPERATION: "Unavailable — unknown operation",
})

DEFAULT_SOURCE = "host-events"
MAX_HISTORY = 64


class SuspendResumeError(HostEventError):
    """Invalid caller input, wrong event type/topic or misuse of the gate."""


@dataclass(frozen=True)
class Decision:
    """Whether a presentation may *offer* an operation, and why."""

    available: bool
    reason: str

    def __post_init__(self):
        if type(self.available) is not bool or self.reason not in DISCLOSURES:
            raise SuspendResumeError("invalid suspend/resume decision")

    @property
    def disclosure(self):
        return DISCLOSURES[self.reason]

    def to_dict(self):
        return {
            "available": self.available,
            "reason": self.reason,
            "disclosure": self.disclosure,
        }


def _deny(reason):
    return Decision(False, reason)


@dataclass(frozen=True)
class SuspendResumeContracts:
    """Immutable, bounded suspend/resume decision snapshot.

    Every observation returns a new snapshot; this one is never mutated.
    ``sequence`` is the last accepted event sequence; an older delivered event
    cannot regress a fail-closed phase.
    """

    phase: str = PHASE_UNKNOWN
    state: str = PHASE_UNKNOWN
    sequence: int = 0
    source: str = DEFAULT_SOURCE
    history: tuple = ()

    def __post_init__(self):
        if self.phase not in PHASES or self.state not in SESSION_STATES:
            raise SuspendResumeError("invalid suspend/resume snapshot state")
        if type(self.sequence) is not int or self.sequence < 0:
            raise SuspendResumeError("invalid host event sequence")
        if type(self.source) is not str or not self.source:
            raise SuspendResumeError("invalid observation source")
        if type(self.history) is not tuple:
            raise SuspendResumeError("history must be a tuple")

    def _next(self, phase, state, sequence):
        history = (self.history + (phase,))[-MAX_HISTORY:]
        return SuspendResumeContracts(phase=phase, state=state,
                                      sequence=sequence, source=self.source,
                                      history=history)

    @staticmethod
    def _phase_for(state, current):
        if state == "suspended":
            return PHASE_SUSPENDED
        if state == "unknown":
            return PHASE_UNKNOWN
        # A live state observed after suspension means a resume happened, but
        # nothing is trusted until the caller re-observes the desktop.
        if current == PHASE_SUSPENDED:
            return PHASE_RESUME_PENDING
        return PHASE_ACTIVE if state == "active" else PHASE_LOCKED

    def observe(self, event):
        """Fold an already-delivered host event; malformed data fails closed.

        A wrong caller type or a different topic is a contract violation and
        raises. An ill-formed ``state`` value on the correct topic is *not*
        guessed: it degrades the snapshot to ``unknown`` with no exception, so
        a host callback can never be crashed by observed data.
        """
        if not isinstance(event, HostEvent):
            raise SuspendResumeError("observation requires a HostEvent")
        if event.topic != SESSION_TOPIC:
            raise SuspendResumeError("unsupported host event topic")
        if event.version != PROTOCOL_VERSION:
            raise SuspendResumeError("unsupported host event version")
        if type(event.sequence) is not int or event.sequence < 0:
            raise SuspendResumeError("invalid host event sequence")
        if event.sequence <= self.sequence:
            return self
        try:
            state = event.payload.get("state")
        except (KeyError, TypeError, AttributeError):
            state = None
        if type(state) is not str or state not in SESSION_STATES:
            state = "unknown"
        return self._next(self._phase_for(state, self.phase), state,
                          event.sequence)

    def from_session_state(self, state):
        """Fold the existing reconciled ``SessionState`` value object.

        The durable ``suspended``/``locked`` fields are read directly, never a
        subclass-supplied label, so a forged view cannot acquire availability.
        """
        if type(state) is not SessionState:
            raise SuspendResumeError("session observation requires SessionState")
        if state.suspended:
            token = "suspended"
        elif state.locked:
            token = "locked"
        else:
            token = "active"
        return self._next(self._phase_for(token, self.phase), token,
                          self.sequence + 1)

    def resume_ready(self):
        """Acknowledge a re-observed desktop after resume.

        Only a snapshot that actually observed a resume, and is still waiting
        for re-observation, may become active. Every other call is rejected.
        """
        if self.phase != PHASE_RESUME_PENDING:
            raise SuspendResumeError("no observed resume awaiting re-observation")
        return self._next(PHASE_ACTIVE, "active", self.sequence + 1)

    def decide(self, operation):
        """Fail-closed availability decision; this never executes anything."""
        if type(operation) is not str or operation not in OPERATIONS:
            return _deny(REASON_INVALID_OPERATION)
        if self.phase == PHASE_ACTIVE:
            return Decision(True, REASON_OK)
        reasons = {
            PHASE_SUSPENDED: REASON_SUSPENDED,
            PHASE_LOCKED: REASON_LOCKED,
            PHASE_RESUME_PENDING: REASON_RESUME_PENDING,
            PHASE_UNKNOWN: REASON_UNKNOWN,
        }
        return _deny(reasons[self.phase])

    @property
    def availability(self):
        return AVAILABLE if self.phase == PHASE_ACTIVE else UNAVAILABLE

    def view(self):
        """Read-only, JSON-serializable projection with fixed key order."""
        return MappingProxyType({
            "phase": self.phase,
            "state": self.state,
            "sequence": self.sequence,
            "source": self.source,
            "availability": self.availability,
            "history": self.history,
        })

    def to_dict(self):
        return dict(self.view())


def empty():
    """The honest default: nothing observed, nothing granted, nothing enabled."""
    return SuspendResumeContracts()
