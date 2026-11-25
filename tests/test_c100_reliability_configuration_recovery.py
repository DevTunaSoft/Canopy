"""Offline unit tests for versioned config backup validation and recovery.

These tests use the real approved manifest and its exact PNGs from the source
tree. They do not compile Qt, start a desktop, or claim Linux Mint coverage.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from canopy_features.reliability import configuration_recovery as recovery
from tools.prepare_approved_art import MANIFEST, read_manifest

ROOT = Path(__file__).resolve().parents[1]
APPROVED = ROOT / "prototype" / "classic" / "assets" / "approved"
MANIFEST_NAME = "manifest.json"


class ConfigurationRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(
            prefix="canopy-config-recovery-test-"
        )
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.backup = self.base / "backup"
        shutil.copytree(APPROVED, self.backup)
        self.original_manifest = (self.backup / MANIFEST_NAME).read_bytes()
        self.manifest = read_manifest(self.backup / MANIFEST_NAME)

    def _write_manifest(self, root, manifest):
        (root / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def _assert_no_staging_left(self):
        self.assertEqual(list(self.base.glob(recovery.STAGING_PREFIX + "*")), [])

    def test_valid_backup_of_approved_config_passes(self):
        report = recovery.validate_backup(self.backup)
        self.assertTrue(report.ok, report.reason)
        self.assertEqual(report.version, 1)
        self.assertEqual(report.reason, "")
        self.assertEqual(len(report.files), 10)

    def test_corrupt_json_rejected_and_no_write_occurs(self):
        (self.backup / MANIFEST_NAME).write_bytes(self.original_manifest[:40])
        report = recovery.validate_backup(self.backup)
        self.assertFalse(report.ok)
        self.assertIn("corrupt config JSON", report.reason)

        active = self.base / "active"
        shutil.copytree(APPROVED, active)
        manifest_before = (active / MANIFEST_NAME).read_bytes()
        with self.assertRaisesRegex(recovery.RecoveryError, "corrupt config JSON"):
            recovery.recover(self.backup, active)
        self.assertEqual((active / MANIFEST_NAME).read_bytes(), manifest_before)
        self.assertEqual(list(self.base.glob("active.corrupt-*")), [])
        self._assert_no_staging_left()

    def test_interrupted_write_artifact_rejected(self):
        (self.backup / "icons" / "Browser_Option_3.png.part").write_bytes(
            b"partial write"
        )
        report = recovery.validate_backup(self.backup)
        self.assertFalse(report.ok)
        self.assertIn("interrupted write artifact", report.reason)
        with self.assertRaisesRegex(recovery.RecoveryError, "refusing recovery"):
            recovery.recover(self.backup, self.base / "active")
        self._assert_no_staging_left()

    def test_truncated_asset_is_rejected_as_incomplete_backup(self):
        asset = self.backup / "icons" / "Browser_Option_3.png"
        complete = asset.read_bytes()
        asset.write_bytes(complete[:16])
        report = recovery.validate_backup(self.backup)
        self.assertFalse(report.ok)
        self.assertIn("SHA-256", report.reason)
        with self.assertRaisesRegex(recovery.RecoveryError, "refusing recovery"):
            recovery.recover(self.backup, self.base / "active")
        self._assert_no_staging_left()

    def test_missing_asset_rejected(self):
        (self.backup / "wallpaper" / "canopy-wave-preview.png").unlink()
        report = recovery.validate_backup(self.backup)
        self.assertFalse(report.ok)
        self.assertIn("missing backup file", report.reason)

    def test_unsupported_version_rejected(self):
        manifest = dict(self.manifest)
        manifest["schema_version"] = 2
        self._write_manifest(self.backup, manifest)
        report = recovery.validate_backup(self.backup)
        self.assertFalse(report.ok)
        self.assertIn("unsupported config version: 2", report.reason)
        with self.assertRaisesRegex(recovery.RecoveryError, "refusing recovery"):
            recovery.recover(self.backup, self.base / "active")

    def test_manifest_diverging_from_trusted_lock_rejected(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest["icons"][0]["sha256"] = "0" * 64
        self._write_manifest(self.backup, manifest)
        report = recovery.validate_backup(self.backup)
        self.assertFalse(report.ok)

    def test_recover_restores_corrupt_active_and_quarantines_it(self):
        active = self.base / "active"
        shutil.copytree(APPROVED, active)
        corrupt = self.original_manifest[:40]
        (active / MANIFEST_NAME).write_bytes(corrupt)

        outcome = recovery.recover(self.backup, active)
        self.assertEqual(outcome.status, "restored")
        self.assertEqual(outcome.version, 1)
        self.assertIsNotNone(outcome.quarantined)
        self.assertEqual((outcome.quarantined / MANIFEST_NAME).read_bytes(), corrupt)
        self.assertEqual(
            (active / MANIFEST_NAME).read_bytes(), self.original_manifest
        )
        self.assertTrue(recovery.validate_backup(active).ok,
                        recovery.validate_backup(active).reason)
        self._assert_no_staging_left()

    def test_recover_is_no_op_for_already_valid_active(self):
        active = self.base / "active"
        shutil.copytree(APPROVED, active)
        before = (active / MANIFEST_NAME).read_bytes()

        outcome = recovery.recover(self.backup, active)
        self.assertEqual(outcome.status, "unchanged")
        self.assertIsNone(outcome.quarantined)
        self.assertEqual((active / MANIFEST_NAME).read_bytes(), before)
        self.assertEqual(list(self.base.glob("active.corrupt-*")), [])
        self._assert_no_staging_left()

    def test_failed_publish_rolls_quarantine_back_and_cleans_staging(self):
        active = self.base / "active"
        shutil.copytree(APPROVED, active)
        corrupt = self.original_manifest[:40]
        (active / MANIFEST_NAME).write_bytes(corrupt)

        real_check = recovery.check_exact

        def fail_inside_staging(path, digest):
            if any(recovery.STAGING_PREFIX in part for part in path.parts):
                raise OSError("simulated interrupted copy")
            return real_check(path, digest)

        with mock.patch.object(recovery, "check_exact", side_effect=fail_inside_staging):
            with self.assertRaisesRegex(recovery.RecoveryError,
                                        "simulated interrupted copy"):
                recovery.recover(self.backup, active)

        self.assertEqual((active / MANIFEST_NAME).read_bytes(), corrupt)
        self.assertEqual(list(self.base.glob("active.corrupt-*")), [])
        self._assert_no_staging_left()

    def test_symlink_destination_refused(self):
        target = self.base / "elsewhere"
        target.mkdir()
        link = self.base / "active"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlink creation unavailable: " + str(exc))
        with self.assertRaisesRegex(recovery.RecoveryError, "unsafe recovery"):
            recovery.recover(self.backup, link)
        self.assertTrue(link.is_symlink())


if __name__ == "__main__":
    unittest.main()
