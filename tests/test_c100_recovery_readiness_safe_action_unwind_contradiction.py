"""Regression: a startup action cannot be both safe and carrying unwind steps.

Audit contract (tip 90c0953): contradictory ready/degraded flags in the
bounded recovery-readiness snapshot. ``StartupCheckpoints.recover()`` emits
READY and START_FRESH only with an empty unwind tuple; a caller-owned
``RecoveryDecision`` can nevertheless pair a safe action with unwind steps.
The snapshot must fail closed instead of publishing a record with both
``safe_to_start=True`` and ``needs_rollback=True``.

All evidence here is SYNTHETIC (pure in-memory composition). No real startup,
delivery channel, Qt/Mint session or screen-reader path was exercised; those
remain NOT_RUN.
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


class SafeActionUnwindContradictionTests(unittest.TestCase):
    def test_ready_action_with_unwind_steps_is_rejected(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.READY, ("shell",), ("shell",), None,
            "all startup steps are durable")
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(decision, _session(), _stats())

    def test_start_fresh_action_with_unwind_steps_is_rejected(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.START_FRESH, (), ("shell",), None,
            "no durable checkpoint exists")
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(decision, _session(), _stats())

    def test_real_action_shapes_still_compose(self):
        cases = (
            checkpoints.RecoveryDecision(
                checkpoints.READY, ("shell",), (), None, "all durable"),
            checkpoints.RecoveryDecision(
                checkpoints.START_FRESH, (), (), None, "fresh start"),
            checkpoints.RecoveryDecision(
                checkpoints.ROLLBACK, ("shell",), ("shell",),
                "shell", "partial startup"),
            checkpoints.RecoveryDecision(
                checkpoints.FAIL_CLOSED, (), (), None, "untrusted"),
        )
        for decision in cases:
            with self.subTest(action=decision.action):
                record = snapshot.compose(decision, _session(), _stats())
                self.assertEqual(record.startup.needs_rollback,
                                 bool(decision.unwind))


if __name__ == "__main__":
    unittest.main()
