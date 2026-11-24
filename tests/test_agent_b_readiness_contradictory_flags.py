"""Regression tests for contradictory readiness flags in the snapshot layer.

Audit slice (Agent B, tip 8e5d59f): a caller-owned ``RecoveryDecision`` can
carry bounded booleans that disagree with its action and unwind steps. The
snapshot must refuse such a record instead of publishing a false ready/safe
status. These hostile values are plain Python bools returned by a subclass:
no I/O, unbounded input or raw exceptions are involved.

Resource note: all evidence here is SYNTHETIC (pure in-memory composition).
No real startup, delivery channel, Qt/Mint session or screen-reader path was
exercised; those remain NOT_RUN.
"""

import unittest

from canopy_features.reliability import event_delivery_loss as delivery
from canopy_features.reliability import lock_session_events as lock
from canopy_features.reliability import recovery_readiness_snapshot as snapshot
from canopy_features.reliability import startup_checkpoints as checkpoints


def _session():
    return lock.Reconciler(initial_locked=False)


def _stats():
    return delivery.DeliveryStats(0, 0, 0, 0, 0, 0, 0, 0, 0)


class _RollbackClaimingSafe(checkpoints.RecoveryDecision):
    """A hostile-but-bounded decision: ROLLBACK with safe_to_start=True."""

    @property
    def safe_to_start(self):
        return True

    @property
    def needs_rollback(self):
        return False


class _SafeActionHidingUnwind(checkpoints.RecoveryDecision):
    """A hostile-but-bounded decision: unwind steps but needs_rollback=False."""

    @property
    def needs_rollback(self):
        return False


class ReadinessContradictoryFlagsTests(unittest.TestCase):
    def test_rollback_action_cannot_claim_safe_to_start(self):
        decision = _RollbackClaimingSafe(
            checkpoints.ROLLBACK, ("shell", "dock"), ("dock", "shell"),
            "dock", "partial startup")
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(decision, _session(), _stats())

    def test_safe_action_cannot_hide_unwind_steps(self):
        decision = _SafeActionHidingUnwind(
            checkpoints.START_FRESH, (), ("shell",), None, "fresh start")
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(decision, _session(), _stats())

    def test_genuine_decision_flags_still_compose(self):
        cases = (
            checkpoints.RecoveryDecision(checkpoints.READY, ("shell",), (),
                                         None, "all durable"),
            checkpoints.RecoveryDecision(checkpoints.START_FRESH, (), (),
                                         None, "no checkpoint"),
            checkpoints.RecoveryDecision(checkpoints.ROLLBACK, ("shell",),
                                         ("shell",), "shell", "partial"),
            checkpoints.RecoveryDecision(checkpoints.FAIL_CLOSED, ("shell",),
                                         (), "shell", "untrusted"),
        )
        for decision in cases:
            with self.subTest(action=decision.action):
                record = snapshot.compose(decision, _session(), _stats())
                self.assertEqual(record.startup.safe_to_start,
                                 decision.action in (checkpoints.START_FRESH,
                                                     checkpoints.READY))
                self.assertEqual(record.startup.needs_rollback,
                                 bool(decision.unwind))
                self.assertEqual(record.acceptance,
                                 snapshot.ACCEPTANCE_NOT_ESTABLISHED)

    def test_duplicate_and_stale_notices_do_not_change_status(self):
        # Bounded hostile notice generations are counted, but cannot create a
        # ready claim from clean delivery counters.
        notices = (
            delivery.OverflowNotice(9, "drop_oldest", 1),
            delivery.OverflowNotice(1, "reject_new", 1),
            delivery.OverflowNotice(1, "drop_oldest", 1),
        )
        decision = checkpoints.RecoveryDecision(
            checkpoints.READY, ("shell",), (), None, "all durable")
        record = snapshot.compose(decision, _session(), _stats(), notices)
        self.assertEqual(record.delivery.notice_count, len(notices))
        self.assertEqual(record.status, snapshot.STATUS_OK)


if __name__ == "__main__":
    unittest.main()
