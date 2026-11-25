"""Offline unit tests for the dry-run Classic preview installation planner.

A green test here proves only deterministic offline planning. It is not a
Linux Mint guest test and not a compiled Qt test.
"""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from canopy_features.installer import preview_install_plan as plan
from tools import mint_classic_qt_smoke as smoke
from tools import mint_guest_preflight as preflight
from tools import register_classic_preview as menu


class PreviewInstallPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "canopy-classic-spike"
        self.binary.write_text("# preview binary placeholder\n",
                               encoding="utf-8")
        self.binary.chmod(0o755)
        self.data_home = self.root / "xdg data home"
        self.art = self.root / "approved art"
        self.art.mkdir()
        self.wallpaper = self.root / "alpine.png"
        self.wallpaper.write_bytes(b"wallpaper")
        self.sha = "a" * 40

    def build(self, **kwargs):
        values = {
            "qt_binary": self.binary,
            "data_home": self.data_home,
            "art": self.art,
            "wallpaper": self.wallpaper,
            "source_sha": self.sha,
        }
        values.update(kwargs)
        return plan.build_plan(**values)

    def test_plan_is_offline_dry_run(self):
        result = self.build()
        self.assertEqual(result["schema_version"], 1)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["performs_install"])
        self.assertFalse(result["privileged"])
        self.assertTrue(any("No Linux Mint guest" in note
                            for note in result["not_proven"]))
        self.assertTrue(any("No compiled Qt application" in note
                            for note in result["not_proven"]))

    def test_missing_qt_executable_rejected(self):
        missing = self.root / "not-built" / "canopy-classic-spike"
        with self.assertRaisesRegex(plan.PlanError, "missing"):
            plan.build_plan(qt_binary=missing, data_home=self.data_home)
        self.assertFalse(missing.exists())

    def test_relative_and_symlinked_qt_executable_rejected(self):
        with self.assertRaisesRegex(plan.PlanError, "absolute path"):
            plan.build_plan(qt_binary="canopy-classic-spike",
                            data_home=self.data_home)
        linked = self.root / "linked-binary"
        linked.symlink_to(self.binary)
        with self.assertRaisesRegex(plan.PlanError, "symlink"):
            plan.build_plan(qt_binary=linked, data_home=self.data_home)

    def test_destinations_come_from_real_installer(self):
        result = self.build()
        expected = menu.paths(self.data_home)
        self.assertEqual(result["destinations"],
                         {key: str(value) for key, value in expected.items()})
        install_step = next(s for s in result["steps"]
                            if s["phase"] == "install")
        self.assertEqual(install_step["owned_by"], menu.DESKTOP)

    def test_steps_reference_real_tools_and_fixed_constants(self):
        result = self.build()
        phases = [step["phase"] for step in result["steps"]]
        self.assertEqual(phases, ["preflight", "verify-binary", "record-source",
                                  "install", "smoke", "rollback"])
        self.assertEqual([step["order"] for step in result["steps"]],
                         list(range(1, len(phases) + 1)))
        by_phase = {step["phase"]: step for step in result["steps"]}
        self.assertEqual(by_phase["preflight"]["required_tools"],
                         list(preflight.NEEDED))
        self.assertEqual(by_phase["smoke"]["resolutions"],
                         [f"{w}x{h}" for w, h in smoke.SIZES])
        self.assertEqual(by_phase["smoke"]["required_markers"],
                         list(smoke.REQUIRED_MARKERS))
        self.assertIn("tools/register_classic_preview.py",
                      by_phase["install"]["command"])
        self.assertEqual(by_phase["smoke"]["status"], "READY")

    def test_smoke_blocked_when_approved_inputs_missing(self):
        result = self.build(art=None, wallpaper=None, source_sha=None)
        smoke_step = next(s for s in result["steps"]
                          if s["phase"] == "smoke")
        self.assertEqual(smoke_step["status"], "BLOCKED")
        self.assertEqual(smoke_step["missing"],
                         ["approved artwork", "approved wallpaper",
                          "source_sha"])
        self.assertTrue(any(s["phase"] == "record-source"
                            for s in result["steps"]) is False)

    def test_native_apps_only_when_requested(self):
        install_step = next(s for s in self.build()["steps"]
                            if s["phase"] == "install")
        self.assertNotIn("--enable-system-apps", install_step["command"])
        enabled = self.build(native_apps=True)
        self.assertTrue(enabled["optional_resources"]["native_apps"])
        enabled_step = next(s for s in enabled["steps"]
                            if s["phase"] == "install")
        self.assertIn("--enable-system-apps", enabled_step["command"])

    def test_invalid_optional_resources_rejected(self):
        with self.assertRaises(plan.PlanError):
            self.build(art=self.root / "missing-art")
        with self.assertRaises(plan.PlanError):
            self.build(wallpaper=str(self.wallpaper.relative_to(self.root)))
        with self.assertRaisesRegex(plan.PlanError, "requires approved"):
            self.build(art=None, terminal=self.wallpaper)

    def test_source_sha_and_tokens_validated(self):
        with self.assertRaisesRegex(plan.PlanError, "40-character"):
            self.build(source_sha="deadbeef")
        with self.assertRaises(plan.PlanError):
            self.build(mint_release="Linux Mint\nmalicious")
        with self.assertRaises(plan.PlanError):
            self.build(session_type="x11;rm -rf /")
        result = self.build(mint_release="21.3", session_type="x11")
        self.assertEqual(result["mint_release"], "21.3")
        self.assertEqual(result["session_type"], "x11")

    def test_build_has_no_filesystem_side_effects(self):
        self.build()
        self.assertFalse(self.data_home.exists())
        self.assertFalse((self.root / "plan.json").exists())
        self.assertEqual(self.binary.read_text(),
                         "# preview binary placeholder\n")

    def test_plan_is_deterministic_and_json_serializable(self):
        first = self.build()
        second = self.build()
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_write_plan_round_trip(self):
        result = self.build()
        output = self.root / "plan.json"
        written = plan.write_plan(result, output, allowed_root=self.root)
        self.assertEqual(written, output)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")),
                         result)
        self.assertNotIn("\r\n", output.read_bytes().decode("utf-8"))

    def test_unauthorized_output_outside_root_rejected(self):
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(elsewhere, ignore_errors=True))
        with self.assertRaisesRegex(plan.PlanError, "outside the authorized"):
            plan.write_plan(self.build(), elsewhere / "plan.json",
                            allowed_root=self.root)

    def test_unauthorized_output_shapes_rejected(self):
        result = self.build()
        cases = [
            ("plan.json", "absolute"),
            (self.root / "plan.txt", ".json"),
        ]
        for output, message in cases:
            with self.subTest(output=output):
                with self.assertRaisesRegex(plan.PlanError, message):
                    plan.write_plan(result, output, allowed_root=self.root)
        existing = self.root / "taken.json"
        existing.write_text("owner data", encoding="utf-8")
        with self.assertRaisesRegex(plan.PlanError, "already exists"):
            plan.write_plan(result, existing, allowed_root=self.root)
        self.assertEqual(existing.read_text(encoding="utf-8"), "owner data")
        real = self.root / "real.json"
        real.write_text("private", encoding="utf-8")
        linked = self.root / "linked.json"
        linked.symlink_to(real)
        with self.assertRaisesRegex(plan.PlanError, "symlink"):
            plan.write_plan(result, linked, allowed_root=self.root)
        self.assertEqual(real.read_text(encoding="utf-8"), "private")

    def test_cli_writes_plan_and_fails_closed_on_missing_binary(self):
        output = self.root / "cli-plan.json"
        argv = ["--binary", str(self.binary), "--data-home",
                str(self.data_home), "--output", str(output),
                "--allowed-root", str(self.root)]
        self.assertEqual(plan.main(argv), 0)
        self.assertTrue(output.is_file())
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))[
            "qt_binary"], str(self.binary))
        missing = self.root / "cli-fail.json"
        bad = ["--binary", str(self.root / "no-such-binary"),
               "--output", str(missing), "--allowed-root", str(self.root)]
        self.assertEqual(plan.main(bad), 1)
        self.assertFalse(missing.exists())

    def test_write_plan_never_overwrites_and_hides_no_secret(self):
        result = self.build()
        output = self.root / "plan.json"
        plan.write_plan(result, output, allowed_root=self.root)
        first = output.read_bytes()
        with self.assertRaisesRegex(plan.PlanError, "already exists"):
            plan.write_plan(result, output, allowed_root=self.root)
        self.assertEqual(output.read_bytes(), first)
        with patch.dict(os.environ, {"CANOPY_TEST_SECRET":
                                     "sensitive-example"}):
            leaked = self.build()
        self.assertNotIn("sensitive-example",
                         json.dumps(leaked, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
