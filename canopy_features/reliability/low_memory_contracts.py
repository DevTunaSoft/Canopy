"""Simulated low-memory contracts for bounded caches.

The condition is always a caller-supplied string: ``NORMAL``, ``LOW`` or
``UNKNOWN``. The module never samples memory, polls, starts threads or
services, reads a clock, or touches the OS. It coordinates fail-closed
shedding of caller-declared bounded caches and grants recovery work only
under explicit, deterministic caps. Recovery never restores more entries
than the caller's budgets allow.

This is simulation-only bookkeeping, not a running-shell profile. Acceptance
stays ``NOT_ESTABLISHED`` and no caller input can turn the record into a
runtime or release claim.
"""

from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.performance.memory_delta import MAX_SAMPLES
from canopy_features.reliability.host_reliability_snapshot import (
    MAX_NOTICES, MAX_WINDOWS)

__all__ = [
    "LowMemoryError", "CacheBoundary", "ShedDecision", "BoundaryState",
    "RecoveryStep", "LowMemorySnapshot", "LowMemoryCacheController",
    "CONDITION_NORMAL", "CONDITION_LOW", "CONDITION_UNKNOWN", "CONDITIONS",
    "SHED_NORMAL", "SHED_LOW_MEMORY", "SHED_UNKNOWN", "DEFAULT_BOUNDARIES",
    "MAX_ENTRIES_PER_BOUNDARY", "MAX_TOTAL_ENTRIES", "MAX_RECOVERY_BUDGET",
    "MAX_RECOVERY_ROUNDS", "MAX_REBUILT_TOTAL", "ACCEPTANCE_NOT_ESTABLISHED",
    "decide",
]

CONDITION_NORMAL = "NORMAL"
CONDITION_LOW = "LOW"
CONDITION_UNKNOWN = "UNKNOWN"
CONDITIONS = frozenset((CONDITION_NORMAL, CONDITION_LOW, CONDITION_UNKNOWN))

SHED_NORMAL = "NORMAL"
SHED_LOW_MEMORY = "LOW_MEMORY"
SHED_UNKNOWN = "UNKNOWN_CONDITION"
SHED_ACTIVE = "SHEDDING"
STEP_ROUND_CAP = "ROUND_CAP"
STEP_REBUILT_CAP = "REBUILT_CAP"
STEP_GRANTED = "GRANTED"

MAX_NAME_CHARS = 64
# Reuse the ceilings already owned by the reliability/performance modules.
MAX_ENTRIES_PER_BOUNDARY = MAX_SAMPLES
MAX_TOTAL_ENTRIES = 4096
DEFAULT_RECOVERY_BUDGET = 8
MAX_RECOVERY_BUDGET = 64
MAX_RECOVERY_ROUNDS = 8
MAX_REBUILT_TOTAL = 4096
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"


class LowMemoryError(ValueError):
    """Invalid condition, boundary, cap or payload in a low-memory contract."""


@dataclass(frozen=True)
class CacheBoundary:
    """One named cache and the entry cap it may never exceed."""

    name: str
    max_entries: int

    def __post_init__(self):
        if type(self.name) is not str or not 0 < len(self.name) <= MAX_NAME_CHARS:
            raise LowMemoryError("boundary name must be bounded text")
        if any(not ch.isprintable() for ch in self.name):
            raise LowMemoryError("boundary name must be printable")
        if (type(self.max_entries) is not int
                or not 1 <= self.max_entries <= MAX_ENTRIES_PER_BOUNDARY):
            raise LowMemoryError("boundary cap out of bounded range")


@dataclass(frozen=True)
class ShedDecision:
    """Fail-closed answer for one boundary under a simulated condition."""

    shed: bool
    allow_populate: bool
    retained_entries: int
    reason: str


@dataclass(frozen=True)
class BoundaryState:
    """Immutable per-boundary view inside a controller snapshot."""

    name: str
    max_entries: int
    retained: int
    shedding: bool
    recovery_credit: int


@dataclass(frozen=True)
class RecoveryStep:
    """One bounded grant of rebuild credits."""

    granted: int
    round: int
    done: bool
    reason: str


@dataclass(frozen=True)
class LowMemorySnapshot:
    """One deterministic, immutable record of simulated shedding state."""

    condition: str
    shedding: bool
    boundaries: tuple
    shed_count: int
    recovery_count: int
    rebuilt_entries: int
    recovery_round: int
    acceptance: str

    def to_dict(self):
        """Return a fresh read-only view with a fixed, stable key order."""
        return MappingProxyType({
            "condition": self.condition,
            "shedding": self.shedding,
            "boundaries": tuple(MappingProxyType({
                "name": b.name,
                "max_entries": b.max_entries,
                "retained": b.retained,
                "shedding": b.shedding,
                "recovery_credit": b.recovery_credit,
            }) for b in self.boundaries),
            "shed_count": self.shed_count,
            "recovery_count": self.recovery_count,
            "rebuilt_entries": self.rebuilt_entries,
            "recovery_round": self.recovery_round,
            "acceptance": self.acceptance,
        })


def _condition(value):
    # Exact str: a bytes value or a bool cannot be mistaken for a label.
    if type(value) is not str or value not in CONDITIONS:
        raise LowMemoryError("unsupported memory condition")
    return value


def decide(condition, boundary):
    """Pure fail-closed decision for one boundary and a simulated condition."""
    condition = _condition(condition)
    if not isinstance(boundary, CacheBoundary):
        raise LowMemoryError("boundary must be a CacheBoundary")
    if condition == CONDITION_NORMAL:
        return ShedDecision(False, True, boundary.max_entries, SHED_NORMAL)
    reason = (SHED_LOW_MEMORY if condition == CONDITION_LOW else SHED_UNKNOWN)
    return ShedDecision(True, False, 0, reason)


DEFAULT_BOUNDARIES = (
    CacheBoundary("delivery_notices", MAX_NOTICES),
    CacheBoundary("switcher_windows", MAX_WINDOWS),
    CacheBoundary("memory_samples", MAX_SAMPLES),
)


class LowMemoryCacheController:
    """Coordinate shedding and bounded recovery over named bounded caches.

    The controller stores only immutable tuple snapshots. When the simulated
    condition is anything but ``NORMAL`` every cache is empty and population
    is refused. Recovery grants credits in bounded rounds; the lifetime count
    of rebuilt entries is capped so repeated shed/recover cycles cannot grow
    retained state without bound.
    """

    __slots__ = ("_condition", "_caps", "_caches", "_budget", "_max_rebuilt",
                 "_credits", "_round", "_rebuilt", "_shed_count",
                 "_recovery_count")

    def __init__(self, boundaries=DEFAULT_BOUNDARIES, *,
                 recovery_budget=DEFAULT_RECOVERY_BUDGET,
                 max_rebuilt=MAX_REBUILT_TOTAL):
        if isinstance(boundaries, (str, bytes, bytearray)) or not isinstance(
                boundaries, (tuple, list)):
            raise LowMemoryError("boundaries must be a sequence of CacheBoundary")
        declared = tuple(boundaries)
        if not declared:
            raise LowMemoryError("at least one boundary is required")
        for boundary in declared:
            if not isinstance(boundary, CacheBoundary):
                raise LowMemoryError("boundaries must hold CacheBoundary values")
        names = [boundary.name for boundary in declared]
        if len(set(names)) != len(names):
            raise LowMemoryError("duplicate boundary names")
        if sum(boundary.max_entries for boundary in declared) > MAX_TOTAL_ENTRIES:
            raise LowMemoryError("total boundary caps exceed bound")
        if (type(recovery_budget) is not int
                or not 1 <= recovery_budget <= MAX_RECOVERY_BUDGET):
            raise LowMemoryError("recovery budget out of bounded range")
        if (type(max_rebuilt) is not int
                or not 1 <= max_rebuilt <= MAX_REBUILT_TOTAL):
            raise LowMemoryError("rebuilt total out of bounded range")
        ordered = tuple(sorted(declared, key=lambda b: b.name))
        self._caps = {b.name: b.max_entries for b in ordered}
        self._caches = {b.name: () for b in ordered}
        self._budget = recovery_budget
        self._max_rebuilt = max_rebuilt
        # Start shedding: an unseen condition is never assumed to be safe.
        self._condition = CONDITION_UNKNOWN
        self._credits = 0
        self._round = 0
        self._rebuilt = 0
        self._shed_count = 0
        self._recovery_count = 0

    def _shedding(self):
        return self._condition != CONDITION_NORMAL

    def _decision(self):
        if not self._shedding():
            return ShedDecision(False, True,
                                sum(len(v) for v in self._caches.values()),
                                SHED_NORMAL)
        reason = (SHED_LOW_MEMORY if self._condition == CONDITION_LOW
                  else SHED_UNKNOWN)
        return ShedDecision(True, False, 0, reason)

    def observe(self, condition):
        """Apply a simulated condition and return the resulting decision."""
        condition = _condition(condition)
        previous = self._condition
        if condition == previous:
            return self._decision()
        if condition == CONDITION_NORMAL:
            self._condition = condition
            self._credits = self._budget
            self._round = 1
            self._recovery_count += 1
        else:
            if previous == CONDITION_NORMAL:
                self._shed_count += 1
            self._condition = condition
            self._credits = 0
            self._round = 0
            for name in self._caches:
                self._caches[name] = ()
        return self._decision()

    def values(self, name):
        """Return the immutable tuple currently cached for ``name``."""
        if type(name) is not str or name not in self._caps:
            raise LowMemoryError("unknown cache boundary")
        return self._caches[name]

    def populate(self, name, entries):
        """Rebuild at most the credited, capped prefix; return entries kept.

        Invalid input fails closed with ``LowMemoryError`` before any state
        changes. While shedding, or when no credit remains, the cache stays
        empty and zero is returned rather than exposing stale entries.
        """
        if type(name) is not str or name not in self._caps:
            raise LowMemoryError("unknown cache boundary")
        if type(entries) is not tuple:
            raise LowMemoryError("entries must be a tuple")
        cap = self._caps[name]
        if len(entries) > cap:
            raise LowMemoryError("entry count exceeds boundary cap")
        if self._shedding() or self._credits <= 0:
            return 0
        allowed = min(len(entries), self._credits,
                      self._max_rebuilt - self._rebuilt)
        if allowed <= 0:
            return 0
        self._caches[name] = entries[:allowed]
        self._credits -= allowed
        self._rebuilt += allowed
        return allowed

    def advance_recovery(self):
        """Grant one bounded batch of rebuild credits, or report done."""
        if self._shedding():
            return RecoveryStep(0, self._round, True, SHED_ACTIVE)
        if self._round >= MAX_RECOVERY_ROUNDS:
            return RecoveryStep(0, self._round, True, STEP_ROUND_CAP)
        if self._rebuilt >= self._max_rebuilt:
            return RecoveryStep(0, self._round, True, STEP_REBUILT_CAP)
        self._credits += self._budget
        self._round += 1
        return RecoveryStep(self._budget, self._round, False, STEP_GRANTED)

    def snapshot(self):
        """Return a deterministic, immutable view of the simulated state."""
        shedding = self._shedding()
        states = tuple(
            BoundaryState(name, self._caps[name], len(self._caches[name]),
                          shedding, 0 if shedding else self._credits)
            for name in sorted(self._caps))
        return LowMemorySnapshot(
            condition=self._condition,
            shedding=shedding,
            boundaries=states,
            shed_count=self._shed_count,
            recovery_count=self._recovery_count,
            rebuilt_entries=self._rebuilt,
            recovery_round=self._round,
            acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        )
