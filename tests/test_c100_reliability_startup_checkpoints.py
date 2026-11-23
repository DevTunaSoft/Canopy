"""Offline tests for startup checkpoints and no-corruption rollback decisions.

No Qt, compositor, desktop session or Linux Mint is started here. Real Mint
acceptance and compiled Qt integration stay NOT RUN until wired separately.
"""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from canopy_features.reliability.startup_checkpoints import (
    CLASSIC_STARTUP_STEPS,
    MAX_JOURNAL_BYTES,
    MAX_STATE_BYTES,
    CheckpointError,
    RollbackDecision,
    StartupCheckpoints,
)

ROOT = Path(__file__).resolve().parents[1]
MAIN_CPP = ROOT / "prototype" / "classic" / "main.cpp"


class ModelFidelityTests(unittest.TestCase):
    def test_step_model_follows_compiled_startup_markers(self):
        text = MAIN_CPP.read_text(encoding="utf-8")
        markers = (
            "const QStringList args = QCoreApplication::arguments();",
            "if (!verifyExactArtwork(requested, !landscapeMode, &error))",
            "QQmlApplicationEngine engine;",
            'engine.load(QUrl(QStringLiteral("qrc:/Canopy/Classic/Main.qml")));',
            'qInfo() << "CANOPY_CLASSIC_WINDOW_READY";',
        )
        positions = [text.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(positions), len(CLASSIC_STARTUP_STEPS))

    def test_invalid_step_allowlists_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "startup.journal"
            for steps in ((), ("ok", "ok"), ("Bad Name",), ("9bad",),
                          ("a" * 49,)):
                with self.subTest(steps=steps):
                    with self.assertRaises(CheckpointError):
                        StartupCheckpoints(path, steps)

    def test_safe_property_rejects_a_forged_target(self):
        forged = RollbackDecision("load_qml", ("parse_args",), (), "CLEAN")
        self.assertFalse(forged.safe)


class DurableCheckpointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "startup.journal"
        self.manager = StartupCheckpoints(self.path)
        self.state = b"top-secret-state-value"

    def run_steps(self, count):
        for step in CLASSIC_STARTUP_STEPS[:count]:
            self.manager.begin(step)
            self.manager.commit(step, self.state)

    def records(self):
        return [line for line in self.path.read_bytes().splitlines() if line]

    def test_commit_is_durable_and_stores_only_a_digest(self):
        self.run_steps(2)
        data = self.path.read_bytes()
        self.assertNotIn(b"top-secret", data)
        self.assertEqual(len(self.records()), 4)
        commits = [json.loads(line) for line in self.records()
                   if json.loads(line)["phase"] == "commit"]
        self.assertEqual(
            [entry["state_sha256"] for entry in commits],
            [hashlib.sha256(self.state).hexdigest()] * 2,
        )
        decision = StartupCheckpoints(self.path).decide()
        self.assertEqual(decision.reason, "CLEAN")
        self.assertEqual(decision.completed, CLASSIC_STARTUP_STEPS[:2])
        self.assertEqual(decision.target, "verify_artwork")
        self.assertEqual(decision.discarded, ())
        self.assertTrue(decision.safe)

    def test_crash_after_intent_rolls_back_to_last_committed_step(self):
        self.run_steps(2)
        # Intent is durable, but the step crashes before its commit record.
        self.manager.begin("create_engine")
        restarted = StartupCheckpoints(self.path)
        decision = restarted.decide()
        self.assertEqual(decision.reason, "PARTIAL_STATE")
        self.assertEqual(decision.target, "verify_artwork")
        self.assertEqual(decision.completed, CLASSIC_STARTUP_STEPS[:2])
        self.assertEqual(decision.discarded, ("create_engine",))
        self.assertTrue(decision.safe)

        rolled = restarted.rollback_to(decision.target)
        self.assertEqual(rolled.reason, "ROLLED_BACK")
        self.assertEqual(rolled.completed, CLASSIC_STARTUP_STEPS[:2])
        after = StartupCheckpoints(self.path).decide()
        self.assertEqual(after.reason, "CLEAN")
        self.assertEqual(after.discarded, ())
        self.assertEqual(len(self.records()), 4)

    def test_torn_temp_write_is_ignored_and_cleaned(self):
        self.run_steps(1)
        temp = self.manager.temp_path
        with mock.patch("os.replace", side_effect=OSError("simulated power loss")):
            with self.assertRaises(OSError):
                self.manager.begin("verify_artwork")
        self.assertTrue(temp.exists())

        restarted = StartupCheckpoints(self.path)
        decision = restarted.decide()
        self.assertEqual(decision.reason, "CLEAN")
        self.assertEqual(decision.target, "parse_args")
        self.assertEqual(decision.completed, ("parse_args",))
        self.assertFalse(temp.exists())
        self.assertEqual(len(self.records()), 2)

    def test_partial_step_cannot_be_committed_out_of_sequence(self):
        self.run_steps(1)
        self.manager.begin("verify_artwork")
        restarted = StartupCheckpoints(self.path)
        with self.assertRaises(CheckpointError):
            restarted.commit("load_qml", self.state)
        self.assertEqual(restarted.decide().target, "parse_args")
        restarted.commit("verify_artwork", self.state)
        self.assertEqual(
            StartupCheckpoints(self.path).decide().target, "verify_artwork",
        )

    def test_bounds_and_ordering_reject_without_publishing_bad_state(self):
        manager = StartupCheckpoints(self.path)
        self.assertEqual(manager.decide().reason, "NO_JOURNAL")
        with self.assertRaises(CheckpointError):
            manager.begin("verify_artwork")
        with self.assertRaises(CheckpointError):
            manager.commit("parse_args", self.state)
        self.assertEqual(manager.decide().reason, "NO_JOURNAL")

        manager.begin("parse_args")
        self.assertEqual(manager.decide().reason, "PARTIAL_STATE")
        with self.assertRaises(CheckpointError):
            manager.commit("parse_args", b"x" * (MAX_STATE_BYTES + 1))
        manager.abort()
        self.assertEqual(manager.decide().reason, "NO_JOURNAL")
        self.assertFalse(manager.temp_path.exists())

    def test_rollback_target_must_be_a_committed_step(self):
        self.run_steps(2)
        manager = StartupCheckpoints(self.path)
        with self.assertRaises(CheckpointError):
            manager.rollback_to("load_qml")
        self.assertEqual(manager.decide().target, "verify_artwork")
        rolled = manager.rollback_to("parse_args")
        self.assertEqual(rolled.completed, ("parse_args",))
        after = StartupCheckpoints(self.path).decide()
        self.assertEqual(after.reason, "CLEAN")
        self.assertEqual(after.target, "parse_args")
        self.assertEqual(len(self.records()), 2)


class CorruptionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "startup.journal"
        self.manager = StartupCheckpoints(self.path)
        for step in CLASSIC_STARTUP_STEPS[:2]:
            self.manager.begin(step)
            self.manager.commit(step, b"state")
        self.original = self.path.read_bytes()

    def write_and_assert_cold_start(self, payload, label):
        with self.subTest(case=label):
            self.path.write_bytes(payload)
            restarted = StartupCheckpoints(self.path)
            decision = restarted.decide()
            self.assertEqual(decision.reason, "CORRUPT_JOURNAL")
            self.assertIsNone(decision.target)
            self.assertEqual(decision.completed, ())
            self.assertTrue(decision.safe)
            restarted.rollback_to()
            self.assertEqual(
                StartupCheckpoints(self.path).decide().reason, "NO_JOURNAL",
            )

    def test_torn_tampered_and_reordered_journals_fail_closed(self):
        lines = self.original.splitlines()
        first = json.loads(lines[0])
        first["sha256"] = ("0" if first["sha256"][0] != "0" else "1") \
            + first["sha256"][1:]
        tampered = [json.dumps(first, sort_keys=True, separators=(",", ":"))
                    .encode("utf-8")] + lines[1:]
        cases = (
            ("torn_tail", self.original[:-5]),
            ("trailing_garbage", self.original + b"garbage\n"),
            ("checksum_flip", b"\n".join(tampered) + b"\n"),
            ("reordered_records", b"\n".join(reversed(lines)) + b"\n"),
        )
        for label, payload in cases:
            self.write_and_assert_cold_start(payload, label)

    def test_oversized_journal_is_rejected_without_loading_it(self):
        self.write_and_assert_cold_start(
            b"x" * (MAX_JOURNAL_BYTES + 1), "oversized",
        )


if __name__ == "__main__":
    unittest.main()
