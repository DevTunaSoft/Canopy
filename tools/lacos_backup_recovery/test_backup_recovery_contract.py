"""Synthetic-only regression tests for the backup/recovery contract.

Run from the worktree root with::

    PYTHONPATH=<worktree-root> python -m unittest discover -s tools/lacos_backup_recovery -p 'test_*.py'

These tests use ``tempfile`` fixtures only. No real guest, deployment,
package state, mount or live owner-data path is touched.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from canopy_features.backup_recovery import (  # noqa: E402
    ALLOW_STAGED,
    INTEGRITY_FAILED,
    NOT_RUN,
    OWNER_DATA_CONFLICT,
    REFUSE,
    ROLLBACK_IN_FLIGHT,
    TARGET_NOT_CONTAINED,
    BackupRecoveryError,
    RollbackCheckpointView,
    SourceSpec,
    build_plan,
    canonical_bytes,
    parse_bounded_document,
    valid_label,
    valid_logical_path,
)
from canopy_features.backup_recovery.integrity import (  # noqa: E402
    MISMATCH,
    build_manifest,
    hash_file,
    verify_manifest,
)
from canopy_features.backup_recovery.checkpoint import (  # noqa: E402
    CheckpointJournal,
    RESUME,
    WAIT_ROLLBACK,
)
from canopy_features.backup_recovery.restore import (  # noqa: E402
    CORE_MUTATION_REFUSED,
    GUEST_NOT_RUN,
    evaluate_restore,
    valid_restore_root,
)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_fixtures import CAPTURED_AT, build_fixture  # noqa: E402

DEPLOYMENT = "deployment.20261128.0"
TARGET = "restore/candidate_a"


class ContractTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lacos-backup-test-")
        self.base = Path(self._tmp.name)
        self.fixture = build_fixture(self.base / "fixture")
        result = build_manifest(self.fixture.source_root, self.fixture.plan)
        self.assertIsNotNone(result.manifest)
        self.manifest = result.manifest
        self.verified = verify_manifest(self.manifest, self.fixture.source_root)
        self.assertTrue(self.verified.verified)
        self.journal = CheckpointJournal(self.fixture.state_dir)
        self.record = self.journal.begin(
            self.fixture.plan, self.fixture.provenance, self.manifest.digest())
        self.record = self.journal.seal()

    def tearDown(self):
        self._tmp.cleanup()

    def decision(self, **kwargs):
        defaults: dict = dict(
            checkpoint=self.record, plan=self.fixture.plan,
            provenance=self.fixture.provenance, manifest=self.manifest,
            integrity=self.verified, current_deployment_id=DEPLOYMENT,
            target_root=TARGET)
        defaults.update(kwargs)
        return evaluate_restore(**defaults)  # type: ignore[arg-type]

    def test_plan_is_canonical_and_bounded(self):
        self.assertEqual(
            self.fixture.plan.digest(),
            __import__("hashlib").sha256(
                canonical_bytes(self.fixture.plan.to_document())).hexdigest())
        self.assertTrue(valid_label("backup_plan_synthetic"))
        self.assertFalse(valid_label("Bad-Name"))
        self.assertTrue(valid_logical_path("owner_data/notes.txt"))
        self.assertFalse(valid_logical_path("../etc/passwd"))
        self.assertFalse(valid_logical_path("a\\b"))

    def test_duplicate_source_identity_refused(self):
        spec = SourceSpec("notes", "owner_data/notes.txt", "owner_data")
        with self.assertRaises(BackupRecoveryError):
            build_plan("other_plan", DEPLOYMENT, [spec, spec])

    def test_manifest_detects_byte_change(self):
        target = self.fixture.path_for("owner_data/notes.txt")
        target.write_bytes(target.read_bytes() + b"changed\n")
        result = verify_manifest(self.manifest, self.fixture.source_root)
        self.assertEqual(result.status, MISMATCH)
        self.assertFalse(result.verified)
        self.assertEqual(self.decision(integrity=result).action, REFUSE)
        self.assertIn(INTEGRITY_FAILED, self.decision(integrity=result).reasons)

    def test_hash_file_refuses_unsafe_bound(self):
        with self.assertRaises(BackupRecoveryError):
            hash_file(self.fixture.path_for("owner_data/notes.txt"), max_bytes=True)

    def test_checkpoint_recover_and_rollback(self):
        self.assertEqual(self.journal.recover().action, RESUME)
        self.assertTrue(self.journal.recover().may_restore)
        rolled = self.journal.mark_rollback("deployment.20261128.1")
        self.assertTrue(rolled.rollback_in_flight)
        self.assertEqual(self.journal.recover().action, WAIT_ROLLBACK)
        decision = self.decision(checkpoint=rolled)
        self.assertEqual(decision.action, REFUSE)
        self.assertIn(ROLLBACK_IN_FLIGHT, decision.reasons)
        settled = self.journal.finish_rollback("deployment.20261128.1")
        self.assertTrue(settled.sealed)
        self.assertEqual(self.journal.recover().action, RESUME)

    def test_restore_baseline_is_staged_only(self):
        decision = self.decision()
        self.assertEqual(decision.action, ALLOW_STAGED)
        self.assertTrue(decision.safe_to_apply)
        self.assertTrue(decision.steps[-1].startswith("REVIEW_REQUIRED"))
        self.assertTrue(all(
            "/usr/" not in step and "/home/" not in step for step in decision.steps))

    def test_owner_data_conflict_needs_ack(self):
        decision = self.decision(existing_targets=("notes",))
        self.assertEqual(decision.action, REFUSE)
        self.assertIn(OWNER_DATA_CONFLICT, decision.reasons)
        acked = self.decision(existing_targets=("notes",), acked_targets=("notes",))
        self.assertEqual(acked.action, ALLOW_STAGED)

    def test_deployment_change_refused(self):
        decision = self.decision(current_deployment_id="deployment.20261128.9")
        self.assertEqual(decision.action, REFUSE)
        self.assertIn("DEPLOYMENT_CHANGED", decision.reasons)

    def test_target_and_core_mutation_refused(self):
        self.assertFalse(valid_restore_root("/usr/bin"))
        self.assertFalse(valid_restore_root("restore/home/data"))
        self.assertIn(TARGET_NOT_CONTAINED,
                      self.decision(target_root="core/restore").reasons)
        core_plan = build_plan(
            "core_plan", DEPLOYMENT,
            [SourceSpec("core", "owner_data/notes.txt", "owner_data")])
        self.assertIn(CORE_MUTATION_REFUSED,
                      self.decision(plan=core_plan).reasons)

    def test_rollback_checkpoint_gate(self):
        pinned = RollbackCheckpointView(
            DEPLOYMENT, "a" * 64, True, CAPTURED_AT)
        self.assertEqual(self.decision(rollback_view=pinned).action, ALLOW_STAGED)
        unpinned = RollbackCheckpointView(
            DEPLOYMENT, "a" * 64, False, CAPTURED_AT)
        decision = self.decision(rollback_view=unpinned)
        self.assertEqual(decision.action, REFUSE)
        self.assertIn("ROLLBACK_CHECKPOINT_MISSING", decision.reasons)

    def test_real_guest_is_not_run(self):
        decision = self.decision(guest_class="REAL_GUEST_NOT_RUN")
        self.assertEqual(decision.action, NOT_RUN)
        self.assertIn(GUEST_NOT_RUN, decision.reasons)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(BackupRecoveryError):
            parse_bounded_document(b'{"a":1,"a":2}')

    def test_wrong_types_fail_closed(self):
        with self.assertRaises(BackupRecoveryError):
            build_plan("bad", DEPLOYMENT, "not-a-list")
        with self.assertRaises(BackupRecoveryError):
            evaluate_restore(
                checkpoint="not-a-record", plan=self.fixture.plan,
                provenance=self.fixture.provenance, manifest=self.manifest,
                integrity=self.verified, current_deployment_id=DEPLOYMENT,
                target_root=TARGET)


if __name__ == "__main__":
    unittest.main()
