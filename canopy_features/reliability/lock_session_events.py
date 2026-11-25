"""Bounded, event-driven reconciliation of suspend/lock/resume event order.

Pure Python state machine. Host code pushes events as they arrive; this module
returns an immutable outcome for each event and never looks for work on its
own. It has no timers, threads, polling, D-Bus, privileged actions, Qt or QML.

Ordering rules (arrival order is authoritative, timestamps guard against late
and backwards events):
  * a duplicate fingerprint is ignored;
  * an event older than the newest observed event is stale and cannot regress
    the committed state;
  * SUSPEND forces the locked flag on (fail-closed);
  * UNLOCK while suspended cannot expose an unlocked session;
  * redundant events report a status but do not emit a transition.

This component is modular: it does not observe real desktop events and does
not prove a working desktop until host code wires it into the Qt application.
"""
from collections import deque
from dataclasses import dataclass
import math
import re

from canopy_core.host_events import HostEventError

SUSPEND = "suspend"
RESUME = "resume"
LOCK = "lock"
UNLOCK = "unlock"
KINDS = frozenset({SUSPEND, RESUME, LOCK, UNLOCK})

TRANSITION = "TRANSITION"
DUPLICATE = "DUPLICATE"
STALE = "STALE"
REDUNDANT = "REDUNDANT"
DEFERRED = "DEFERRED"

MAX_TIMESTAMP = 1_000_000_000_000
MAX_SOURCE_BYTES = 64
MAX_DUPLICATE_WINDOW = 1024
MAX_HISTORY = 1024

_SOURCE = re.compile(r"[a-z0-9_.:-]{0,64}\Z")


class LockSessionEventError(HostEventError):
    """Invalid event, bound, or caller use of the reconciler."""


@dataclass(frozen=True)
class SessionEvent:
    """One externally observed power or lock event with bounded fields."""

    kind: str
    timestamp: float
    source: str = ""

    def __post_init__(self):
        if type(self.kind) is not str or self.kind not in KINDS:
            raise LockSessionEventError("unknown session event kind")
        if type(self.timestamp) not in (int, float):
            raise LockSessionEventError("event timestamp must be a finite number")
        if abs(self.timestamp) > MAX_TIMESTAMP:
            raise LockSessionEventError("event timestamp exceeds bound")
        if not math.isfinite(self.timestamp):
            raise LockSessionEventError("event timestamp must be finite")
        if (type(self.source) is not str
                or len(self.source.encode("utf-8")) > MAX_SOURCE_BYTES
                or not _SOURCE.fullmatch(self.source)):
            raise LockSessionEventError("invalid event source")


@dataclass(frozen=True)
class SessionState:
    """Canonical, fail-closed session state derived from observed events."""

    suspended: bool
    locked: bool

    @property
    def label(self):
        if self.suspended:
            return "suspended"
        if self.locked:
            return "locked"
        return "active"


@dataclass(frozen=True)
class Outcome:
    """Result of one observation; state is the state after the event."""

    status: str
    event: SessionEvent
    previous: SessionState
    state: SessionState

    @property
    def transitioned(self):
        return self.status == TRANSITION


class Reconciler:
    """Single-thread, bounded reconciler. Call only from the host event loop."""

    def __init__(self, *, initial_locked=True, duplicate_window=64,
                 history_limit=32):
        if type(initial_locked) is not bool:
            raise LockSessionEventError("initial_locked must be a bool")
        if (type(duplicate_window) is not int
                or not 1 <= duplicate_window <= MAX_DUPLICATE_WINDOW):
            raise LockSessionEventError("invalid duplicate window")
        if (type(history_limit) is not int
                or not 0 <= history_limit <= MAX_HISTORY):
            raise LockSessionEventError("invalid history limit")
        self._state = SessionState(False, initial_locked)
        self._duplicate_window = duplicate_window
        self._seen = deque()
        self._seen_set = set()
        self._history = deque(maxlen=history_limit)
        self._last_timestamp = None
        self._accepted = 0

    @property
    def state(self):
        return self._state

    @property
    def accepted(self):
        return self._accepted

    @property
    def history(self):
        """Immutable tuple of the most recent transitions (bounded)."""
        return tuple(self._history)

    def observe(self, event):
        if type(event) is not SessionEvent:
            raise LockSessionEventError("observe() requires a SessionEvent")
        fingerprint = (event.kind, event.timestamp, event.source)
        if fingerprint in self._seen_set:
            return Outcome(DUPLICATE, event, self._state, self._state)
        self._remember(fingerprint)
        if (self._last_timestamp is not None
                and event.timestamp < self._last_timestamp):
            return Outcome(STALE, event, self._state, self._state)
        self._last_timestamp = event.timestamp
        previous = self._state
        if event.kind == UNLOCK and previous.suspended:
            return Outcome(DEFERRED, event, previous, previous)
        current = self._next(previous, event.kind)
        if current == previous:
            return Outcome(REDUNDANT, event, previous, previous)
        self._state = current
        self._accepted += 1
        outcome = Outcome(TRANSITION, event, previous, current)
        if self._history.maxlen:
            self._history.append(outcome)
        return outcome

    def _remember(self, fingerprint):
        if len(self._seen) >= self._duplicate_window:
            self._seen_set.discard(self._seen.popleft())
        self._seen.append(fingerprint)
        self._seen_set.add(fingerprint)

    @staticmethod
    def _next(state, kind):
        if kind == SUSPEND:
            return SessionState(True, True)
        if kind == RESUME:
            return SessionState(False, state.locked)
        if kind == LOCK:
            return SessionState(state.suspended, True)
        return SessionState(False, False)
