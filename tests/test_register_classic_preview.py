"""Dry-run and verifier contract tests for register_classic_preview CLI.

These are offline tests. Native Mint session acceptance remains NOT_RUN.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from canopy_features.mint import install_recovery_plan as planner
from tools import register_classic_preview as menu

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "register_classic_preview.py"


class RegisterClassicPreviewDryRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "xdg data home"
        self.home.mkdir()
        self.binary = self.base / "canopy-classic"
        self.binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.binary.chmod(0o755)
        self.marker = self.base / "binary-was-executed"
        self.paths = menu.paths(self.home)

    def install(self):
        with patch("tools.register_classic_preview._effective_uid",
                   return_value=1000):
            return menu.install(self.home, self.binary)

    def run_cli(self, *argv):
        env = dict(os.environ)
        env["XDG_DATA_HOME"] = str(self.home)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run([sys.executable, "-B", str(TOOL), *argv],
                              capture_output=True, text=True, env=env,
                              check=False)

    def test_install_dry_run_returns_the_planner_plan_without_writes(self):
        with patch("tools.register_classic_preview._effective_uid",
                   return_value=1000):
            actual = menu.install(self.home, self.binary, dry_run=True)
        expected = planner.plan_install(self.home, self.binary)
        self.assertEqual(actual, expected)
        self.assertEqual(planner.verify_plan(actual)["verdict"], "PASS")
        self.assertFalse(self.paths["desktop"].exists())
        self.assertFalse(self.paths["manifest"].exists())
        self.assertFalse(self.marker.exists())
        self.assertEqual(actual["native_mint_session_acceptance"], "NOT_RUN")

    def test_uninstall_dry_run_does_not_delete_exact_owned_files(self):
        desktop = self.install()
        original = desktop.read_bytes()
        with patch("tools.register_classic_preview._effective_uid",
                   return_value=1000):
            plan = menu.uninstall(self.home, dry_run=True)
        self.assertEqual(plan["operation"], "uninstall")
        self.assertEqual(planner.verify_plan(plan)["verdict"], "PASS")
        self.assertEqual(desktop.read_bytes(), original)
        self.assertEqual(menu.status(self.home), "INSTALLED")

    def test_uninstall_dry_run_refuses_modified_files(self):
        desktop = self.install()
        desktop.write_bytes(desktop.read_bytes() + b"user edit\n")
        with patch("tools.register_classic_preview._effective_uid",
                   return_value=1000):
            with self.assertRaisesRegex(planner.RecoveryPlanError,
                                        "not installed and exact"):
                menu.uninstall(self.home, dry_run=True)
        self.assertTrue(desktop.is_file())

    def test_root_is_refused_even_for_dry_run(self):
        with patch("tools.register_classic_preview._effective_uid",
                   return_value=0):
            with self.assertRaisesRegex(menu.RegistrationError, "root"):
                menu.install(self.home, self.binary, dry_run=True)
            with self.assertRaisesRegex(menu.RegistrationError, "root"):
                menu.uninstall(self.home, dry_run=True)
        self.assertFalse(self.paths["desktop"].exists())

    def test_cli_install_dry_run_prints_json_and_writes_nothing(self):
        result = self.run_cli("install", "--binary", str(self.binary),
                              "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CANOPY_PREVIEW_DRY_RUN:", result.stdout)
        payload = json.loads(result.stdout.split("CANOPY_PREVIEW_DRY_RUN:", 1)[1])
        self.assertEqual(planner.verify_plan(payload)["verdict"], "PASS")
        self.assertEqual(payload["guest_execution"], "NOT_RUN")
        self.assertFalse(self.paths["desktop"].exists())
        self.assertFalse(self.marker.exists())

    def test_cli_uninstall_dry_run_preserves_the_entry(self):
        desktop = self.install()
        before = desktop.read_bytes()
        result = self.run_cli("uninstall", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CANOPY_PREVIEW_DRY_RUN:", result.stdout)
        self.assertEqual(desktop.read_bytes(), before)
        self.assertEqual(menu.status(self.home), "INSTALLED")

    def test_cli_verify_plan_rejects_corruption_without_changes(self):
        with patch("tools.register_classic_preview._effective_uid",
                   return_value=1000):
            plan = menu.install(self.home, self.binary, dry_run=True)
        valid = self.base / "valid-plan.json"
        valid.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
        before = valid.read_bytes()
        result = self.run_cli("verify-plan", "--plan", str(valid))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CANOPY_PREVIEW_VERIFY: PASS", result.stdout)
        corrupt = json.loads(json.dumps(plan))
        corrupt["system_paths_written"] = ["/etc/xdg/autostart"]
        bad = self.base / "bad-plan.json"
        bad.write_text(json.dumps(corrupt, sort_keys=True), encoding="utf-8")
        rejected = self.run_cli("verify-plan", "--plan", str(bad))
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("CANOPY_PREVIEW_VERIFY: FAIL", rejected.stdout)
        self.assertEqual(valid.read_bytes(), before)
        self.assertFalse(self.paths["desktop"].exists())

    def test_pure_builders_match_the_real_install_bytes(self):
        payload = menu.desktop_entry(self.binary)
        marker = menu.ownership_marker(payload)
        self.assertTrue(payload.startswith(b"[Desktop Entry]\n"))
        self.assertEqual(json.loads(marker.decode("utf-8"))["sha256"],
                         planner._sha(payload))
        desktop = self.install()
        self.assertEqual(desktop.read_bytes(), payload)
        self.assertEqual(self.paths["manifest"].read_bytes(), marker)

    def test_dry_run_does_not_execute_a_hostile_binary(self):
        self.binary.write_text("#!/bin/sh\ntouch " + str(self.marker) + "\n",
                               encoding="utf-8")
        self.binary.chmod(0o755)
        with patch("tools.register_classic_preview._effective_uid",
                   return_value=1000):
            menu.install(self.home, self.binary, dry_run=True)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
