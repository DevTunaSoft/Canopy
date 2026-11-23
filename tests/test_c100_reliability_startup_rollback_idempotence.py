"""Regression: repeated recover() after a crash before finish() must be stable.

A crash after the last complete() but before finish() leaves an IN_PROGRESS
journal whose completed list is a full plan. recover() must persist a
schema-valid ROLLBACK decision so a second recover() returns the same decision
instead of flipping to FAIL_CLOSED on a state the module's own validator
rejects.
"""
import json
from pathlib import Path
import tempfile
import unittest

from canopy_features.reliability.startup_checkpoints import (
    COMPLETE, FAIL_CLOSED, ROLLBACK, CheckpointError, StartupCheckpoints,
)

STEPS = ("dock", "menu", "search")


class StartupRollbackIdempotenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="canopy-checkpoint-idempotence-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "state"
        self.journal = StartupCheckpoints(self.directory, STEPS)

    def reopen(self):
        return StartupCheckpoints(self.directory, STEPS)

    def raw(self):
        return self.journal.path.read_bytes()

    def test_full_unfinished_startup_rollback_is_idempotent(self):
        self.journal.begin()
        for step in STEPS:
            self.journal.complete(step)
        # No finish(): the crash landed after the last durable step.
        first = self.reopen().recover()
        durable = self.raw()
        second = self.reopen().recover()
        self.assertEqual(first.action, ROLLBACK)
        self.assertEqual(first.unwind, tuple(reversed(STEPS)))
        self.assertEqual(second, first)
        self.assertEqual(second.action, ROLLBACK)
        self.assertEqual(self.raw(), durable)

    def test_persisted_rollback_record_is_schema_valid(self):
        self.journal.begin()
        for step in STEPS:
            self.journal.complete(step)
        self.reopen().recover()
        # A trusted ROLLBACK journal refuses new steps because it is closed,
        # not because its own validator rejects the bytes it just wrote.
        with self.assertRaisesRegex(CheckpointError, "not accepting steps"):
            self.reopen().complete("dock")
        self.assertEqual(json.loads(self.raw().decode("utf-8"))["status"], ROLLBACK)

    def test_partial_rollback_decision_and_bytes_are_unchanged(self):
        self.journal.begin()
        self.journal.complete("dock")
        first = self.reopen().recover()
        durable = self.raw()
        again = self.reopen().recover()
        self.assertEqual(again, first)
        self.assertEqual(again.unwind, ("dock",))
        self.assertEqual(self.raw(), durable)
        self.assertNotEqual(first.action, COMPLETE)

    def test_tampered_state_still_fails_closed_without_mutation(self):
        self.journal.path.write_bytes(json.dumps({
            "schema": 1, "steps": list(STEPS),
            "completed": list(STEPS), "status": "MYSTERY",
        }).encode("utf-8"))
        durable = self.raw()
        first = self.reopen().recover()
        second = self.reopen().recover()
        self.assertEqual(first.action, FAIL_CLOSED)
        self.assertEqual(second, first)
        self.assertEqual(self.raw(), durable)


if __name__ == "__main__":
    unittest.main()
