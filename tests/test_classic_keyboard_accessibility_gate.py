"""Deterministic regression tests for bounded keyboard-driver coordination.

These tests never launch a real Qt binary and never weaken the gate. A mocked
TimeoutExpired models a host-scheduled start that missed its budget; every
other failure mode is asserted to remain a single-attempt, fail-closed result.
"""
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
import unittest.mock as mock

from tools.qa import classic_keyboard_accessibility_gate as gate

SHA = "a" * 40


def _valid_stdout():
    """Build protocol lines from the pinned steps, without any Qt binary."""
    lines = []
    for step_id, _key, required in gate.STEPS:
        detail = ";".join(field + "=" + required[field]
                          for field in sorted(required))
        lines.append("\t".join((gate.STEP_PREFIX, step_id, "PASS", detail)))
    return ("\n".join(lines) + "\n").encode("utf-8")


class _DriverFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kg-regression-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.driver = self.root / "driver.py"
        self.driver.write_text("pass\n", encoding="utf-8")
        self.driver.chmod(0o700)
        self.binary = self.root / "classic.bin"
        self.binary.write_bytes(b"inert stand-in")
        self.binary.chmod(0o700)

    def run_gate(self):
        return gate.run_driver(driver=self.driver, binary=self.binary,
                               source_sha=SHA, timeout_seconds=10)

    def good_result(self):
        return subprocess.CompletedProcess([], 0, _valid_stdout(), b"")


class BoundedRetryTests(_DriverFixture):
    def test_transient_timeout_is_retried_with_identical_inputs(self):
        outcomes = [subprocess.TimeoutExpired(["driver"], 10), self.good_result()]
        calls = []

        def fake_run(command, **kwargs):
            calls.append((tuple(command), dict(kwargs)))
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with mock.patch.object(gate.subprocess, "run", side_effect=fake_run):
            report = self.run_gate()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1], "retry must reuse identical inputs")
        self.assertEqual(calls[0][1]["timeout"], 10)
        self.assertEqual(len(report["steps"]), len(gate.STEPS))
        for step, (step_id, _key, required) in zip(report["steps"], gate.STEPS):
            self.assertEqual(step["id"], step_id)
            self.assertEqual(set(step["detail"]), set(required))

    def test_persistent_timeout_fails_closed_after_bounded_attempts(self):
        with mock.patch.object(
                gate.subprocess, "run",
                side_effect=subprocess.TimeoutExpired(["driver"], 10)) as run:
            with self.assertRaisesRegex(gate.GateError, "timed out"):
                self.run_gate()
        self.assertEqual(run.call_count, gate.MAX_DRIVER_ATTEMPTS)

    def test_os_error_is_never_retried(self):
        with mock.patch.object(gate.subprocess, "run",
                               side_effect=OSError("cannot start")) as run:
            with self.assertRaisesRegex(gate.GateError, "could not be started"):
                self.run_gate()
        self.assertEqual(run.call_count, 1)

    def test_nonzero_exit_is_never_retried(self):
        result = subprocess.CompletedProcess([], 3, b"", b"")
        with mock.patch.object(gate.subprocess, "run", return_value=result) as run:
            with self.assertRaisesRegex(gate.GateError, "exited nonzero"):
                self.run_gate()
        self.assertEqual(run.call_count, 1)

    def test_malformed_step_output_is_never_retried(self):
        result = subprocess.CompletedProcess(
            [], 0, b"CANOPY_A11Y_STEP\tonly-three-fields\n", b"")
        with mock.patch.object(gate.subprocess, "run", return_value=result) as run:
            with self.assertRaisesRegex(gate.GateError, "malformed driver step"):
                self.run_gate()
        self.assertEqual(run.call_count, 1)

    def test_per_attempt_timeout_bounds_are_unchanged(self):
        self.assertEqual(gate.MIN_TIMEOUT, 2)
        self.assertEqual(gate.MAX_TIMEOUT, 90)
        self.assertEqual(gate.MAX_DRIVER_ATTEMPTS, 2)
        for bad in (1, 91, True, 10.0, "10"):
            with self.subTest(bad=bad):
                with mock.patch.object(gate.subprocess, "run") as run:
                    with self.assertRaises(gate.GateError):
                        gate.run_driver(
                            driver=self.driver, binary=self.binary,
                            source_sha=SHA, timeout_seconds=bad)
                self.assertEqual(run.call_count, 0)

    def test_retried_report_keeps_full_fail_closed_schema(self):
        outcomes = [subprocess.TimeoutExpired(["driver"], 10), self.good_result()]
        with mock.patch.object(gate.subprocess, "run", side_effect=outcomes):
            report = self.run_gate()
        self.assertEqual(set(report), gate.REPORT_KEYS)
        self.assertEqual(report["platform"], "offscreen")
        self.assertEqual(report["input_mode"], "keyboard-only")
        for field in ("screen_reader", "mint_acceptance", "visual_approval"):
            self.assertEqual(report[field], gate.NOT_RUN)


class LaunchCoordinationTests(_DriverFixture):
    def test_concurrent_launches_are_serialised(self):
        state = {"active": 0, "peak": 0, "errors": [], "reports": []}
        guard = threading.Lock()

        def fake_run(command, **kwargs):
            with guard:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time.sleep(0.02)
            with guard:
                state["active"] -= 1
            return self.good_result()

        def worker():
            try:
                state["reports"].append(self.run_gate())
            except Exception as exc:  # pragma: no cover - surfaced by assertion
                state["errors"].append(repr(exc))

        with mock.patch.object(gate.subprocess, "run", side_effect=fake_run):
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertEqual(state["errors"], [])
        self.assertEqual(len(state["reports"]), 4)
        self.assertEqual(state["peak"], 1,
                         "driver launches in one process must be coordinated")


if __name__ == "__main__":
    unittest.main()
