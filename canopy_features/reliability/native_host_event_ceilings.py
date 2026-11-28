"""Native-Plasma ceilings for host-event consumers (PR #728 adaptation).

This module ports the *semantics* of the reviewed lifetime-ceiling fixes to
the native Python host boundary: an event budget is an epoch bound reconciled
by the next real event, and recovery/rebuild budgets belong to an explicit
host episode rather than the process lifetime. It does not replace the older
reliability modules: their lifetime-cap tests remain valid on this branch.
Nothing here samples a clock, polls, sleeps, starts a thread/service, touches
the OS or emits a new topic. All state is fixed-size and host-owned.

The authoritative catalog/producer is supplied by trusted host code as a
callable returning an immutable tuple. Every accepted event performs exactly
one bounded producer call, so the newest authoritative state wins even at an
epoch boundary; no refresh is frozen, queued or deferred to a timer.
"""
from collections import deque
from dataclasses import dataclass
from types import MappingProxyType

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    HostEvent,
    TOPICS as HOST_EVENT_TOPICS,
)

__all__ = [
    "RefreshEpochController",
    "EpochReport",
    "EpisodeRecoveryBudget",
    "EpisodeRebuildBudget",
    "REFRESH_TOPIC",
    "EPOCH_EVENT_LIMIT",
    "MAX_REPORT_HISTORY",
    "MAX_CATALOG_ENTRIES",
    "MAX_CATALOG_ID_CHARS",
    "FIXED_OUTCOMES",
    "OUTCOME_REFRESHED",
    "OUTCOME_UNCHANGED",
    "OUTCOME_REFUSED",
    "OUTCOME_REJECTED",
    "MAX_EPISODE_GRANTS",
    "MAX_EPISODE_REBUILDS",
    "CLAIMS",
]

REFRESH_TOPIC = "app.catalog.changed"
if REFRESH_TOPIC not in HOST_EVENT_TOPICS:
    raise RuntimeError("host event contract changed; ceiling adapter must be reviewed")

EPOCH_EVENT_LIMIT = 64
MAX_REPORT_HISTORY = 16
MAX_CATALOG_ENTRIES = 64
MAX_CATALOG_ID_CHARS = 64

OUTCOME_REFRESHED = "refreshed"
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_REFUSED = "snapshot_refused"
OUTCOME_REJECTED = "event_rejected"
FIXED_OUTCOMES = (OUTCOME_REFRESHED, OUTCOME_UNCHANGED,
                  OUTCOME_REFUSED, OUTCOME_REJECTED)

MAX_EPISODE_GRANTS = 64
MAX_EPISODE_REBUILDS = 4096

CLAIMS = (
    "existing_host_events_only",
    "epoch_not_lifetime",
    "one_bounded_producer_call",
    "no_timer_no_poll_no_queue",
    "counts_only_diagnostics",
)


@dataclass(frozen=True)
class EpochReport:
    """Immutable, count-only result; never carries catalog text."""

    outcome: str
    sequence: int
    producer_calls: int
    added: int
    removed: int
    entries: int
    reason: str | None = None

    def to_dict(self):
        return MappingProxyType({
            "outcome": self.outcome,
            "sequence": self.sequence,
            "producer_calls": self.producer_calls,
            "added": self.added,
            "removed": self.removed,
            "entries": self.entries,
            "reason": self.reason,
        })


class _CeilingError(ValueError):
    """Invalid host-supplied bound, state or event (internal base type)."""


class CeilingError(_CeilingError):
    """Invalid host-supplied bound, state or event."""


def _bounded_int(value, limit, name):
    if type(value) is not int or not 1 <= value <= limit:
        raise CeilingError("invalid " + name + " bound")
    return value


def _immutable_state(state):
    """Validate a host-produced catalog snapshot; no values are echoed."""
    if type(state) is not tuple or len(state) > MAX_CATALOG_ENTRIES:
        raise CeilingError("catalog state must be a bounded tuple")
    for entry in state:
        if (type(entry) is not str or not 0 < len(entry) <= MAX_CATALOG_ID_CHARS
                or any(not ch.isprintable() for ch in entry)):
            raise CeilingError("catalog state carries an invalid entry")
    return state


class RefreshEpochController:
    """Apply protocol-v2 catalog events with an epoch, not lifetime, ceiling."""

    __slots__ = ("_producer", "_max_events", "_state", "_last_sequence",
                 "_events", "_epoch_events", "_reconciliations",
                 "_producer_calls", "_rejections", "_reports", "_closed")

    def __init__(self, producer, *, max_events=EPOCH_EVENT_LIMIT):
        if not callable(producer):
            raise CeilingError("trusted host producer must be callable")
        self._producer = producer
        self._max_events = _bounded_int(max_events, EPOCH_EVENT_LIMIT,
                                        "refresh epoch")
        self._state = ()
        self._last_sequence = 0
        self._events = 0
        self._epoch_events = 0
        self._reconciliations = 0
        self._producer_calls = 0
        self._rejections = 0
        self._reports = deque(maxlen=MAX_REPORT_HISTORY)
        self._closed = False

    def observe(self, event):
        """Apply one real HostEvent; return a fixed, count-only report."""
        if self._closed:
            return self._reject("CLOSED")
        if (type(event) is not HostEvent or event.version != PROTOCOL_VERSION
                or event.topic != REFRESH_TOPIC
                or type(event.sequence) is not int or event.sequence < 1):
            return self._reject("BAD_EVENT")
        if event.sequence <= self._last_sequence:
            return self._reject("REPLAYED_SEQUENCE")

        # At an epoch boundary the *next real event* reconciles. The single
        # bounded producer call below reads the current authoritative state,
        # so the newest catalog always wins and nothing is deferred.
        reconciling = self._epoch_events >= self._max_events
        self._producer_calls += 1
        try:
            state = _immutable_state(self._producer())
        except Exception:
            # Atomic refusal: no state change; counts only in diagnostics.
            self._last_sequence = event.sequence
            self._events += 1
            self._advance_epoch(reconciling)
            return self._report(OUTCOME_REFUSED, event.sequence, 0, 0,
                                len(self._state))

        previous = self._state
        changed = state != previous
        self._state = state
        self._last_sequence = event.sequence
        self._events += 1
        self._advance_epoch(reconciling)
        outcome = OUTCOME_REFRESHED if changed else OUTCOME_UNCHANGED
        return self._report(outcome, event.sequence,
                            len(state) - len(previous) if changed else 0,
                            len(previous) - len(state) if changed else 0,
                            len(state))

    def _advance_epoch(self, reconciling):
        if reconciling:
            self._epoch_events = 1
            self._reconciliations += 1
        else:
            self._epoch_events += 1

    def _reject(self, reason):
        self._rejections += 1
        return self._report(OUTCOME_REJECTED, 0, 0, 0,
                            len(self._state), reason)

    def _report(self, outcome, sequence, added, removed, entries,
                reason=None):
        self._reports.append(EpochReport(
            outcome, sequence,
            0 if outcome == OUTCOME_REJECTED else 1,
            added, removed, entries, reason))
        return self._reports[-1]

    @property
    def authoritative_state(self):
        """Current authoritative tuple; test data, never put in a report."""
        return self._state

    @property
    def event_count(self):
        return self._events

    @property
    def epoch_events(self):
        return self._epoch_events

    @property
    def reconciliations(self):
        return self._reconciliations

    @property
    def producer_calls(self):
        return self._producer_calls

    @property
    def rejection_count(self):
        return self._rejections

    @property
    def reports(self):
        return tuple(self._reports)

    @property
    def connected(self):
        """The epoch bound is never a trust-gate or freeze condition."""
        return not self._closed

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._state = ()
        self._reports.clear()


class EpisodeRecoveryBudget:
    """Per-episode recovery grants with a diagnostic-only lifetime count."""

    __slots__ = ("_max", "_episode_grants", "_grants_total", "_episodes")

    def __init__(self, max_grants=MAX_EPISODE_GRANTS):
        self._max = _bounded_int(max_grants, MAX_EPISODE_GRANTS, "recovery")
        self._episode_grants = 0
        self._grants_total = 0
        self._episodes = 0

    def new_episode(self):
        """Explicit host condition opens a new episode and rebases the budget."""
        self._episode_grants = 0
        self._episodes += 1

    def grant(self):
        if self._episode_grants >= self._max:
            return "CAPACITY"
        self._episode_grants += 1
        self._grants_total += 1
        return "RECOVERY_GRANTED"

    @property
    def episode_grants(self):
        return self._episode_grants

    @property
    def grants_total(self):
        return self._grants_total

    @property
    def episodes(self):
        return self._episodes


class EpisodeRebuildBudget:
    """Per-episode rebuild credits; retained entries stay within hard caps."""

    __slots__ = ("_cap", "_per_episode", "_retained", "_rebuilt",
                 "_generations", "_closed")

    def __init__(self, cap=MAX_EPISODE_REBUILDS, per_episode=8):
        self._cap = _bounded_int(cap, MAX_EPISODE_REBUILDS, "retained")
        self._per_episode = _bounded_int(per_episode,
                                         MAX_EPISODE_REBUILDS, "rebuild")
        self._retained = 0
        self._rebuilt = 0
        self._generations = 0
        self._closed = False

    def shed(self):
        """Explicit shedding clears retained entries and closes the episode."""
        self._retained = 0
        self._rebuilt = 0

    def normal_transition(self):
        """Explicit host NORMAL condition opens a new rebuild episode."""
        self._rebuilt = 0
        self._generations += 1

    def rebuild(self, count):
        if self._closed:
            return 0
        if type(count) is not int or count < 0:
            raise CeilingError("rebuild count must be a bounded integer")
        allowed = min(count, self._per_episode - self._rebuilt,
                      self._cap - self._retained)
        if allowed <= 0:
            return 0
        self._retained += allowed
        self._rebuilt += allowed
        return allowed

    def close(self):
        self._closed = True
        self._retained = 0
        self._rebuilt = 0

    @property
    def retained(self):
        return self._retained

    @property
    def rebuilt(self):
        return self._rebuilt

    @property
    def generations(self):
        return self._generations
