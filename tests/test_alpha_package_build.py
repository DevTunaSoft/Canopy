"""Targeted tests for deterministic staging and the PE-002 compile gate.

Synthetic fixtures only: no build, no Mint guest, no acceptance claim.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.alpha_package import alphactl  # noqa: E402
from tools.alpha_package import build_package  # noqa: E402

SOURCE = "90dd463dc96d70bae00cfe4b2391784a86fb0b12"


class AlphaPackageBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.binary = self.base / "bin" / "canopy-classic"
        self.binary.parent.mkdir()
        self.binary.write_bytes(b"#!/bin/sh\nprintf synthetic-payload\n")
        self.binary.chmod(0o755)
        self.sha = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.evidence = self.base / "PE-002.json"
        self.evidence.write_text(json.dumps({
            "id": "PE-002", "status": "COMPILED", "source_commit": SOURCE,
            "sha256": self.sha, "artifact": "synthetic-artifact",
        }), encoding="utf-8")

    def _build(self, name, *, binary=None, sha=None, evidence=None):
        return build_package.build_package(
            self.base / name, SOURCE, "alpha-build-test",
            binary or self.binary, sha or self.sha, evidence or self.evidence)

    def test_plan_stages_only_compile_not_run_metadata(self):
        result = build_package.plan_package(self.base / "plan", SOURCE,
                                            "alpha-plan-test")
        self.assertEqual(result["completion"], "COMPILE_NOT_RUN")
        manifest = json.loads((self.base / "plan/MANIFEST.json").read_text(
            encoding="utf-8"))
        self.assertEqual(manifest["build"], {
            "status": "COMPILE_NOT_RUN", "binary_sha256": None,
            "evidence_sha256": None, "artifact": None})
        self.assertEqual(manifest["payload"], {
            "path": None, "sha256": None, "size": None, "mode": None})
        self.assertNotIn("payload/canopy-classic", manifest["files"])
        self.assertEqual(alphactl.verify_package(self.base / "plan")["verdict"],
                         "PASS")

    def test_build_requires_matching_evidence_and_pin(self):
        result = self._build("good")
        self.assertEqual(result["completion"], "COMPILED_EVIDENCE_VERIFIED")
        self.assertEqual(result["binary_sha256"], self.sha)
        manifest = json.loads((self.base / "good/MANIFEST.json").read_text(
            encoding="utf-8"))
        self.assertEqual(manifest["build"]["source_commit"]
                         if "source_commit" in manifest["build"] else
                         manifest["source_commit"], SOURCE)
        self.assertEqual(manifest["build"]["binary_sha256"], self.sha)
        self.assertEqual(manifest["payload"]["path"], "payload/canopy-classic")
        with self.assertRaises(build_package.BuildError):
            self._build("bad-sha", sha="0" * 64)
        wrong = self.base / "wrong-evidence.json"
        wrong.write_text(json.dumps({
            "id": "PE-002", "status": "COMPILED", "sha256": "1" * 64,
        }), encoding="utf-8")
        with self.assertRaises(build_package.BuildError):
            self._build("bad-evidence", evidence=wrong)
        with self.assertRaises((build_package.BuildError,
                                alphactl.AlphaPackageError)):
            self._build("no-evidence", evidence=self.base / "absent.json")

    def test_staging_and_tarball_never_overwrite(self):
        build_package.plan_package(self.base / "once", SOURCE, "alpha-once")
        with self.assertRaises(build_package.BuildError):
            build_package.plan_package(self.base / "once", SOURCE, "alpha-once")
        tarball = self.base / "out.tar.gz"
        first = build_package.write_tarball(self.base / "once", tarball)
        self.assertEqual(first["verdict"], "PASS")
        with self.assertRaises(build_package.BuildError):
            build_package.write_tarball(self.base / "once", tarball)

    def test_tarball_is_deterministic_and_bounded(self):
        self._build("a")
        self._build("b")
        first = build_package.write_tarball(
            self.base / "a", self.base / "first.tar.gz")
        second = build_package.write_tarball(
            self.base / "b", self.base / "second.tar.gz")
        self.assertEqual(first["tarball_sha256"], second["tarball_sha256"])
        with tarfile.open(self.base / "first.tar.gz", "r:gz") as archive:
            names = archive.getnames()
            self.assertIn("payload/canopy-classic", names)
            self.assertIn("MANIFEST.json", names)
            self.assertIn("CHECKSUMS.sha256", names)
            self.assertTrue(all(info.mtime == 0 for info in archive.getmembers()))
            self.assertEqual(names, sorted(names))
        checksums = (self.base / "a/CHECKSUMS.sha256").read_bytes()
        self.assertTrue(checksums.endswith(b"\n"))
        self.assertNotIn(b"\r", checksums)


if __name__ == "__main__":
    unittest.main()
