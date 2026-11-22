"""Offline unit tests for pre-upgrade old/new installation ownership checks."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from canopy_features.installer import upgrade_ownership as uo
from tools import register_classic_preview as installer

ROOT = Path(__file__).resolve().parents[1]
OLD = "1.4.0"
NEW = "2.0.0"


class UpgradeOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.home = base / "xdg data with spaces"
        self.home.mkdir()
        self.payload = base / "canopy-payload.bin"
        self.payload.write_bytes(b"new canopy release payload v2")
        self.digest = hashlib.sha256(self.payload.read_bytes()).hexdigest()
        self.manifest = base / "release.json"
        self.write_manifest(version=NEW, digest=self.digest)

    def write_manifest(self, *, version, digest, schema=1):
        data = {"schema": schema, "version": version, "payload_sha256": digest}
        self.manifest.write_text(json.dumps(data), encoding="utf-8")

    def install_old(self):
        # Build an owned registration with the tool's own marker schema; the
        # tool's install() rejects Windows paths (backslash in Exec), so this
        # stays cross-platform while still exercising its real status() check.
        p = installer.paths(self.home)
        for key in ("parent", "folder", "apps"):
            p[key].mkdir(parents=True, exist_ok=True)
        payload = (b"[Desktop Entry]\nType=Application\nVersion=1.0\n"
                   b"Name=Canopy Classic Preview\nExec=canopy-classic\n"
                   b"Terminal=false\nX-Canopy-Preview=true\n")
        marker = json.dumps({"schema": 1, "sha256": installer._sha(payload)},
                            sort_keys=True).encode("utf-8")
        p["desktop"].write_bytes(payload)
        p["manifest"].write_bytes(marker)
        self.assertEqual(installer.status(self.home), "INSTALLED")

    def verify(self, installed_version=OLD):
        return uo.verify_upgrade(self.home, installed_version,
                                 self.payload, self.manifest)

    def cli(self, installed_version=OLD):
        return subprocess.run(
            [sys.executable, "-m", "canopy_features.installer.upgrade_ownership",
             "verify", "--home", str(self.home),
             "--installed-version", installed_version,
             "--payload", str(self.payload), "--manifest", str(self.manifest)],
            cwd=str(ROOT), check=False, capture_output=True, text=True)

    def test_clean_upgrade_allowed_and_verifier_writes_nothing(self):
        self.install_old()
        marker = installer.paths(self.home)["manifest"]
        before = (marker.read_bytes(), self.payload.read_bytes(),
                  self.manifest.read_bytes())
        decision = self.verify()
        self.assertEqual(tuple(decision), (OLD, NEW))
        self.assertEqual((marker.read_bytes(), self.payload.read_bytes(),
                          self.manifest.read_bytes()), before)
        self.assertEqual(installer.status(self.home), "INSTALLED")

    def test_no_old_installation_refused(self):
        with self.assertRaisesRegex(uo.UpgradeError, "not owned: NOT_INSTALLED"):
            self.verify()

    def test_tampered_old_ownership_marker_refused(self):
        self.install_old()
        marker = installer.paths(self.home)["manifest"]
        marker.write_text(json.dumps({"schema": 1, "sha256": "0" * 64}),
                          encoding="utf-8")
        self.assertEqual(installer.status(self.home), "MODIFIED_OR_UNMANAGED")
        with self.assertRaisesRegex(uo.UpgradeError, "not owned"):
            self.verify()
        self.assertTrue(installer.paths(self.home)["desktop"].is_file())

    def test_tampered_candidate_manifest_digest_refused(self):
        self.install_old()
        self.write_manifest(version=NEW, digest="1" * 64)
        with self.assertRaisesRegex(uo.UpgradeError, "does not match"):
            self.verify()
        self.assertEqual(installer.status(self.home), "INSTALLED")

    def test_tampered_candidate_payload_refused(self):
        self.install_old()
        self.payload.write_bytes(b"tampered payload bytes")
        with self.assertRaisesRegex(uo.UpgradeError, "does not match"):
            self.verify()

    def test_version_rollback_refused(self):
        self.install_old()
        self.write_manifest(version="1.0.0", digest=self.digest)
        with self.assertRaisesRegex(uo.UpgradeError, "rollback refused"):
            self.verify()

    def test_equal_version_refused(self):
        self.install_old()
        self.write_manifest(version=OLD, digest=self.digest)
        with self.assertRaisesRegex(uo.UpgradeError, "rollback refused"):
            self.verify()

    def test_numeric_version_compare_not_lexical(self):
        self.install_old()
        self.write_manifest(version="1.10.0", digest=self.digest)
        decision = self.verify(installed_version="1.9.0")
        self.assertEqual(decision.new_version, "1.10.0")

    def test_rollback_of_higher_minor_refused(self):
        self.install_old()
        self.write_manifest(version="1.9.0", digest=self.digest)
        with self.assertRaisesRegex(uo.UpgradeError, "rollback refused"):
            self.verify(installed_version="1.10.0")

    def test_malformed_and_tampered_manifest_shapes_refused(self):
        self.install_old()
        cases = (
            {"schema": 2, "version": NEW, "payload_sha256": self.digest},
            {"schema": 1, "version": NEW, "payload_sha256": "not-hex"},
            {"schema": 1, "version": NEW, "payload_sha256": self.digest,
             "execute": "/bin/sh"},
            {"schema": 1, "version": "1.x", "payload_sha256": self.digest},
        )
        for data in cases:
            with self.subTest(data=data):
                self.manifest.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(uo.UpgradeError):
                    self.verify()

    def test_oversized_manifest_refused(self):
        self.install_old()
        self.manifest.write_bytes(b" " * (uo.MAX_MANIFEST_BYTES + 1))
        with self.assertRaisesRegex(uo.UpgradeError, "invalid candidate manifest"):
            self.verify()

    def test_invalid_installed_version_refused(self):
        self.install_old()
        with self.assertRaisesRegex(uo.UpgradeError, "invalid version"):
            self.verify(installed_version="v2")

    def test_cli_fail_closed_on_tampered_manifest(self):
        self.install_old()
        self.write_manifest(version=NEW, digest="1" * 64)
        process = self.cli()
        self.assertEqual(process.returncode, 1, process.stderr)
        self.assertIn("CANOPY_UPGRADE_REFUSED", process.stderr)

    def test_cli_allows_clean_upgrade(self):
        self.install_old()
        process = self.cli()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("CANOPY_UPGRADE_ALLOWED", process.stdout)
        self.assertIn(OLD + " -> " + NEW, process.stdout)


if __name__ == "__main__":
    unittest.main()
