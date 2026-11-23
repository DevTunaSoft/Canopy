"""Offline tests for the dry-run Classic preview installation planner.

These tests never run Qt, never touch a real Linux Mint system and never write
outside temporary directories. Desktop quoting is checked against the real
installer's ``_quote`` helper; no install, session change or Qt launch occurs.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from canopy_features.installer import preview_install_plan as planner
from tools import mint_guest_preflight as preflight
from tools import register_classic_preview as register


def ready_preflight():
    """Simulated Mint-like preflight; not evidence of a real Mint guest."""
    return preflight.assess(
        {"ID": "linuxmint", "VERSION_ID": "22.3"},
        {"DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "X-Cinnamon",
         "XDG_SESSION_TYPE": "x11"},
        {name: True for name in preflight.NEEDED},
        "6.4.2",
    )


def make_binary(directory):
    exe = Path(directory) / "canopy-classic"
    exe.write_bytes(b"fake compiled qt binary")
    return exe


class PreviewInstallPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "data-home"
        self.exe = make_binary(self.root)
        self.ready = ready_preflight()

    def plan(self, **kwargs):
        kwargs.setdefault("binary", self.exe)
        kwargs.setdefault("home", self.home)
        kwargs.setdefault("preflight_report", self.ready)
        return planner.build_plan(**kwargs)

    # -- dry-run guarantee -------------------------------------------------
    def test_dry_run_creates_no_files_or_directories(self):
        before = set(self.root.rglob("*"))
        plan = self.plan()
        text = planner.render_json(plan)
        self.assertTrue(json.loads(text)["dry_run"])
        self.assertEqual(set(self.root.rglob("*")), before)
        self.assertFalse(self.home.exists())

    # -- happy path --------------------------------------------------------
    def test_ready_plan_has_expected_paths_and_exec(self):
        art = self.root / "approved"
        art.mkdir()
        wallpaper = self.root / "wallpaper.png"
        wallpaper.write_bytes(b"png")
        plan = self.plan(art=art, wallpaper=wallpaper)
        self.assertEqual(plan["status"], "READY")
        self.assertEqual(plan["blockers"], [])
        self.assertEqual(plan["target"]["desktop_entry"],
                         str(self.home / "applications" / register.DESKTOP))
        self.assertEqual(
            plan["exec_argv"],
            [str(self.exe), "--approved-art-dir", str(art),
             "--landscape-wallpaper", str(wallpaper)],
        )
        self.assertIn("Exec=", plan["desktop_entry_payload"])
        self.assertIn("--enable-system-apps", " ".join(
            self.plan(native_apps=True)["exec_argv"]))

    # -- missing Qt executable (required coverage) -------------------------
    def test_missing_qt_executable_blocks_plan(self):
        missing = self.root / "does-not-exist"
        plan = self.plan(binary=missing)
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertTrue(any("Canopy Qt executable" in b for b in plan["blockers"]))
        self.assertIsNone(plan["exec_argv"])
        self.assertIsNone(plan["desktop_entry_payload"])

    def test_non_executable_qt_blocks_plan(self):
        with mock.patch.object(planner.os, "access", return_value=False):
            plan = self.plan()
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertTrue(any("not executable" in b for b in plan["blockers"]))

    # -- payload reuses the real installer's quoting and template ----------
    def test_desktop_payload_reuses_installer_quoting_and_manifest_digest(self):
        plan = self.plan()
        expected = " ".join(
            register._quote(Path(arg).as_posix()) for arg in plan["exec_argv"]
        )
        self.assertEqual(plan["exec_command"], expected)
        payload = plan["desktop_entry_payload"]
        self.assertIn("Exec=" + expected + "\n", payload)
        self.assertIn("X-Canopy-Preview=true\n", payload)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.assertEqual(
            json.loads(plan["ownership_manifest_payload"])["sha256"], digest
        )

    # -- authorization / output safety (required coverage) -----------------
    def test_write_plan_within_authorized_root(self):
        allowed = self.root / "allowed"
        allowed.mkdir()
        output = allowed / "plan.json"
        plan = self.plan()
        self.assertEqual(planner.write_plan(plan, output, allowed_root=allowed),
                         str(output))
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), plan)
        if os.name == "posix":
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_write_plan_refuses_unauthorized_output(self):
        allowed = self.root / "allowed"
        blocked = self.root / "blocked"
        allowed.mkdir()
        blocked.mkdir()
        with self.assertRaises(planner.PlanError):
            planner.write_plan(self.plan(), blocked / "plan.json",
                               allowed_root=allowed)
        self.assertFalse((blocked / "plan.json").exists())

    def test_write_plan_refuses_existing_output(self):
        allowed = self.root / "allowed"
        allowed.mkdir()
        output = allowed / "plan.json"
        output.write_text("keep me", encoding="utf-8")
        with self.assertRaises(planner.PlanError):
            planner.write_plan(self.plan(), output, allowed_root=allowed)
        self.assertEqual(output.read_text(encoding="utf-8"), "keep me")

    def test_write_plan_refuses_symlinked_output(self):
        allowed = self.root / "allowed"
        allowed.mkdir()
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        link = allowed / "plan.json"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlinks unavailable: " + str(exc))
        with self.assertRaises(planner.PlanError):
            planner.write_plan(self.plan(), link, allowed_root=allowed)

    def test_write_plan_refuses_root_privilege(self):
        allowed = self.root / "allowed"
        allowed.mkdir()
        with mock.patch.object(register.os, "geteuid", create=True,
                               return_value=0):
            with self.assertRaises(planner.PlanError):
                planner.write_plan(self.plan(), allowed / "plan.json",
                                   allowed_root=allowed)
        self.assertFalse((allowed / "plan.json").exists())

    # -- honesty about what is not proven ----------------------------------
    def test_non_mint_preflight_is_a_warning_not_an_acceptance_claim(self):
        other = preflight.assess(
            {"ID": "ubuntu", "VERSION_ID": "24.04"}, {}, {}, None
        )
        plan = self.plan(preflight_report=other)
        self.assertEqual(plan["status"], "READY")
        self.assertTrue(plan["warnings"])
        self.assertEqual(plan["preflight"]["mint_guest_acceptance"], "NOT_RUN")
        self.assertIn("linux_mint_guest_acceptance", plan["not_proven"])
        self.assertTrue(all(x in plan["not_proven"] for x in (
            "visual_owner_approval", "compiled_qt_execution")))

    def test_simulated_mint_preflight_does_not_claim_real_mint_test(self):
        self.assertEqual(self.ready["status"], "READY_FOR_TESTS")
        plan = self.plan()
        self.assertIn("integration_note", plan)
        self.assertIn("not prove a working desktop", plan["integration_note"])
        self.assertEqual(plan["dry_run"], True)


if __name__ == "__main__":
    unittest.main()
