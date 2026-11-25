"""Offline startup checkpoint tests: crashes, partial state, fail-closed reads."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canopy_features.reliability.startup_checkpoints import (
    COMPLETE, FAIL_CLOSED, MAX_STATE_BYTES, MAX_STEPS, READY, ROLLBACK,
    START_FRESH, CheckpointError, StartupCheckpoints,
)

STEPS = ("dock", "menu", "search")


class StartupCheckpointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="canopy-checkpoint-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "state"
        self.journal = StartupCheckpoints(self.directory, STEPS)

    def reopen(self):
        """Model a fresh process: no in-memory state, same durable directory."""
        return StartupCheckpoints(self.directory, STEPS)

    def raw(self, value):
        self.journal.path.write_bytes(value)

    def record(self):
        return json.loads(self.journal.path.read_text(encoding="utf-8"))

    def test_fresh_start_needs_no_rollback_and_writes_nothing(self):
        decision = self.journal.recover()
        self.assertEqual(decision.action, START_FRESH)
        self.assertTrue(decision.safe_to_start)
        self.assertFalse(decision.needs_rollback)
        self.assertEqual(decision.completed, ())
        self.assertFalse(self.journal.path.exists())

    def test_full_run_is_ready_after_restart(self):
        self.journal.begin()
        for step in STEPS:
            self.journal.complete(step)
        self.journal.finish()
        restarted = self.reopen().recover()
        self.assertEqual(restarted.action, READY)
        self.assertTrue(restarted.safe_to_start)
        self.assertEqual(restarted.completed, STEPS)
        self.assertEqual(restarted.unwind, ())
        self.assertEqual(self.record()["status"], COMPLETE)

    def test_crash_mid_startup_persists_durable_rollback_decision(self):
        self.journal.begin()
        self.journal.complete("dock")
        self.journal.complete("menu")

        restarted = self.reopen()
        decision = restarted.recover()
        self.assertEqual(decision.action, ROLLBACK)
        self.assertFalse(decision.safe_to_start)
        self.assertTrue(decision.needs_rollback)
        self.assertEqual(decision.completed, ("dock", "menu"))
        self.assertEqual(decision.unwind, ("menu", "dock"))
        self.assertEqual(decision.target, "menu")
        self.assertEqual(self.record()["status"], ROLLBACK)

        durable = self.journal.path.read_bytes()
        again = self.reopen().recover()
        self.assertEqual(again, decision)
        self.assertEqual(self.journal.path.read_bytes(), durable)
        with self.assertRaises(CheckpointError):
            restarted.complete("search")

    def test_crash_before_first_step_rolls_back_nothing(self):
        self.journal.begin()
        decision = self.reopen().recover()
        self.assertEqual(decision.action, ROLLBACK)
        self.assertEqual(decision.completed, ())
        self.assertEqual(decision.unwind, ())
        self.assertIsNone(decision.target)
        self.assertFalse(decision.needs_rollback)
        self.assertEqual(self.record()["status"], ROLLBACK)

    def test_crash_during_initialization_is_fail_closed(self):
        self.raw(b'{"schema": 1, "steps": ["dock", "menu"')
        durable = self.journal.path.read_bytes()
        decision = self.reopen().recover()
        self.assertEqual(decision.action, FAIL_CLOSED)
        self.assertFalse(decision.safe_to_start)
        self.assertEqual(decision.completed, ())
        self.assertEqual(decision.unwind, ())
        self.assertEqual(self.journal.path.read_bytes(), durable)
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ["startup.json"])

    def test_tampered_and_partial_states_never_become_progress(self):
        cases = {
            "wrong schema": {"schema": 2, "steps": list(STEPS),
                             "completed": ["dock"], "status": "IN_PROGRESS"},
            "non-prefix completed": {"schema": 1, "steps": list(STEPS),
                                     "completed": ["menu"], "status": "IN_PROGRESS"},
            "false completion": {"schema": 1, "steps": list(STEPS),
                                 "completed": ["dock"], "status": COMPLETE},
            "unknown status": {"schema": 1, "steps": list(STEPS),
                               "completed": [], "status": "MYSTERY"},
            "extra field": {"schema": 1, "steps": list(STEPS),
                            "completed": [], "status": "IN_PROGRESS", "extra": 1},
        }
        for label, payload in cases.items():
            with self.subTest(label):
                self.raw(json.dumps(payload).encode("utf-8"))
                durable = self.journal.path.read_bytes()
                decision = self.reopen().recover()
                self.assertEqual(decision.action, FAIL_CLOSED)
                self.assertFalse(decision.safe_to_start)
                self.assertEqual(decision.unwind, ())
                self.assertEqual(self.journal.path.read_bytes(), durable)

        with self.subTest("oversize"):
            self.raw(b"x" * (MAX_STATE_BYTES + 1))
            self.assertEqual(self.reopen().recover().action, FAIL_CLOSED)
        with self.subTest("non-utf8"):
            self.raw(b"\xff\xfe\x00")
            self.assertEqual(self.reopen().recover().action, FAIL_CLOSED)

    def test_failed_atomic_replace_does_not_invent_a_completed_step(self):
        self.journal.begin()
        self.journal.complete("dock")
        with patch("canopy_features.reliability.startup_checkpoints.os.replace",
                   side_effect=OSError("simulated crash before rename")):
            with self.assertRaises(CheckpointError):
                self.journal.complete("menu")

        self.assertEqual(self.record()["completed"], ["dock"])
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ["startup.json"])
        decision = self.reopen().recover()
        self.assertEqual(decision.completed, ("dock",))
        self.assertEqual(decision.unwind, ("dock",))

    def test_orphan_temp_from_crashed_write_is_ignored(self):
        (self.directory / ".canopy-startup-orphan.tmp").write_bytes(b"half written")
        decision = self.journal.recover()
        self.assertEqual(decision.action, START_FRESH)
        self.assertTrue((self.directory / ".canopy-startup-orphan.tmp").exists())
        self.assertFalse(self.journal.path.exists())

    def test_out_of_order_and_unknown_steps_cannot_mutate_state(self):
        self.journal.begin()
        self.journal.complete("dock")
        durable = self.journal.path.read_bytes()
        for bad in ("search", "DOCK", "", "dock"):
            with self.subTest(bad):
                with self.assertRaises(CheckpointError):
                    self.journal.complete(bad)
                self.assertEqual(self.journal.path.read_bytes(), durable)
        with self.assertRaises(CheckpointError):
            self.journal.begin()
        with self.assertRaises(CheckpointError):
            self.journal.finish()
        self.assertEqual(self.journal.path.read_bytes(), durable)

    def test_explicit_reset_after_fail_closed_allows_a_clean_run(self):
        self.raw(b"not json at all")
        self.assertEqual(self.reopen().recover().action, FAIL_CLOSED)
        self.journal.reset()
        self.assertEqual(self.record()["status"], "IN_PROGRESS")
        for step in STEPS:
            self.journal.complete(step)
        self.journal.finish()
        self.assertEqual(self.reopen().recover().action, READY)

    def test_tampered_state_is_refused_by_all_mutating_methods(self):
        self.raw(json.dumps({
            "schema": 1, "steps": list(STEPS), "completed": ["menu"],
            "status": "IN_PROGRESS",
        }).encode("utf-8"))
        durable = self.journal.path.read_bytes()
        with self.assertRaises(CheckpointError):
            self.journal.complete("dock")
        with self.assertRaises(CheckpointError):
            self.journal.finish()
        with self.assertRaises(CheckpointError):
            self.journal.begin()
        self.assertEqual(self.journal.path.read_bytes(), durable)

    def test_plan_bounds_and_names_are_validated(self):
        with self.assertRaises(CheckpointError):
            StartupCheckpoints(self.directory, ())
        with self.assertRaises(CheckpointError):
            StartupCheckpoints(self.directory, ["s%02d" % i for i in range(MAX_STEPS + 1)])
        with self.assertRaises(CheckpointError):
            StartupCheckpoints(self.directory, ("dock", "dock"))
        with self.assertRaises(CheckpointError):
            StartupCheckpoints(self.directory, ("Dock",))
        with self.assertRaises(CheckpointError):
            StartupCheckpoints(self.directory, ("../escape",))

    def test_symlink_state_paths_are_refused(self):
        outside = self.directory.parent / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        link = self.directory / "startup.json"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable to this unprivileged Windows test user")
        else:
            with self.assertRaises(CheckpointError):
                StartupCheckpoints(self.directory, STEPS)
            self.assertEqual(outside.read_text(encoding="utf-8"), "{}")

        linked_dir = self.directory.parent / "linked-state"
        try:
            linked_dir.symlink_to(self.directory, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlinks unavailable to this test user")
        else:
            with self.assertRaises(CheckpointError):
                StartupCheckpoints(linked_dir, STEPS)


if __name__ == "__main__":
    unittest.main()
