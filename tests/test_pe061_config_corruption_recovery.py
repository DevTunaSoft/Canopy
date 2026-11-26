"""PE-061: bounded corrupt-config recovery for installer/session paths.

Targeted host-side tests only. Every fixture uses a bounded temporary
directory and a synthetic marker string; no real credential, host session or
compiled Qt/Mint behavior is exercised or claimed.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from canopy_features.reliability import bounded_config_recovery as recovery
from canopy_features.reliability.startup_checkpoints import (
    CheckpointError, FAIL_CLOSED, MAX_STATE_BYTES, StartupCheckpoints,
)
from canopy_features.installer import uninstall_integrity as uninstall
from tools import register_classic_preview as menu

# Synthetic marker only: never a credential, never logged.
MARKER = "SYNTHETIC_PE061_MARKER_9F2A"
STEPS = ("dock", "menu", "search")


class BoundedConfigReadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="canopy-pe061-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "installer" / "ownership.json"
        self.path.parent.mkdir(parents=True)

    def test_corrupt_config_returns_fail_closed_status_with_bounded_raw_bytes(self):
        raw = b'{"schema":1,"note":"' + MARKER.encode("ascii") + b'"}\x00'
        self.path.write_bytes(raw)

        loaded = recovery.read_bounded_config(self.path, max_bytes=4096)

        self.assertEqual(loaded.status, "CORRUPT")
        self.assertIsNone(loaded.document)
        self.assertEqual(loaded.raw, raw)

    def test_valid_config_returns_document_and_bounded_raw(self):
        payload = {"schema": 1, "files": {}}
        raw = json.dumps(payload).encode("utf-8")
        self.path.write_bytes(raw)

        loaded = recovery.read_bounded_config(self.path, max_bytes=4096)

        self.assertEqual(loaded.status, "OK")
        self.assertEqual(loaded.document, payload)
        self.assertEqual(loaded.raw, raw)

    def test_oversize_config_is_bounded_and_never_retained(self):
        self.path.write_bytes(b"x" * 4200)
        with mock.patch("pathlib.Path.read_bytes",
                        side_effect=AssertionError("unbounded read")):
            loaded = recovery.read_bounded_config(self.path, max_bytes=4096)
        self.assertEqual(loaded.status, "OVERSIZE")
        self.assertIsNone(loaded.document)
        self.assertEqual(loaded.raw, b"")

    def test_duplicate_json_keys_fail_closed_and_keep_raw_bytes(self):
        raw = b'{"schema":1,"schema":2,"files":{}}'
        self.path.write_bytes(raw)

        loaded = recovery.read_bounded_config(self.path, max_bytes=4096)

        self.assertEqual(loaded.status, "CORRUPT")
        self.assertIsNone(loaded.document)
        self.assertEqual(loaded.raw, raw)

    def test_symlinked_config_path_is_refused_without_reading_target(self):
        target = self.root / "outside.json"
        target.write_bytes(b'{"schema":1,"files":{}}')
        try:
            self.path.symlink_to(target)
        except (OSError, NotImplementedError, ValueError) as exc:
            self.skipTest("symlinks unavailable on this host: %s" % exc)

        loaded = recovery.read_bounded_config(self.path, max_bytes=4096)

        self.assertEqual(loaded.status, "UNSAFE_PATH")
        self.assertIsNone(loaded.document)
        self.assertEqual(loaded.raw, b"")
        self.assertEqual(target.read_bytes(), b'{"schema":1,"files":{}}')


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="canopy-pe061-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "installer" / "ownership.json"
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"active-config")

    def test_quarantine_rotates_bounded_snapshots(self):
        for raw in (b"first", b"second", b"third", b"fourth"):
            recovery.quarantine_config(self.path, raw, max_bytes=4096)

        names = sorted(p.name for p in self.path.parent.iterdir()
                       if ".corrupt" in p.name)
        self.assertEqual(names, ["ownership.json.corrupt",
                                 "ownership.json.corrupt.1",
                                 "ownership.json.corrupt.2"])
        self.assertEqual(
            Path(str(self.path) + ".corrupt").read_bytes(), b"fourth")
        self.assertEqual(
            Path(str(self.path) + ".corrupt.1").read_bytes(), b"third")
        self.assertEqual(
            Path(str(self.path) + ".corrupt.2").read_bytes(), b"second")
        self.assertEqual(self.path.read_bytes(), b"active-config")

    def test_quarantine_refuses_oversize_raw_without_writes(self):
        with self.assertRaises(recovery.ConfigRecoveryError):
            recovery.quarantine_config(self.path, b"x" * 4097, max_bytes=4096)
        self.assertEqual(self.path.read_bytes(), b"active-config")
        self.assertEqual([p.name for p in self.path.parent.iterdir()],
                         ["ownership.json"])

    def test_quarantine_refuses_symlinked_snapshot_target(self):
        target = self.root / "outside.json"
        target.write_bytes(b"other-data")
        alias = Path(str(self.path) + ".corrupt")
        try:
            alias.symlink_to(target)
        except (OSError, NotImplementedError, ValueError) as exc:
            self.skipTest("symlinks unavailable on this host: %s" % exc)

        with self.assertRaises(recovery.ConfigRecoveryError):
            recovery.quarantine_config(self.path, b"corrupt", max_bytes=4096)
        self.assertEqual(target.read_bytes(), b"other-data")
        self.assertEqual(self.path.read_bytes(), b"active-config")

    def test_failed_quarantine_leaves_existing_snapshots_unchanged(self):
        recovery.quarantine_config(self.path, b"older", max_bytes=4096)
        before = Path(str(self.path) + ".corrupt").read_bytes()
        with mock.patch("canopy_features.reliability.bounded_config_recovery"
                        ".os.replace", side_effect=OSError("simulated")):
            with self.assertRaises(recovery.ConfigRecoveryError):
                recovery.quarantine_config(self.path, b"newer", max_bytes=4096)
        self.assertEqual(Path(str(self.path) + ".corrupt").read_bytes(), before)
        self.assertEqual(self.path.read_bytes(), b"active-config")
        leftovers = [p.name for p in self.path.parent.iterdir()
                     if p.name.startswith(".canopy-config-recovery-")]
        self.assertEqual(leftovers, [])


class InstallerManifestRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="canopy-pe061-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest = menu.paths(self.root)["manifest"]
        self.manifest.parent.mkdir(parents=True)
        (self.root / "install").mkdir()

    def test_corrupt_manifest_is_quarantined_and_replaced_with_empty_defaults(self):
        raw = b'{"schema":1,"files":{"a":"' + MARKER.encode("ascii") + b'"}}\x00'
        self.manifest.write_bytes(raw)

        outcome = uninstall.recover_manifest(self.manifest)

        self.assertEqual(outcome.status, "DEFAULTS_APPLIED")
        self.assertEqual(outcome.manifest, {"schema": 1, "files": {}})
        self.assertEqual(
            Path(str(self.manifest) + ".corrupt").read_bytes(), raw)
        self.assertEqual(
            json.loads(self.manifest.read_text(encoding="utf-8")),
            {"schema": 1, "files": {}})
        self.assertNotIn(MARKER, str(outcome))
        plan = uninstall.plan_uninstall(self.root / "install", outcome.manifest)
        self.assertTrue(plan.safe)
        self.assertEqual(plan.remove_files, ())

    def test_valid_manifest_is_unchanged_and_not_snapshotted(self):
        payload = {"schema": 1, "files": {"apps/x.desktop": "a" * 64}}
        raw = json.dumps(payload).encode("utf-8")
        self.manifest.write_bytes(raw)

        outcome = uninstall.recover_manifest(self.manifest)

        self.assertEqual(outcome.status, "UNCHANGED")
        self.assertEqual(outcome.manifest, payload)
        self.assertEqual(self.manifest.read_bytes(), raw)
        self.assertEqual([p.name for p in self.manifest.parent.iterdir()],
                         ["ownership.json"])

    def test_oversize_manifest_is_refused_without_writes(self):
        raw = b"x" * (uninstall.MAX_MANIFEST_BYTES + 8)
        self.manifest.write_bytes(raw)

        with self.assertRaises(uninstall.UninstallIntegrityError):
            uninstall.recover_manifest(self.manifest)

        self.assertEqual(self.manifest.read_bytes(), raw)
        self.assertEqual([p.name for p in self.manifest.parent.iterdir()],
                         ["ownership.json"])

    def test_duplicate_key_manifest_fails_closed_on_read(self):
        self.manifest.write_bytes(
            b'{"schema":1,"schema":2,"files":{}}')

        with self.assertRaises(uninstall.UninstallIntegrityError):
            uninstall.read_manifest(self.manifest)

    def test_invalid_schema_manifest_is_quarantined_and_defaulted(self):
        raw = b'{"schema":2,"files":{}}'
        self.manifest.write_bytes(raw)

        outcome = uninstall.recover_manifest(self.manifest)

        self.assertEqual(outcome.status, "DEFAULTS_APPLIED")
        self.assertEqual(outcome.manifest, {"schema": 1, "files": {}})
        self.assertEqual(
            Path(str(self.manifest) + ".corrupt").read_bytes(), raw)


class SessionCheckpointRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="canopy-pe061-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / "state"
        self.journal = StartupCheckpoints(self.directory, STEPS)

    def test_reset_after_corrupt_checkpoint_keeps_bounded_snapshot(self):
        raw = b'{"schema":1,"steps":["dock"'
        self.journal.path.write_bytes(raw)
        self.assertEqual(self.journal.recover().action, FAIL_CLOSED)

        self.journal.reset()

        snapshot = Path(str(self.journal.path) + ".corrupt")
        self.assertEqual(snapshot.read_bytes(), raw)
        self.assertEqual(json.loads(self.journal.path.read_text())["status"],
                         "IN_PROGRESS")
        self.assertEqual(StartupCheckpoints(self.directory, STEPS).recover()
                         .action, "ROLLBACK")

    def test_repeated_corruption_is_capped_three_snapshots(self):
        for marker in (b"one", b"two", b"three", b"four"):
            self.journal.path.write_bytes(marker)
            StartupCheckpoints(self.directory, STEPS).recover()
            self.journal.reset()
        names = sorted(p.name for p in self.directory.iterdir()
                       if ".corrupt" in p.name)
        self.assertEqual(names, ["startup.json.corrupt",
                                 "startup.json.corrupt.1",
                                 "startup.json.corrupt.2"])
        self.assertEqual(
            Path(str(self.journal.path) + ".corrupt").read_bytes(), b"four")
        self.assertEqual(
            Path(str(self.journal.path) + ".corrupt.2").read_bytes(), b"two")

    def test_oversize_checkpoint_is_never_overwritten(self):
        raw = b"x" * (MAX_STATE_BYTES + 8)
        self.journal.path.write_bytes(raw)
        self.assertEqual(self.journal.recover().action, FAIL_CLOSED)

        with self.assertRaises(CheckpointError):
            self.journal.reset()

        self.assertEqual(self.journal.path.read_bytes(), raw)
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()),
                         ["startup.json"])

    def test_tampered_valid_json_is_quarantined_before_reset(self):
        raw = json.dumps({
            "schema": 1, "steps": list(STEPS),
            "completed": ["menu"], "status": "IN_PROGRESS",
        }).encode("utf-8")
        self.journal.path.write_bytes(raw)
        self.assertEqual(self.journal.recover().action, FAIL_CLOSED)

        self.journal.reset()

        self.assertEqual(
            Path(str(self.journal.path) + ".corrupt").read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
