"""Regression tests for malformed completed steps in a READY recovery decision.

Audit slice (Agent A, tip 465f557): ``RecoveryDecision`` is a plain dataclass,
so a caller can hand ``compose`` a READY decision whose completed steps are
empty, duplicated or non-string. ``StartupCheckpoints.recover()`` can only
emit READY with a full, unique, string-valued plan prefix; a malformed READY
declaration must not publish ``STATUS_OK`` with a false completed count.

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


class ReadyCompletedStepsTests(unittest.TestCase):
    def test_ready_with_no_completed_steps_is_rejected(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.READY, (), (), None, "all startup steps are durable")
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(decision, _session(), _stats())

    def test_ready_with_duplicate_completed_steps_is_rejected(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.READY, ("shell", "shell"), (), None, "all durable")
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(decision, _session(), _stats())

    def test_ready_with_non_string_completed_step_is_rejected(self):
        decision = checkpoints.RecoveryDecision(
            checkpoints.READY, ("shell",), (), None, "all durable")
        object.__setattr__(decision, "completed", ("shell", 7))
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.compose(decision, _session(), _stats())

    def test_legitimate_decisions_still_compose(self):
        cases = (
            checkpoints.RecoveryDecision(
                checkpoints.READY, ("shell", "dock"), (), None, "all durable"),
            checkpoints.RecoveryDecision(
                checkpoints.START_FRESH, (), (), None, "no checkpoint"),
            checkpoints.RecoveryDecision(
                checkpoints.ROLLBACK, ("shell",), ("shell",),
                "shell", "partial startup"),
            checkpoints.RecoveryDecision(
                checkpoints.FAIL_CLOSED, (), (), None, "untrusted"),
        )
        for decision in cases:
            with self.subTest(action=decision.action):
                record = snapshot.compose(decision, _session(), _stats())
                self.assertEqual(record.startup.completed_count,
                                 len(decision.completed))


if __name__ == "__main__":
    unittest.main()
