"""Keyboard-only/accessibility gate: deterministic driver and negative controls.

The driver here is an inert Python harness that imitates the compiled Qt
offscreen marker protocol. A green unit test is NOT compiled Qt evidence and
NOT Mint acceptance; it only proves the gate validates the pinned contract.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.qa import classic_keyboard_accessibility_gate as gate

REPO_ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
BINARY = "b" * 64

FAKE_DRIVER = '''import os
import sys
import time

TAB = chr(9)
mode = os.environ.get("CANOPY_FAKE_MODE", "good")
script = os.environ.get("CANOPY_A11Y_SCRIPT", "")
binary = os.environ.get("CANOPY_A11Y_BINARY", "")
if not script.endswith(".json") or not binary:
    sys.exit(9)
steps = [
    ("overlay_open", "overlay=open;focus=canopyLauncherSearch;accessible_name=Search available preview applications"),
    ("overlay_tab_grid", "focus=canopyLauncherGrid;border_width=2"),
    ("grid_arrow_first", "current_index=0;accessible_name=Select Files"),
    ("overlay_escape", "overlay=closed"),
    ("overlay_reopen", "overlay=open"),
    ("grid_enter_files", "overlay=closed;files_window=open"),
    ("files_tab_search", "focus=canopyPreviewSearch;accessible_name=Filter files in current folder"),
    ("files_escape", "files_window=closed"),
    ("dock_tab_focus", "focus=canopyDockTile;accessible_name=Files preview;border_width=2"),
    ("dock_arrow_next", "focus=canopyDockTile;accessible_name=Browser preview;border_width=2"),
    ("dock_return_activate", "activation=requested;focus_claim=false"),
]
if mode == "missing":
    steps.pop(3)
elif mode == "reorder":
    steps[0], steps[1] = steps[1], steps[0]
elif mode == "wrong_detail":
    steps[1] = (steps[1][0], steps[1][1].replace("border_width=2", "border_width=0"))
elif mode == "extra":
    steps.append(steps[0])
elif mode == "unknown":
    steps[-1] = ("surprise_step", steps[-1][1])
elif mode == "sleep":
    time.sleep(4)
for step_id, detail in steps:
    print(TAB.join(["CANOPY_A11Y_STEP", step_id, "PASS", detail]), flush=True)
if mode == "exit1":
    sys.exit(3)
'''


class KeyboardAccessibilityGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.driver = self.root / "fake-driver.py"
        self.driver.write_text(FAKE_DRIVER, encoding="utf-8")
        self.driver.chmod(0o700)
        self.binary = self.root / "fake-classic.bin"
        self.binary.write_bytes(b"inert compiled-binary stand-in")
        self.binary.chmod(0o700)
        self.report = gate.run_driver(
            driver=self.driver, binary=self.binary, source_sha=SHA,
            timeout_seconds=10)

    def test_source_contract_passes_and_is_read_only(self):
        before = gate.inspect_source(REPO_ROOT)
        self.assertEqual(before["status"], "PASS")
        after = gate.inspect_source(REPO_ROOT)
        self.assertEqual(after["files_sha256"], before["files_sha256"])
        self.assertIn("prototype/classic/DockTile.qml", before["files_sha256"])

    def test_source_contract_rejects_missing_keyboard_needle(self):
        scratch = self.root / "scratch-source"
        for relative, _ in gate.SOURCE_CONTRACTS:
            target = scratch / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            original = REPO_ROOT / relative
            text = original.read_text(encoding="utf-8")
            if relative.endswith("LauncherOverlay.qml"):
                text = text.replace("Keys.onEscapePressed: launcher.closeLauncher()",
                                    "Keys.onEscapePressed: noop()")
            target.write_text(text, encoding="utf-8")
        result = gate.inspect_source(scratch)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("LauncherOverlay" in item for item in result["missing"]))

    def test_valid_offscreen_report_passes_without_forbidden_claims(self):
        verdict = gate.assess(self.report, expected_source_sha=SHA,
                              expected_binary_sha256=self.report["binary_sha256"])
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(verdict["steps_verified"], len(gate.STEPS))
        for field in ("screen_reader", "mint_acceptance", "visual_owner_approval"):
            self.assertEqual(verdict[field], gate.NOT_RUN)
        self.assertEqual(len(self.report["binary_sha256"]), 64)
        self.assertEqual(self.report["platform"], "offscreen")
        self.assertEqual(self.report["input_mode"], "keyboard-only")

    def test_report_rejects_wrong_sha_pins(self):
        with self.assertRaisesRegex(gate.GateError, "source SHA"):
            gate.assess(self.report, expected_source_sha="c" * 40)
        with self.assertRaisesRegex(gate.GateError, "binary SHA"):
            gate.assess(self.report, expected_source_sha=SHA,
                        expected_binary_sha256="d" * 64)
        with self.assertRaisesRegex(gate.GateError, "SHA pin"):
            gate.assess(self.report, expected_source_sha=True)

    def test_report_rejects_wrong_platform_and_input_mode(self):
        for field, value in (("platform", "xcb"), ("input_mode", "mouse-and-keyboard"),
                             ("kind", "synthetic"), ("schema", True)):
            with self.subTest(field=field):
                case = copy.deepcopy(self.report)
                case[field] = value
                with self.assertRaises(gate.GateError):
                    gate.assess(case, expected_source_sha=SHA)

    def test_report_rejects_self_asserted_screen_reader_or_mint_claims(self):
        for field in ("screen_reader", "mint_acceptance", "visual_approval"):
            with self.subTest(field=field):
                case = copy.deepcopy(self.report)
                case[field] = "PASS"
                with self.assertRaisesRegex(gate.GateError, "unsupported claim"):
                    gate.assess(case, expected_source_sha=SHA)

    def test_report_rejects_step_order_count_and_detail_violations(self):
        case = copy.deepcopy(self.report)
        case["steps"][0], case["steps"][1] = case["steps"][1], case["steps"][0]
        with self.assertRaisesRegex(gate.GateError, "step contract"):
            gate.assess(case, expected_source_sha=SHA)
        case = copy.deepcopy(self.report)
        case["steps"].pop()
        with self.assertRaisesRegex(gate.GateError, "step count"):
            gate.assess(case, expected_source_sha=SHA)
        case = copy.deepcopy(self.report)
        case["steps"][1]["detail"]["border_width"] = "0"
        with self.assertRaisesRegex(gate.GateError, "step detail"):
            gate.assess(case, expected_source_sha=SHA)
        case = copy.deepcopy(self.report)
        case["steps"][1]["status"] = "FAIL"
        with self.assertRaisesRegex(gate.GateError, "step contract"):
            gate.assess(case, expected_source_sha=SHA)
        case = copy.deepcopy(self.report)
        case["steps"][0]["detail"]["screen_reader_verified"] = "true"
        with self.assertRaisesRegex(gate.GateError, "step contract"):
            gate.assess(case, expected_source_sha=SHA)

    def test_duplicate_json_keys_are_rejected(self):
        path = self.root / "duplicate.json"
        path.write_text(json.dumps(self.report)[:-1] + ', "platform": "xcb"}',
                        encoding="utf-8")
        with self.assertRaisesRegex(gate.GateError, "duplicate JSON key"):
            gate.read_report(path)

    def test_extra_top_level_claim_key_is_rejected(self):
        case = copy.deepcopy(self.report)
        case["screen_reader_passed"] = True
        with self.assertRaisesRegex(gate.GateError, "unexpected evidence schema"):
            gate.assess(case, expected_source_sha=SHA)

    def test_driver_negative_controls_never_become_pass(self):
        for mode, expected in (
            ("missing", "step count"),
            ("reorder", "step contract"),
            ("wrong_detail", "step detail"),
            ("extra", "step count"),
            ("unknown", "step contract"),
            ("exit1", "nonzero"),
        ):
            import unittest.mock as mock
            with self.subTest(mode=mode):
                with mock.patch.dict(os.environ, {"CANOPY_FAKE_MODE": mode}):
                    try:
                        report = gate.run_driver(
                            driver=self.driver, binary=self.binary,
                            source_sha=SHA, timeout_seconds=10)
                    except gate.GateError as exc:
                        self.assertIn(expected, str(exc))
                        continue
                with self.assertRaisesRegex(gate.GateError, expected):
                    gate.assess(report, expected_source_sha=SHA)

    def test_driver_timeout_and_bad_paths_fail_closed(self):
        import unittest.mock as mock
        with mock.patch.dict(os.environ, {"CANOPY_FAKE_MODE": "sleep"}):
            with self.assertRaisesRegex(gate.GateError, "timed out"):
                gate.run_driver(driver=self.driver, binary=self.binary,
                                source_sha=SHA, timeout_seconds=gate.MIN_TIMEOUT)
        with self.assertRaises(gate.GateError):
            gate.run_driver(driver=self.root / "absent.py", binary=self.binary,
                            source_sha=SHA, timeout_seconds=10)
        with self.assertRaises(gate.GateError):
            gate.run_driver(driver=self.driver, binary=self.binary,
                            source_sha=SHA, timeout_seconds=1)

    def test_evaluate_without_evidence_is_not_run(self):
        outcome = gate.evaluate(REPO_ROOT, None, expected_source_sha=SHA)
        self.assertEqual(outcome["source_contract"], "PASS")
        self.assertEqual(outcome["compiled_qt_offscreen"]["status"], gate.NOT_RUN)
        self.assertEqual(outcome["verdict"], gate.NOT_RUN)
        self.assertEqual(outcome["screen_reader"], gate.NOT_RUN)

    def test_cli_exit_codes_for_not_run_and_valid_evidence(self):
        command = [sys.executable, "-m",
                   "tools.qa.classic_keyboard_accessibility_gate",
                   "--source-root", str(REPO_ROOT),
                   "--expected-source-sha", SHA]
        plain = subprocess.run(command, cwd=REPO_ROOT, capture_output=True,
                               text=True, timeout=90)
        self.assertEqual(plain.returncode, 2)
        self.assertIn("VERDICT " + gate.NOT_RUN, plain.stdout)
        path = self.root / "valid-report.json"
        path.write_text(json.dumps(self.report), encoding="utf-8")
        verified = subprocess.run(
            command + ["--report", str(path), "--expected-binary-sha256",
                       self.report["binary_sha256"]],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=90)
        self.assertEqual(verified.returncode, 0)
        self.assertIn("VERDICT PASS", verified.stdout)


if __name__ == "__main__":
    unittest.main()
