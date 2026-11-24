"""RED/GREEN: durable checkpoint plan must match the caller's trusted plan.

A journal constructed for one startup plan must not report READY/safe_to_start
for a durable record that describes a *different* valid plan. The old recover()
cross-checked neither the durable plan nor its completed steps against the
trusted steps, so a foreign COMPLETE record produced a false startup claim.
"""

import json
import tempfile
import unittest
from pathlib import Path

from canopy_features.reliability import startup_checkpoints as s

TRUSTED = ("dock", "menu", "search")


class DurablePlanConsistencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="canopy-cp-plan-consistency-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "state"
        self.journal = s.StartupCheckpoints(self.directory, TRUSTED)

    def write_record(self, plan, completed, status):
        record = {
            "schema": s.SCHEMA,
            "steps": list(plan),
            "completed": list(completed),
            "status": status,
        }
        self.journal.path.write_bytes(json.dumps(record).encode("utf-8"))

    def assert_fail_closed_untouched(self):
        durable = self.journal.path.read_bytes()
        decision = self.journal.recover()
        self.assertEqual(decision.action, s.FAIL_CLOSED)
        self.assertFalse(decision.safe_to_start)
        self.assertEqual(decision.completed, ())
        self.assertEqual(decision.unwind, ())
        self.assertIsNone(decision.target)
        self.assertEqual(self.journal.path.read_bytes(), durable)

    def test_foreign_complete_plan_is_not_a_ready_claim(self):
        self.write_record(("alpha",), ("alpha",), s.COMPLETE)
        self.assert_fail_closed_untouched()

    def test_short_foreign_plan_cannot_invent_completion(self):
        self.write_record(("dock",), ("dock",), s.COMPLETE)
        self.assert_fail_closed_untouched()

    def test_long_foreign_plan_cannot_invent_extra_completion(self):
        self.write_record(TRUSTED + ("extra",), TRUSTED + ("extra",), s.COMPLETE)
        self.assert_fail_closed_untouched()

    def test_foreign_in_progress_plan_cannot_persist_a_foreign_rollback(self):
        self.write_record(("extra", "step"), ("extra",), s.IN_PROGRESS)
        self.assert_fail_closed_untouched()

    def test_foreign_rollback_plan_is_fail_closed(self):
        self.write_record(("alpha", "beta"), ("alpha",), s.ROLLBACK)
        self.assert_fail_closed_untouched()

    def test_matching_plan_still_recovers_ready(self):
        self.write_record(TRUSTED, TRUSTED, s.COMPLETE)
        decision = self.journal.recover()
        self.assertEqual(decision.action, s.READY)
        self.assertTrue(decision.safe_to_start)
        self.assertEqual(decision.completed, TRUSTED)

    def test_matching_partial_plan_still_recovers_rollback(self):
        self.write_record(TRUSTED, TRUSTED[:2], s.IN_PROGRESS)
        decision = self.journal.recover()
        self.assertEqual(decision.action, s.ROLLBACK)
        self.assertEqual(decision.unwind, ("menu", "dock"))

    def test_reset_after_foreign_plan_restores_trusted_plan(self):
        self.write_record(("alpha",), ("alpha",), s.COMPLETE)
        self.assertEqual(self.journal.recover().action, s.FAIL_CLOSED)
        self.journal.reset()
        for step in TRUSTED:
            self.journal.complete(step)
        self.journal.finish()
        self.assertEqual(self.journal.recover().action, s.READY)
        self.assertEqual(self.journal.recover().completed, TRUSTED)


if __name__ == "__main__":
    unittest.main()
