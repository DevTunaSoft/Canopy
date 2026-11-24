"""Bounded, immutable, host-facing reliability snapshot.

Composes the already-tested value objects produced by three independent
state models into one deterministic record:

* ``reliability/startup_checkpoints.py`` -- the durable ``RecoveryDecision``
  derived after a crash (action, completed/unwind steps, reason);
* ``reliability/event_delivery_loss.py`` -- the ``DeliveryStats`` counters and
  bounded ``OverflowNotice`` history of one delivery channel;
* ``windows/switcher_state.py`` -- the frozen ``SwitchState`` view of window
  selection.

The snapshot is a pure composition layer. It performs no I/O, clock or
randomness, spawns no threads and observes no OS or Qt state; the caller hands
it the value objects it already owns. Embedded collections are bounded
(notices, switcher order, reason text), every public view is immutable, and
two compositions of equal inputs are byte-for-byte identical.

This is evidence-shaped bookkeeping, not proof of a running desktop. MINT,
Qt and visual acceptance are deliberately reported as ``NOT_ESTABLISHED``;
no caller input can turn the record into an acceptance claim.
"""

from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.reliability.event_delivery_loss import (
    DeliveryStats, OverflowNotice)
from canopy_features.reliability.startup_checkpoints import (
    FAIL_CLOSED, READY, ROLLBACK, START_FRESH, RecoveryDecision)
from canopy_features.windows.switcher_state import SwitchState

SCHEMA = 1
RECOVERY_ACTIONS = frozenset({START_FRESH, READY, ROLLBACK, FAIL_CLOSED})
MAX_NOTICES = 8
MAX_WINDOWS = 64
MAX_REASON_CHARS = 160
MAX_ID_LENGTH = 128
MAX_POLICY_CHARS = 32
MAX_WINDOW_ID = 1_000_000_000_000

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"

_COUNTER_FIELDS = ("sent", "received", "delivered", "duplicates", "reordered",
                   "gaps", "missed", "dropped", "rejected")
_ANOMALY_FIELDS = ("dropped", "rejected", "gaps", "duplicates", "reordered",
                   "missed")


class SnapshotError(ValueError):
    """Invalid component, counter, flag or bound passed to ``compose``."""


@dataclass(frozen=True)
class StartupSnapshot:
    """Bounded projection of a durable ``RecoveryDecision``."""

    action: str
    safe_to_start: bool
    needs_rollback: bool
    completed_count: int
    unwind_count: int
    reason: str


@dataclass(frozen=True)
class DeliverySnapshot:
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
class SwitcherSnapshot:
    """Bounded projection of a frozen ``SwitchState`` view."""

    active: bool
    current: object
    selected: object
    window_count: int
    order: tuple


@dataclass(frozen=True)
class HostReliabilitySnapshot:
    """One deterministic, immutable record of host reliability state."""

    schema: int
    status: str
    acceptance: str
    startup: StartupSnapshot
    delivery: DeliverySnapshot
    switcher: SwitcherSnapshot

    @property
    def is_blocked(self) -> bool:
        return self.status == STATUS_BLOCKED

    def to_dict(self):
        """Return a fresh read-only view with a fixed, stable key order."""
        return MappingProxyType({
            "schema": self.schema,
            "status": self.status,
            "acceptance": self.acceptance,
            "startup": MappingProxyType({
                "action": self.startup.action,
                "safe_to_start": self.startup.safe_to_start,
                "needs_rollback": self.startup.needs_rollback,
                "completed_count": self.startup.completed_count,
                "unwind_count": self.startup.unwind_count,
                "reason": self.startup.reason,
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
            "switcher": MappingProxyType({
                "active": self.switcher.active,
                "current": self.switcher.current,
                "selected": self.switcher.selected,
                "window_count": self.switcher.window_count,
                "order": self.switcher.order,
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


def _tuple_of(value, field):
    if type(value) is not tuple:
        raise SnapshotError(field + " must be a tuple")
    return value


def _window_id(value):
    if value is None:
        return None
    if type(value) is int and 0 < value <= MAX_WINDOW_ID:
        return value
    if type(value) is str and 0 < len(value) <= MAX_ID_LENGTH:
        return value
    raise SnapshotError("invalid window id in switcher view")


def _startup_view(decision):
    if not isinstance(decision, RecoveryDecision):
        raise SnapshotError("startup must be a RecoveryDecision")
    if not isinstance(decision.action, str) or decision.action not in RECOVERY_ACTIONS:
        raise SnapshotError("unsupported recovery action")
    if type(decision.reason) is not str:
        raise SnapshotError("recovery reason must be a string")
    completed = _tuple_of(decision.completed, "completed")
    unwind = _tuple_of(decision.unwind, "unwind")
    # safe_to_start and needs_rollback are derived fields, not independent
    # inputs: the first follows the durable action, the second follows the
    # durable unwind tuple. A caller can construct a decision whose action is
    # safe while unwind steps remain, or subclass one whose overridden flags
    # hide a real rollback. Either case lets _derive_status publish a false
    # OK, so re-derive both and fail closed when they disagree.
    expected_safe = decision.action in (START_FRESH, READY)
    expected_rollback = bool(unwind)
    if expected_safe and expected_rollback:
        raise SnapshotError("startup action contradicts unwind steps")
    if (_flag(decision.safe_to_start, "safe_to_start") != expected_safe
            or _flag(decision.needs_rollback, "needs_rollback") != expected_rollback):
        raise SnapshotError("startup flags contradict the durable decision")
    return StartupSnapshot(
        action=decision.action,
        safe_to_start=expected_safe,
        needs_rollback=expected_rollback,
        completed_count=len(completed),
        unwind_count=len(unwind),
        reason=decision.reason[:MAX_REASON_CHARS],
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
              for field in _COUNTER_FIELDS}
    return DeliverySnapshot(
        notice_count=len(notices[-MAX_NOTICES:]),
        last_policy=last_policy,
        **counts,
    ), counts


def _switcher_view(state):
    if not isinstance(state, SwitchState):
        raise SnapshotError("switcher must be a SwitchState")
    order = _tuple_of(state.order, "switcher order")
    for item in order:
        _window_id(item)
    return SwitcherSnapshot(
        active=_flag(state.active, "switcher active"),
        current=_window_id(state.current),
        selected=_window_id(state.selected),
        window_count=len(order),
        order=order[:MAX_WINDOWS],
    )


def _derive_status(startup, counts):
    # A startup that cannot safely start blocks the record; it outranks any
    # delivery anomaly. Otherwise counted delivery health decides. A clean
    # channel with a safe startup is OK. There is no acceptance field: this
    # status describes only the supplied state, never a running desktop.
    if not startup.safe_to_start or startup.action == FAIL_CLOSED:
        return STATUS_BLOCKED
    if any(counts[field] for field in _ANOMALY_FIELDS):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(startup, delivery, notices, switcher):
    """Compose four already-tested value objects into one immutable record.

    ``notices`` is the bounded tuple returned by
    ``BoundedDeliveryChannel.overflow_notices()``. Only the most recent
    ``MAX_NOTICES`` entries are counted; the full history is never copied
    into the record. Every rejected input raises ``SnapshotError`` before any
    record is built, so no partial snapshot escapes.
    """
    startup_view = _startup_view(startup)
    delivery_view, counts = _delivery_view(delivery, notices)
    switcher_view = _switcher_view(switcher)
    return HostReliabilitySnapshot(
        schema=SCHEMA,
        status=_derive_status(startup_view, counts),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        startup=startup_view,
        delivery=delivery_view,
        switcher=switcher_view,
    )
