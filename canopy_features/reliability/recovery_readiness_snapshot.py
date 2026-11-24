"""Bounded, immutable, host-facing boot/recovery readiness snapshot.

Composes three already-tested value objects produced by independent reliability
models into one deterministic record:

* ``reliability/startup_checkpoints.py`` -- the durable ``RecoveryDecision``
  derived after a crash (action, completed/unwind steps, reason);
* ``reliability/lock_session_events.py`` -- the fail-closed ``SessionState``,
  accepted-event count and bounded recent outcome history;
* ``reliability/event_delivery_loss.py`` -- ``DeliveryStats`` counters and the
  bounded ``OverflowNotice`` history of one delivery channel.

This is a pure composition layer: no I/O, clock, randomness, threads, locks,
polling, OS or Qt observation. The caller hands it value objects it already
owns. Embedded collections are bounded (recent outcomes, notices, text), every
public view is immutable, and two compositions of equal inputs are
byte-for-byte identical. No caller input can make an acceptance or real
observation claim: acceptance is always ``NOT_ESTABLISHED`` and observation
always ``NOT_PERFORMED``.

The status describes only the supplied state, never a running desktop.
"""
from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.reliability.event_delivery_loss import (
    DeliveryStats, OverflowNotice)
from canopy_features.reliability.lock_session_events import (
    DEFERRED, DUPLICATE, REDUNDANT, STALE, TRANSITION,
    Outcome, Reconciler, SessionState)
from canopy_features.reliability.startup_checkpoints import (
    FAIL_CLOSED, READY, ROLLBACK, START_FRESH, RecoveryDecision)

SCHEMA = 1
MAX_NOTICES = 8
MAX_RECENT = 8
MAX_CHARS = 160
MAX_POLICY_CHARS = 32

RECOVERY_ACTIONS = frozenset({START_FRESH, READY, ROLLBACK, FAIL_CLOSED})
SESSION_LABELS = frozenset({"suspended", "locked", "active"})
SESSION_STATUSES = frozenset({TRANSITION, DUPLICATE, STALE, REDUNDANT, DEFERRED})
COUNTER_FIELDS = ("sent", "received", "delivered", "duplicates", "reordered",
                  "gaps", "missed", "dropped", "rejected")
ANOMALY_FIELDS = ("dropped", "rejected", "gaps", "duplicates", "reordered",
                  "missed")

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"


class SnapshotError(ValueError):
    """Invalid component, counter, flag or bound passed to ``compose``."""


@dataclass(frozen=True)
class StartupView:
    """Bounded projection of a durable ``RecoveryDecision``."""

    action: str
    safe_to_start: bool
    needs_rollback: bool
    completed_count: int
    unwind_count: int
    reason: str


@dataclass(frozen=True)
class SessionView:
    """Bounded projection of a lock/session reconciler."""

    label: str
    suspended: bool
    locked: bool
    accepted: int
    recent_statuses: tuple


@dataclass(frozen=True)
class DeliveryView:
    """Counted delivery health plus the last recorded overflow policy."""

    sent: int
    received: int
    delivered: int
    duplicates: int
    reordered: int
    gaps: int
    missed: int
    dropped: int
    rejected: int
    notice_count: int
    last_policy: object


@dataclass(frozen=True)
class RecoveryReadinessSnapshot:
    """One deterministic, immutable record of host recovery readiness."""

    schema: int
    status: str
    acceptance: str
    observation: str
    startup: StartupView
    session: SessionView
    delivery: DeliveryView

    @property
    def is_blocked(self) -> bool:
        return self.status == STATUS_BLOCKED

    def to_dict(self):
        """Return a fresh read-only view with a fixed, stable key order."""
        return MappingProxyType({
            "schema": self.schema,
            "status": self.status,
            "acceptance": self.acceptance,
            "observation": self.observation,
            "startup": MappingProxyType({
                "action": self.startup.action,
                "safe_to_start": self.startup.safe_to_start,
                "needs_rollback": self.startup.needs_rollback,
                "completed_count": self.startup.completed_count,
                "unwind_count": self.startup.unwind_count,
                "reason": self.startup.reason,
            }),
            "session": MappingProxyType({
                "label": self.session.label,
                "suspended": self.session.suspended,
                "locked": self.session.locked,
                "accepted": self.session.accepted,
                "recent_statuses": self.session.recent_statuses,
            }),
            "delivery": MappingProxyType({
                "sent": self.delivery.sent,
                "received": self.delivery.received,
                "delivered": self.delivery.delivered,
                "duplicates": self.delivery.duplicates,
                "reordered": self.delivery.reordered,
                "gaps": self.delivery.gaps,
                "missed": self.delivery.missed,
                "dropped": self.delivery.dropped,
                "rejected": self.delivery.rejected,
                "notice_count": self.delivery.notice_count,
                "last_policy": self.delivery.last_policy,
            }),
        })


def _count(value, field):
    if type(value) is not int or value < 0:
        raise SnapshotError(field + " must be a non-negative int")
    return value


def _flag(value, field):
    if type(value) is not bool:
        raise SnapshotError(field + " must be a bool")
    return value


def _text(value, field):
    if type(value) is not str:
        raise SnapshotError(field + " must be a string")
    return value


def _bounded_text(value, field):
    return _text(value, field)[:MAX_CHARS]


def _startup_view(decision):
    if not isinstance(decision, RecoveryDecision):
        raise SnapshotError("startup must be a RecoveryDecision")
    action = _text(decision.action, "recovery action")
    if action not in RECOVERY_ACTIONS:
        raise SnapshotError("unsupported recovery action")
    if type(decision.completed) is not tuple or type(decision.unwind) is not tuple:
        raise SnapshotError("completed and unwind steps must be tuples")
    # recover() only emits READY with a complete, unique, string-valued plan
    # prefix. A caller-owned dataclass can still carry empty, duplicated or
    # non-string steps; counting those as completed would publish a false
    # ready claim with an inflated completed_count.
    completed = decision.completed
    if any(type(step) is not str or not step for step in completed):
        raise SnapshotError("completed steps must be non-empty strings")
    if len(set(completed)) != len(completed):
        raise SnapshotError("completed steps must be unique")
    if action == READY and not completed:
        raise SnapshotError("ready recovery decision has no completed steps")
    safe_to_start = _flag(decision.safe_to_start, "safe_to_start")
    needs_rollback = _flag(decision.needs_rollback, "needs_rollback")
    # These flags are derived, not independent: a safe action never carries
    # unwind steps, and a rollback action is never safe to start. Trusting a
    # hostile-but-bounded override here could publish a false ready claim.
    if safe_to_start != (action in (START_FRESH, READY)):
        raise SnapshotError("safe_to_start disagrees with recovery action")
    if needs_rollback != bool(decision.unwind):
        raise SnapshotError("needs_rollback disagrees with unwind steps")
    return StartupView(
        action=action,
        safe_to_start=safe_to_start,
        needs_rollback=needs_rollback,
        completed_count=len(decision.completed),
        unwind_count=len(decision.unwind),
        reason=_bounded_text(decision.reason, "recovery reason"),
    )


def _session_view(reconciler):
    if not isinstance(reconciler, Reconciler):
        raise SnapshotError("session must be a Reconciler")
    state = reconciler.state
    if not isinstance(state, SessionState):
        raise SnapshotError("session state must be a SessionState")
    suspended = _flag(state.suspended, "session suspended")
    locked = _flag(state.locked, "session locked")
    label = _text(state.label, "session label")
    if label not in SESSION_LABELS:
        raise SnapshotError("unknown session state label")
    expected = "suspended" if suspended else ("locked" if locked else "active")
    if label != expected:
        raise SnapshotError("session state label disagrees with its flags")
    history = reconciler.history
    if type(history) is not tuple:
        raise SnapshotError("session history must be a tuple")
    statuses = []
    for outcome in history[-MAX_RECENT:]:
        if not isinstance(outcome, Outcome):
            raise SnapshotError("session history must hold Outcome values")
        status = _text(outcome.status, "session outcome status")
        if status not in SESSION_STATUSES:
            raise SnapshotError("unsupported session outcome status")
        statuses.append(status)
    return SessionView(
        label=label,
        suspended=suspended,
        locked=locked,
        accepted=_count(reconciler.accepted, "session accepted count"),
        recent_statuses=tuple(statuses),
    )


def _delivery_view(stats, notices):
    if not isinstance(stats, DeliveryStats):
        raise SnapshotError("delivery must be a DeliveryStats")
    if type(notices) is not tuple:
        raise SnapshotError("notices must be a tuple")
    for notice in notices:
        if not isinstance(notice, OverflowNotice):
            raise SnapshotError("notices must hold OverflowNotice entries")
    last_policy = None
    if notices:
        policy = notices[-1].policy
        if type(policy) is not str or not 0 < len(policy) <= MAX_POLICY_CHARS:
            raise SnapshotError("invalid overflow policy in notice history")
        last_policy = policy
    counts = {field: _count(getattr(stats, field), field)
              for field in COUNTER_FIELDS}
    return DeliveryView(
        notice_count=len(notices[-MAX_NOTICES:]),
        last_policy=last_policy,
        **counts,
    ), counts


def _derive_status(startup, session, counts):
    # An unsafe/fail-closed startup or a suspended session blocks readiness;
    # both outrank delivery anomalies. A locked session, pending rollback,
    # recent session churn and counted delivery problems are attention-worthy
    # but still a usable snapshot. This status describes only the supplied
    # state; there is no acceptance field to flip.
    if not startup.safe_to_start or startup.action == FAIL_CLOSED:
        return STATUS_BLOCKED
    if session.suspended:
        return STATUS_BLOCKED
    if (startup.needs_rollback or session.locked
            or session.recent_statuses
            or any(counts[field] for field in ANOMALY_FIELDS)):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(startup, session, delivery, notices=()):
    """Compose three already-tested value objects into one immutable record.

    ``notices`` is the bounded tuple returned by
    ``BoundedDeliveryChannel.overflow_notices()``; only the most recent
    ``MAX_NOTICES`` entries are counted. Every component is validated before
    any record is built, so a rejected input raises ``SnapshotError`` without
    a partial result. The source objects are never mutated.
    """
    startup_view = _startup_view(startup)
    session_view = _session_view(session)
    delivery_view, counts = _delivery_view(delivery, notices)
    return RecoveryReadinessSnapshot(
        schema=SCHEMA,
        status=_derive_status(startup_view, session_view, counts),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        observation=OBSERVATION_NOT_PERFORMED,
        startup=startup_view,
        session=session_view,
        delivery=delivery_view,
    )
