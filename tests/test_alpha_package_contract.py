"""Targeted contract tests for the standalone alpha lifecycle controller.

All filesystem fixtures are temporary. Compiled input here is a synthetic
text file: these tests prove package/state logic only (SYNTHETIC), not a
compile, a Linux Mint session or owner acceptance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.alpha_package import alphactl  # noqa: E402
from tools.alpha_package import build_package  # noqa: E402

SOURCE = "90dd463dc96d70bae00cfe4b2391784a86fb0b12"


class AlphaPackageContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.binary = base / "build" / "canopy-classic"
        self.binary.parent.mkdir()
        self.binary.write_bytes(b"#!/bin/sh\nprintf synthetic\n")
        self.binary.chmod(0o755)
        self.binary_sha = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.evidence = base / "evidence.json"
        self.evidence.write_text(json.dumps({
            "id": "PE-002", "status": "COMPILED", "source_commit": SOURCE,
            "sha256": self.binary_sha, "artifact": "synthetic-pin",
        }), encoding="utf-8")
        self.staging = base / "staging"
        build_package.build_package(self.staging, SOURCE, "test-alpha",
                                    self.binary, self.binary_sha, self.evidence)
        self.home = base / "home"
        self.home.mkdir()
        self.owned = alphactl._owned(str(self.home))
        self.state = alphactl._state_path(str(self.home))

    def _install(self):
        result = alphactl.apply_install(self.staging, self.home)
        self.assertEqual(result["verdict"], "PASS", result)
        return result

    def test_plan_mode_has_no_binary_and_install_refuses_it(self):
        stage = Path(self.tmp.name) / "plan-only"
        result = build_package.plan_package(stage, SOURCE, "plan-alpha")
        self.assertEqual(result["completion"], "COMPILE_NOT_RUN")
        manifest = json.loads((stage / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["build"]["status"], "COMPILE_NOT_RUN")
        self.assertIsNone(manifest["payload"]["sha256"])
        self.assertFalse((stage / "payload").exists())
        verdict = alphactl.main(["install", "--root", str(stage),
                                 "--home", str(self.home), "--apply"])
        self.assertEqual(verdict, 1)
        self.assertFalse(self.owned["desktop"].exists())
        self.assertFalse(self.state.exists())

    def test_verify_package_passes_and_detects_tampering(self):
        checked = alphactl.verify_package(self.staging)
        self.assertEqual(checked["verdict"], "PASS", checked)
        self.assertEqual(checked["build_status"], "COMPILED_EVIDENCE_VERIFIED")
        (self.staging / "tools/alpha_package/NOTICE.md").write_bytes(b"tampered\n")
        checked = alphactl.verify_package(self.staging)
        self.assertEqual(checked["verdict"], "FAIL")
        self.assertTrue(any("NOTICE.md" in reason for reason in checked["reasons"]))

    def test_dry_run_writes_nothing_and_apply_creates_exact_files(self):
        plan = alphactl.plan_install(self.staging, self.home)
        self.assertTrue(plan["dry_run"])
        self.assertFalse(plan["performs_changes"])
        self.assertFalse(plan["privileged"])
        self.assertEqual(plan["native_mint_session_acceptance"], "NOT_RUN")
        self.assertFalse(self.owned["desktop"].exists())
        self.assertFalse(self.state.exists())
        result = self._install()
        self.assertEqual(result["binary_sha256"], self.binary_sha)
        entry = self.owned["desktop"].read_bytes()
        marker = json.loads(self.owned["manifest"].read_text(encoding="utf-8"))
        self.assertEqual(marker, {"schema": 1, "sha256": hashlib.sha256(entry).hexdigest()})
        self.assertTrue(self.state.is_file())
        checked = alphactl.load_state(self.home)
        self.assertEqual(checked["after"]["desktop"]["sha256"], hashlib.sha256(entry).hexdigest())

    def test_install_refuses_existing_config_without_overwriting(self):
        original = b"[Desktop Entry]\nName=User owned\n"
        self.owned["desktop"].parent.mkdir(parents=True)
        self.owned["desktop"].write_bytes(original)
        with self.assertRaises(alphactl.AlphaPackageError):
            alphactl.apply_install(self.staging, self.home)
        self.assertEqual(self.owned["desktop"].read_bytes(), original)
        self.assertFalse(self.owned["manifest"].exists())
        self.assertFalse(self.state.exists())

    def test_uninstall_restores_original_desktop_and_refuses_modified_entry(self):
        self._install()
        result = alphactl.apply_uninstall(self.staging, self.home)
        self.assertEqual(result["verdict"], "PASS", result)
        self.assertTrue(result["original_desktop_restored"])
        for name in ("desktop", "manifest"):
            self.assertEqual(self.owned[name].exists(), False)
        self.assertFalse(self.state.exists())
        self._install()
        altered = self.owned["desktop"].read_bytes() + b"# user edit\n"
        self.owned["desktop"].write_bytes(altered)
        with self.assertRaises(alphactl.AlphaPackageError):
            alphactl.apply_uninstall(self.staging, self.home)
        self.assertEqual(self.owned["desktop"].read_bytes(), altered)
        self.assertTrue(self.owned["manifest"].exists())

    def test_rollback_after_partial_uninstall_restores_installed_state(self):
        self._install()
        expected = alphactl._snapshot(str(self.home))["desktop"]
        self.owned["manifest"].unlink()
        plan = alphactl.plan_rollback(self.staging, self.home, "after")
        self.assertTrue(plan["dry_run"])
        result = alphactl.apply_rollback(self.staging, self.home, "after")
        self.assertEqual(result["verdict"], "PASS", result)
        actual = alphactl._snapshot(str(self.home))["desktop"]
        self.assertTrue(alphactl._same_state(actual, expected))
        self.assertEqual(alphactl.apply_uninstall(self.staging, self.home)["verdict"], "PASS")

    def test_rollback_to_before_removes_only_owned_files(self):
        self._install()
        result = alphactl.apply_rollback(self.staging, self.home, "before")
        self.assertEqual(result["verdict"], "PASS", result)
        self.assertFalse(self.owned["desktop"].exists())
        self.assertFalse(self.owned["manifest"].exists())
        self.assertFalse(self.state.exists())

    def test_duplicate_keys_are_refused_in_manifest_and_state(self):
        manifest_path = self.staging / "MANIFEST.json"
        original_manifest = manifest_path.read_bytes()
        raw = original_manifest.decode("utf-8")
        manifest_path.write_text(
            raw.replace('"schema": 1', '"schema": 1, "schema": 1', 1),
            encoding="utf-8")
        with self.assertRaises(alphactl.AlphaPackageError):
            alphactl.load_manifest(self.staging)
        manifest_path.write_bytes(original_manifest)
        self._install()
        state_raw = self.state.read_text(encoding="utf-8")
        self.state.write_text(
            state_raw.replace('"schema": 1', '"schema": 1, "schema": 1', 1),
            encoding="utf-8")
        with self.assertRaises(alphactl.AlphaPackageError):
            alphactl.load_state(self.home)

    def test_cli_plan_install_uninstall_round_trip(self):
        script = build_package._repo_root() / "tools/alpha_package/alphactl.py"
        def run(*args):
            return subprocess.run(
                [sys.executable, str(script), *args],
                capture_output=True, text=True, check=False)
        plan = run("plan", "--root", str(self.staging), "--home", str(self.home))
        self.assertEqual(plan.returncode, 0, plan.stderr)
        self.assertTrue(json.loads(plan.stdout.split("CANOPY_ALPHA:", 1)[1])["dry_run"])
        applied = run("install", "--root", str(self.staging),
                      "--home", str(self.home), "--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue(self.owned["desktop"].is_file())
        removed = run("uninstall", "--root", str(self.staging),
                      "--home", str(self.home), "--apply")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(self.owned["desktop"].exists())


if __name__ == "__main__":
    unittest.main()
