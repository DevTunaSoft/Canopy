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


def _positive_report_with_mocked_driver(driver, binary, timeout_seconds=10):
    """Build the inert positive report without launching a child process.

    The eleven protocol lines are derived from the pinned ``gate.STEPS``
    contract and delivered through a mocked ``CompletedProcess`` to the real
    ``run_driver`` parser. This keeps the report schema and all step/claim
    assertions intact while removing host-scheduling dependence from the
    positive fixture. Negative controls in the tests below keep using real
    subprocess launches.
    """
    import unittest.mock as mock

    lines = [
        "\t".join((gate.STEP_PREFIX, step_id, "PASS",
                   ";".join("{}={}".format(name, value)
                            for name, value in detail.items())))
        for step_id, _key, detail in gate.STEPS
    ]
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    completed = subprocess.CompletedProcess([], 0, payload, b"")
    with mock.patch.object(gate.subprocess, "run", return_value=completed) as run:
        report = gate.run_driver(
            driver=driver, binary=binary, source_sha=SHA,
            timeout_seconds=timeout_seconds)
        calls = list(run.call_args_list)
    return report, calls


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
        self.report, _ = _positive_report_with_mocked_driver(
            self.driver, self.binary, timeout_seconds=10)

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

    def test_positive_fixture_has_no_real_subprocess_launch(self):
        report, calls = _positive_report_with_mocked_driver(
            self.driver, self.binary)
        self.assertEqual(report, self.report)
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(args[0], [sys.executable, str(self.driver)])
        self.assertEqual(kwargs["timeout"], 10)
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(kwargs["stderr"], subprocess.PIPE)
        self.assertEqual(len(self.report["steps"]), len(gate.STEPS))

    def test_negative_controls_still_launch_a_real_subprocess(self):
        import unittest.mock as mock

        real_run = gate.subprocess.run
        calls = []

        def recording_run(command, **kwargs):
            calls.append((list(command), dict(kwargs)))
            return real_run(command, **kwargs)

        with mock.patch.object(gate.subprocess, "run", side_effect=recording_run):
            with mock.patch.dict(os.environ, {"CANOPY_FAKE_MODE": "sleep"}):
                with self.assertRaisesRegex(gate.GateError, "timed out"):
                    gate.run_driver(driver=self.driver, binary=self.binary,
                                    source_sha=SHA,
                                    timeout_seconds=gate.MIN_TIMEOUT)
        self.assertEqual(len(calls), gate.MAX_DRIVER_ATTEMPTS)
        for command, kwargs in calls:
            self.assertEqual(command, [sys.executable, str(self.driver)])
            self.assertEqual(kwargs["timeout"], gate.MIN_TIMEOUT)
            self.assertFalse(kwargs["shell"])

        calls.clear()
        with mock.patch.object(gate.subprocess, "run", side_effect=recording_run):
            with mock.patch.dict(os.environ, {"CANOPY_FAKE_MODE": "exit1"}):
                with self.assertRaisesRegex(gate.GateError, "nonzero"):
                    gate.run_driver(driver=self.driver, binary=self.binary,
                                    source_sha=SHA, timeout_seconds=10)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], [sys.executable, str(self.driver)])
        self.assertFalse(calls[0][1]["shell"])

    def test_gate_bounds_and_defaults_are_unchanged(self):
        import inspect

        self.assertEqual(gate.MIN_TIMEOUT, 2)
        self.assertEqual(gate.MAX_TIMEOUT, 90)
        self.assertEqual(gate.MAX_DRIVER_ATTEMPTS, 2)
        self.assertEqual(inspect.signature(gate.run_driver).parameters[
            "timeout_seconds"].default, 25)
        self.assertEqual(inspect.signature(gate.run_compiled_self_test).parameters[
            "timeout_seconds"].default, 30)
        source = Path(gate.__file__).read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--timeout", type=int, default=30)',
                      source)

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


# Exact marker lines observed from the compiled Classic binary at d53f0e7 with
# QT_QPA_PLATFORM=offscreen and the built-in self-test hooks.
REAL_LAUNCHER_MARKERS = (
    "SELF_TEST_PASS: quick controls registered and fail closed",
    "SELF_TEST_PASS: actual launcher image component count 8",
    "SELF_TEST_PASS: actual launcher button image geometry centered 8",
    "SELF_TEST_PASS: actual Qt launcher opens, searches and closes",
    "SELF_TEST_PASS: Files dock hide/restore and activity indicator",
    "SELF_TEST_PASS: Files close control and dock reopen",
    "SELF_TEST_PASS: Files keyboard close and reopen bindings",
    "SELF_TEST_PASS: dock icons horizontally/vertically centred count 8 with equal 54px art slots and 7px minimum dock insets",
    "SELF_TEST_PASS: nonuniform window screenshot captured QSize(1200, 750) sampled colors 75",
    "SELF_TEST_PASS: actual launcher overlay screenshot captured QSize(1200, 750)",
)
REAL_ACTIVATION_MARKERS = (
    "SELF_TEST_PASS: dock running and active indicators reflect trusted snapshot",
    "SELF_TEST_PASS: dock activation intent reaches host gate without false focus",
    "SELF_TEST_PASS: closed snapshot clears running and active indicators",
    "SELF_TEST_PASS: untrusted snapshot clears all indicators",
    "WINDOW_ACTIVATION_HOST_SELF_TEST_PASS running=ok active=ok closed=ok fail_closed=ok",
    "SELF_TEST_PASS: quick controls registered in compiled shell",
    "QUICK_CONTROLS_FIXTURE_PASS: opener wired, four domains fail closed, approved visuals unchanged",
)


def _marker_bytes(lines):
    return ("\n".join(lines) + "\n").encode("utf-8")


class CompiledSelfTestHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "classic.exe"
        self.binary.write_bytes(b"compiled-binary-stand-in")
        self.binary.chmod(0o700)
        self.art = self.root / "approved"
        self.art.mkdir()
        (self.art / "manifest.json").write_text("{}", encoding="utf-8")
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.markers = {
            "launcher": REAL_LAUNCHER_MARKERS,
            "activation": REAL_ACTIVATION_MARKERS,
        }

    def _fake_run(self, calls):
        import unittest.mock as mock

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            payload = (REAL_ACTIVATION_MARKERS
                       if "--self-test-window-activation-fixture" in command
                       else REAL_LAUNCHER_MARKERS)
            for index, argument in enumerate(command):
                if argument in ("--self-test-screenshot",
                                "--self-test-launcher-screenshot"):
                    Path(command[index + 1]).write_bytes(
                        gate.PNG_SIGNATURE + b"bounded-fake-png")
            return subprocess.CompletedProcess(command, 0, b"",
                                               _marker_bytes(payload))
        return mock.patch.object(gate.subprocess, "run", side_effect=runner)

    def test_real_compiled_markers_map_to_all_eleven_pinned_steps(self):
        lines = gate._compiled_step_lines(self.markers,
                                          gate.inspect_source(REPO_ROOT))
        self.assertEqual(len(lines), len(gate.STEPS))
        steps = [gate._parse_step_line(line) for line in lines]
        for step, (step_id, key, detail) in zip(steps, gate.STEPS):
            step["key"] = key
            self.assertEqual(step["id"], step_id)
            self.assertEqual(set(step["detail"]), set(detail))
            for field, expected in detail.items():
                self.assertEqual(step["detail"][field], expected)
        evidence = {"execution": "compiled-binary-self-test", "invocations": 2}
        verdict = gate.assess(
            {"schema": gate.SCHEMA, "kind": gate.KIND,
             "platform": "offscreen", "source_sha": SHA,
             "binary_sha256": BINARY, "driver": gate.COMPILED_DRIVER,
             "input_mode": "keyboard-only", "steps": steps,
             "screen_reader": gate.NOT_RUN,
             "mint_acceptance": gate.NOT_RUN,
             "visual_approval": gate.NOT_RUN},
            expected_source_sha=SHA,
            expected_binary_sha256=BINARY, compiled_evidence=evidence)
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(verdict["compiled_self_test"], evidence)
        self.assertIn("source contracts", verdict["scope"])

    def test_missing_duplicate_and_source_drift_fail_closed(self):
        key_marker = "SELF_TEST_PASS: actual Qt launcher opens, searches and closes"
        without = tuple(line for line in REAL_LAUNCHER_MARKERS
                        if line != key_marker)
        with self.assertRaisesRegex(gate.GateError, "missing compiled marker"):
            gate._compiled_step_lines(
                {"launcher": without, "activation": REAL_ACTIVATION_MARKERS},
                {"status": "PASS"})
        with self.assertRaisesRegex(gate.GateError, "duplicate compiled marker"):
            gate._compiled_step_lines(
                {"launcher": REAL_LAUNCHER_MARKERS + (key_marker,),
                 "activation": REAL_ACTIVATION_MARKERS},
                {"status": "PASS"})
        with self.assertRaisesRegex(gate.GateError, "source contract must pass"):
            gate._compiled_step_lines(self.markers, {"status": "FAIL"})
        import unittest.mock as mock
        drifted = tuple((step_id + "_x", key, detail)
                        for step_id, key, detail in gate.STEPS)
        with mock.patch.object(gate, "STEPS", drifted):
            with self.assertRaisesRegex(gate.GateError, "drifted"):
                gate._compiled_step_lines(self.markers, {"status": "PASS"})

    def test_harness_executes_two_bounded_offscreen_invocations(self):
        calls = []
        with self._fake_run(calls):
            report, evidence = gate.run_compiled_self_test(
                binary=self.binary, approved_art_dir=self.art,
                source_root=REPO_ROOT, source_sha=SHA,
                artifact_dir=self.artifacts, timeout_seconds=12)
        self.assertEqual(len(calls), 2)
        self.assertEqual(report["driver"], gate.COMPILED_DRIVER)
        self.assertEqual(len(report["steps"]), len(gate.STEPS))
        self.assertEqual(evidence["invocations"], 2)
        self.assertEqual(evidence["execution"], "compiled-binary-self-test")
        self.assertEqual(len(evidence["screenshots_sha256"]), 2)
        self.assertTrue(evidence["observed_marker_lines"]["launcher"])
        self.assertTrue(evidence["observed_marker_lines"]["activation"])
        for command, kwargs in calls:
            self.assertEqual(kwargs["env"]["QT_QPA_PLATFORM"], "offscreen")
            self.assertEqual(kwargs["env"]["QT_FORCE_STDERR_LOGGING"], "1")
            self.assertNotIn("DISPLAY", kwargs["env"])
            self.assertFalse(kwargs["shell"])
            self.assertEqual(kwargs["timeout"], 12)
        self.assertIn("--self-test-window-activation-fixture", calls[1][0])
        self.assertIn("--self-test-launcher-screenshot", calls[0][0])
        self.assertTrue((self.artifacts / "canopy-keyboard-desktop.png").is_file())
        self.assertTrue((self.artifacts / "canopy-keyboard-launcher.png").is_file())
        outcome = gate.evaluate(REPO_ROOT, report, expected_source_sha=SHA,
                                expected_binary_sha256=report["binary_sha256"],
                                compiled_evidence=evidence)
        self.assertEqual(outcome["verdict"], "PASS")
        self.assertEqual(outcome["execution"], "compiled-binary-self-test")

    def test_harness_rejects_failure_marker_nonzero_exit_and_bad_inputs(self):
        import unittest.mock as mock
        for payload, expected in (
            (_marker_bytes(["SELF_TEST_FAIL: injected"]), "failure marker"),
            (b"", "missing compiled launcher marker"),
        ):
            with self.subTest(expected=expected):
                with mock.patch.object(gate.subprocess, "run", return_value=
                                       subprocess.CompletedProcess([], 0, b"", payload)):
                    with self.assertRaisesRegex(gate.GateError, expected):
                        gate.run_compiled_self_test(
                            binary=self.binary, approved_art_dir=self.art,
                            source_root=REPO_ROOT, source_sha=SHA)
        with mock.patch.object(gate.subprocess, "run", return_value=
                               subprocess.CompletedProcess([], 3, b"", b"")):
            with self.assertRaisesRegex(gate.GateError, "exited nonzero"):
                gate.run_compiled_self_test(
                    binary=self.binary, approved_art_dir=self.art,
                    source_root=REPO_ROOT, source_sha=SHA)
        for size in ("719x480", "1200X750", "3841x2160", "1200x750x1"):
            with self.subTest(size=size):
                with self.assertRaises(gate.GateError):
                    gate.run_compiled_self_test(
                        binary=self.binary, approved_art_dir=self.art,
                        source_root=REPO_ROOT, source_sha=SHA, size=size)

    def test_cli_compiled_mode_reports_execution_and_rejects_mixing(self):
        import unittest.mock as mock
        evidence = {"execution": "compiled-binary-self-test", "invocations": 2}
        report = {"schema": gate.SCHEMA, "kind": gate.KIND,
                  "platform": "offscreen", "source_sha": SHA,
                  "binary_sha256": BINARY, "driver": gate.COMPILED_DRIVER,
                  "input_mode": "keyboard-only", "steps": [],
                  "screen_reader": gate.NOT_RUN,
                  "mint_acceptance": gate.NOT_RUN,
                  "visual_approval": gate.NOT_RUN}
        base = ["--source-root", str(REPO_ROOT), "--expected-source-sha", SHA]
        compiled_args = ["--compiled-binary", str(self.binary),
                         "--approved-art-dir", str(self.art)]
        with mock.patch.object(gate, "run_compiled_self_test",
                               return_value=(report, evidence)):
            self.assertEqual(gate.main(base + compiled_args), 1)
            self.assertEqual(gate.main(base + compiled_args +
                                       ["--expected-binary-sha256", BINARY]), 1)
            full = dict(report)
            full["steps"] = [gate._parse_step_line(line) for line in
                             gate._compiled_step_lines(
                                 self.markers, gate.inspect_source(REPO_ROOT))]
            for step, (_, key, _) in zip(full["steps"], gate.STEPS):
                step["key"] = key
            with mock.patch.object(gate, "run_compiled_self_test",
                                   return_value=(full, evidence)):
                output = self.root / "compiled-outcome.json"
                self.assertEqual(gate.main(base + compiled_args + [
                    "--expected-binary-sha256", BINARY,
                    "--json-out", str(output)]), 0)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["execution"], "compiled-binary-self-test")
        self.assertEqual(payload["compiled_qt_offscreen"]["status"], "PASS")
        self.assertEqual(gate.main(base + [
            "--compiled-binary", str(self.binary),
            "--approved-art-dir", str(self.art), "--report", str(output)]), 1)


if __name__ == "__main__":
    unittest.main()
