"""Offline negative-control tests for the user-level install/recovery planner.

A PASS here proves deterministic planning and exact-state verification only.
Native Mint session acceptance is NOT_RUN and must come from guest execution.
"""
import base64
from contextlib import redirect_stdout
import io
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


class InstallRecoveryPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "xdg data home"
        self.home.mkdir()
        self.binary = self.base / "canopy-classic"
        self.binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.binary.chmod(0o755)
        self.art = self.base / "approved art"
        self.art.mkdir()
        self.wallpaper = self.base / "alpine.png"
        self.wallpaper.write_bytes(b"wallpaper")

    def install(self):
        with patch("tools.register_classic_preview._effective_uid",
                   return_value=1000):
            return menu.install(self.home, self.binary)

    def uninstall(self):
        with patch("tools.register_classic_preview._effective_uid",
                   return_value=1000):
            return menu.uninstall(self.home)

    def plan_install(self, **kwargs):
        values = {"binary": self.binary}
        values.update(kwargs)
        return planner.plan_install(self.home, values.pop("binary"), **values)

    def expected_mode(self, posix):
        return 0o666 if os.name == "nt" else posix

    def assert_no_writes(self, plan):
        self.assertFalse((self.home / "applications" / menu.DESKTOP).exists())
        self.assertFalse(menu.paths(self.home)["manifest"].exists())
        self.assertEqual(plan["dry_run"], True)
        self.assertEqual(plan["performs_changes"], False)

    def test_install_plan_is_pure_dry_run_and_labels_guest_not_run(self):
        plan = self.plan_install()
        self.assert_no_writes(plan)
        self.assertEqual(planner.verify_plan(plan)["verdict"], "PASS")
        self.assertEqual(plan["operation"], "install")
        self.assertEqual(plan["privileged"], False)
        self.assertEqual(plan["system_paths_written"], [])
        self.assertEqual(plan["session_changes"], [])
        self.assertEqual(plan["native_mint_session_acceptance"], "NOT_RUN")
        self.assertEqual(plan["guest_execution"], "NOT_RUN")
        self.assertEqual(plan["session_restoration"]["acceptance"], "NOT_RUN")
        self.assertTrue(any("NOT_RUN" in note for note in plan["not_proven"]))

    def test_projected_bytes_match_a_real_install_exactly(self):
        plan = self.plan_install()
        self.assert_no_writes(plan)
        desktop = self.install()
        for key, target in (("desktop", desktop),
                            ("manifest", menu.paths(self.home)["manifest"])):
            expected = plan["after_expected"][key]
            self.assertEqual(base64.b64decode(expected["payload_base64"]),
                             target.read_bytes())
            self.assertEqual(expected["sha256"], planner._sha(target.read_bytes()))
            self.assertEqual(expected["mode"], self.expected_mode(
                0o644 if key == "desktop" else 0o600))

    def test_snapshot_records_exact_state_without_following_links(self):
        self.install()
        snap = planner.snapshot_desktop_entry(self.home)
        self.assertEqual(snap["status"], "INSTALLED")
        self.assertTrue(snap["safe"])
        for key in planner.OWNED_FILES:
            path = menu.paths(self.home)[key]
            self.assertEqual(base64.b64decode(snap[key]["payload_base64"]),
                             path.read_bytes())
            self.assertEqual(snap[key]["sha256"], planner._sha(path.read_bytes()))
            self.assertEqual(snap[key]["mode"], os.stat(path).st_mode & 0o777)

    def test_verify_recovery_passes_after_exact_install(self):
        plan = self.plan_install()
        self.install()
        result = planner.verify_recovery(self.home, plan)
        self.assertEqual(result, {"verdict": "PASS", "reasons": []})

    def test_modified_entry_is_detected_as_corruption(self):
        plan = self.plan_install()
        desktop = self.install()
        desktop.write_bytes(desktop.read_bytes() + b"# tampered\n")
        result = planner.verify_recovery(self.home, plan)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("sha256_mismatch:desktop", result["reasons"])
        self.assertIn("payload_base64_mismatch:desktop", result["reasons"])

    def test_missing_binary_is_refused_before_any_write(self):
        missing = self.base / "not-built" / "canopy"
        with self.assertRaisesRegex(planner.RecoveryPlanError,
                                    "Canopy binary must be an existing"):
            self.plan_install(binary=missing)
        self.assertFalse((self.base / "not-built").exists())
        self.assert_no_writes({"dry_run": True, "performs_changes": False})

    def test_symlinked_binary_parent_is_refused(self):
        real_dir = self.base / "real-build"
        real_dir.mkdir()
        target = real_dir / "canopy"
        target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        target.chmod(0o755)
        alias_dir = self.base / "linked-build"
        alias_dir.symlink_to(real_dir, target_is_directory=True)
        with self.assertRaises(planner.RecoveryPlanError):
            self.plan_install(binary=alias_dir / "canopy")
        self.assertFalse(menu.paths(self.home)["desktop"].exists())

    def test_symlinked_desktop_entry_fails_verification_not_pass(self):
        plan = self.plan_install()
        desktop = self.install()
        original = desktop.read_bytes()
        outside = self.base / "outside.desktop"
        outside.write_bytes(original)
        desktop.unlink()
        desktop.symlink_to(outside)
        result = planner.verify_recovery(self.home, plan)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("unexpected_path:desktop", result["reasons"])
        self.assertEqual(outside.read_bytes(), original)

    def test_unexpected_session_autostart_path_fails_closed(self):
        plan = self.plan_install()
        self.install()
        autostart = self.home / ".config" / "autostart" / menu.DESKTOP
        autostart.parent.mkdir(parents=True)
        autostart.write_text("[Desktop Entry]\nX-Canopy-Preview=true\n",
                             encoding="utf-8")
        result = planner.verify_recovery(self.home, plan)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("unexpected_path:xdg_autostart", result["reasons"])

    def test_oversized_desktop_entry_is_unreadable_and_refused(self):
        destination = menu.paths(self.home)["desktop"]
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"x" * (planner.MAX_DESKTOP_BYTES + 1))
        snap = planner.snapshot_desktop_entry(self.home)
        self.assertEqual(snap["desktop"]["kind"], "OVERSIZE")
        self.assertFalse(snap["desktop"]["safe"])
        with self.assertRaisesRegex(planner.RecoveryPlanError, "install refused"):
            self.plan_install()
        self.assertEqual(destination.stat().st_size, planner.MAX_DESKTOP_BYTES + 1)

    def test_uninstall_plan_requires_exact_owned_state(self):
        with self.assertRaisesRegex(planner.RecoveryPlanError,
                                    "not installed and exact"):
            planner.plan_uninstall(self.home)
        desktop = self.install()
        desktop.write_bytes(desktop.read_bytes() + b"# changed\n")
        with self.assertRaisesRegex(planner.RecoveryPlanError,
                                    "not installed and exact"):
            planner.plan_uninstall(self.home)
        self.assertTrue(desktop.is_file())

    def test_uninstall_plan_rollback_is_bounded_and_exact(self):
        self.install()
        plan = planner.plan_uninstall(self.home)
        self.assertEqual(planner.verify_plan(plan)["verdict"], "PASS")
        self.assertEqual(plan["after_expected"]["status"], "NOT_INSTALLED")
        self.assertEqual(len(plan["rollback"]), 1)
        rollback = plan["rollback"][0]
        self.assertEqual(rollback["bytes_bound"], planner.MAX_DESKTOP_BYTES)
        self.assertEqual(base64.b64decode(rollback["payload_base64"]),
                         menu.paths(self.home)["desktop"].read_bytes())
        self.uninstall()
        self.assertEqual(planner.verify_recovery(self.home, plan)["verdict"],
                         "PASS")

    def test_partial_rollback_is_detected_as_failure(self):
        self.install()
        plan = planner.plan_uninstall(self.home)
        self.uninstall()
        # Simulate a partial rollback: entry restored, marker still absent.
        rolled = menu.paths(self.home)["desktop"]
        rolled.write_bytes(base64.b64decode(plan["rollback"][0]["payload_base64"]))
        result = planner.verify_recovery(self.home, plan)
        self.assertEqual(result["verdict"], "FAIL")
        self.assertIn("status_mismatch", result["reasons"])
        self.assertIn("kind_mismatch:desktop", result["reasons"])
        self.assertEqual(rolled.stat().st_size,
                         len(base64.b64decode(plan["rollback"][0]["payload_base64"])))

    def test_recovery_plan_is_noop_without_managed_entry(self):
        plan = planner.plan_recovery(self.home)
        self.assertEqual(plan["session_restoration"]["strategy"],
                         "NO_OP_SESSION_NEVER_CHANGED")
        self.assertEqual(plan["auto_action_allowed"], False)
        self.assertEqual(planner.verify_recovery(self.home, plan)["verdict"],
                         "PASS")

    def test_modified_recovery_plan_needs_manual_review_and_deletes_nothing(self):
        desktop = self.install()
        desktop.write_bytes(desktop.read_bytes() + b"# user note\n")
        plan = planner.plan_recovery(self.home)
        self.assertEqual(plan["after_expected"], None)
        self.assertEqual(plan["auto_action_allowed"], False)
        self.assertFalse(any("unlink" in step["phase"] for step in plan["steps"]))
        self.assertEqual(planner.verify_recovery(self.home, plan)["verdict"],
                         "NEEDS_MANUAL_REVIEW")
        self.assertTrue(desktop.is_file())

    def test_installed_recovery_plan_never_changes_the_session(self):
        self.install()
        plan = planner.plan_recovery(self.home)
        self.assertEqual(planner.verify_plan(plan)["verdict"], "PASS")
        self.assertEqual(plan["session_changes"], [])
        self.assertEqual(plan["system_paths_written"], [])
        self.assertEqual(len(plan["rollback"]), 1)
        self.uninstall()
        self.assertEqual(planner.verify_recovery(self.home, plan)["verdict"],
                         "PASS")

    def test_verify_plan_rejects_corrupted_claims_and_unexpected_paths(self):
        plan = self.plan_install()
        for field, value in (
                ("dry_run", False),
                ("performs_changes", True),
                ("privileged", True),
                ("native_mint_session_acceptance", "PASS"),
                ("guest_execution", "PASS"),
                ("session_changes", ["replace-cinnamon"]),
                ("system_paths_written", ["/etc/xdg/autostart"]),
                ("session_restoration", {"strategy": "REPLACE_LOGIN_MANAGER",
                                         "display_manager": "CHANGED",
                                         "compositor": "CHANGED",
                                         "acceptance": "PASS"}),
        ):
            with self.subTest(field=field):
                corrupt = json.loads(json.dumps(plan))
                corrupt[field] = value
                self.assertEqual(planner.verify_plan(corrupt)["verdict"], "FAIL")
        corrupt = json.loads(json.dumps(plan))
        corrupt["rollback"][0]["target"] = "/etc/xdg/autostart/org.canopy.desktop"
        self.assertIn("rollback_outside_owned_paths",
                      planner.verify_plan(corrupt)["reasons"])
        corrupt = json.loads(json.dumps(plan))
        corrupt["before"]["desktop"]["payload_base64"] = base64.b64encode(
            b"not the recorded bytes").decode("ascii")
        self.assertIn("snapshot_checksum_mismatch:desktop",
                      planner.verify_plan(corrupt)["reasons"])

    def test_cross_field_and_home_mismatch_guards(self):
        plan = self.plan_install()
        self.install()
        other = self.base / "other home"
        other.mkdir()
        self.assertEqual(
            planner.verify_recovery(other, plan)["verdict"], "FAIL")
        self.assertIn("home_mismatch",
                      planner.verify_recovery(other, plan)["reasons"])
        corrupt = json.loads(json.dumps(plan))
        corrupt["after_expected"]["status"] = "NOT_INSTALLED"
        self.assertIn("absent_status_with_owned_files",
                      planner.verify_plan(corrupt)["reasons"])
        corrupt = json.loads(json.dumps(plan))
        corrupt["after_expected"]["desktop"]["kind"] = "ABSENT"
        self.assertIn("installed_status_without_owned_files",
                      planner.verify_plan(corrupt)["reasons"])
        corrupt = json.loads(json.dumps(plan))
        corrupt["rollback"][0]["bytes_bound"] = planner.MAX_DESKTOP_BYTES + 1
        self.assertIn("unbounded_rollback",
                      planner.verify_plan(corrupt)["reasons"])
        corrupt = json.loads(json.dumps(plan))
        corrupt["not_proven"] = ["Nothing to report"]
        self.assertIn("missing_not_run_label",
                      planner.verify_plan(corrupt)["reasons"])

    def test_wrong_type_arguments_use_domain_error(self):
        for bad in (None, 7, True, [], {}, b"/tmp", "relative/path"):
            with self.subTest(home=repr(bad)):
                with self.assertRaises(planner.RecoveryPlanError):
                    planner.snapshot_desktop_entry(bad)
                with self.assertRaises(planner.RecoveryPlanError):
                    planner.plan_uninstall(bad)
        for bad in (7, True, [], {}, b"binary"):
            with self.subTest(binary=repr(bad)):
                with self.assertRaises(planner.RecoveryPlanError):
                    self.plan_install(binary=bad)

    def test_system_owned_homes_are_refused(self):
        for home in ("/etc", "/usr/share", "/var/lib", "C:/Windows/System32",
                     "C:\\Program Files\\Canopy"):
            with self.subTest(home=home):
                with self.assertRaises(planner.RecoveryPlanError):
                    planner.snapshot_desktop_entry(home)

    def test_plans_are_deterministic_json_and_bounded(self):
        first = self.plan_install()
        second = self.plan_install()
        self.assertEqual(first, second)
        text = json.dumps(first, sort_keys=True)
        self.assertEqual(text, json.dumps(second, sort_keys=True))
        self.assertLess(len(text.encode("utf-8")), planner.MAX_PLAN_BYTES)
        self.assertLessEqual(len(first["steps"]), planner.MAX_STEPS)

    def test_verify_plan_file_rejects_duplicate_json_keys(self):
        plan = self.plan_install()
        output = self.base / "plan.json"
        output.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
        self.assertEqual(planner.verify_plan_file(output)["verdict"], "PASS")
        raw = output.read_text(encoding="utf-8")
        duplicated = raw.replace('"dry_run": true',
                                 '"dry_run": true, "dry_run": false', 1)
        output.write_text(duplicated, encoding="utf-8")
        verdict = planner.verify_plan_file(output)
        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertTrue(any("duplicate" in reason for reason in verdict["reasons"]))

    def test_module_cli_is_read_only_and_prints_verdict(self):
        output = self.base / "cli-plan.json"
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            rc = planner.main(["--home", str(self.home), "--action", "install",
                               "--binary", str(self.binary)])
        self.assertEqual(rc, 0)
        self.assertFalse(menu.paths(self.home)["desktop"].exists())
        text = buffer.getvalue()
        self.assertIn("CANOPY_INSTALL_RECOVERY:", text)
        payload = json.loads(text.split("CANOPY_INSTALL_RECOVERY:", 1)[1])
        self.assertEqual(planner.verify_plan(payload)["verdict"], "PASS")
        output.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        self.assertEqual(planner.verify_plan_file(output)["verdict"], "PASS")
        check = planner.main(["--home", str(self.home), "--action", "verify",
                              "--plan", str(output)])
        self.assertEqual(check, 1)  # NOT installed: no false PASS
        self.install()
        self.assertEqual(planner.main(["--home", str(self.home),
                                       "--action", "verify",
                                       "--plan", str(output)]), 0)

    def test_environment_secrets_are_not_emitted(self):
        with patch.dict(os.environ, {"CANOPY_RECOVERY_SECRET": "do-not-leak"}):
            plan = self.plan_install()
        self.assertNotIn("do-not-leak", json.dumps(plan, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
