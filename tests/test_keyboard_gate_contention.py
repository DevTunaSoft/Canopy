"""Contention reproducibility guard and no-weakening negative controls.

The logged full-suite failure was host process-startup contention, not a
contract regression: the same 18-test module passed in other runs, and a bare
interpreter launch on this host measured a 1.2 s median (2.7 s max). These
tests prove the bounded retry absorbs exactly that transient condition while
a genuinely hanging driver, a semantically invalid report and every
deterministic failure mode still fail closed.
"""
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
import unittest.mock as mock

from tools.qa import classic_keyboard_accessibility_gate as gate

SHA = "a" * 40


def _step_lines():
    lines = []
    for step_id, _key, required in gate.STEPS:
        detail = ";".join(field + "=" + required[field]
                          for field in sorted(required))
        lines.append("\t".join((gate.STEP_PREFIX, step_id, "PASS", detail)))
    return ("\n".join(lines) + "\n").encode("utf-8")


class ContentionReproGuard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kg-contention-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.driver = self.root / "driver.py"
        self.driver.write_text("pass\n", encoding="utf-8")
        self.driver.chmod(0o700)
        self.binary = self.root / "classic.bin"
        self.binary.write_bytes(b"inert stand-in")
        self.binary.chmod(0o700)

    def run_gate(self, timeout_seconds=10):
        return gate.run_driver(driver=self.driver, binary=self.binary,
                               source_sha=SHA, timeout_seconds=timeout_seconds)

    def test_one_delayed_launch_then_success_is_absorbed(self):
        """Models the observed 10 s startup miss without sleeping 10 s."""
        outcomes = [subprocess.TimeoutExpired(["driver"], 10),
                    subprocess.CompletedProcess([], 0, _step_lines(), b"")]
        with mock.patch.object(gate.subprocess, "run", side_effect=outcomes) as run:
            report = self.run_gate()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(len(report["steps"]), len(gate.STEPS))

    def test_persistent_contention_still_fails_closed_and_bounded(self):
        with mock.patch.object(
                gate.subprocess, "run",
                side_effect=subprocess.TimeoutExpired(["driver"], 10)) as run:
            with self.assertRaisesRegex(gate.GateError, "timed out"):
                self.run_gate()
        self.assertEqual(run.call_count, gate.MAX_DRIVER_ATTEMPTS)
        self.assertLessEqual(run.call_count, 4)

    def test_real_hanging_driver_is_not_rescued(self):
        """Real subprocess negative control: sleep driver must still FAIL."""
        self.driver.write_text("import time\ntime.sleep(6)\n", encoding="utf-8")
        started = time.monotonic()
        with self.assertRaisesRegex(gate.GateError, "timed out"):
            gate.run_driver(driver=self.driver, binary=self.binary,
                            source_sha=SHA, timeout_seconds=gate.MIN_TIMEOUT)
        self.assertGreaterEqual(time.monotonic() - started, gate.MIN_TIMEOUT)

    def test_real_fast_driver_still_passes(self):
        self.driver.write_text(
            "import os\nfor line in os.environ['CANOPY_STEPS'].split('|'):\n"
            "    print(line, flush=True)\n", encoding="utf-8")
        steps = "|".join(_step_lines().decode("utf-8").splitlines())
        with mock.patch.dict(os.environ, {"CANOPY_STEPS": steps}):
            # Positive control for a fast driver: give the real process a
            # generous per-attempt bound on this contended host. The gate's
            # own timeout bounds and negative controls stay strict below.
            report = self.run_gate(timeout_seconds=60)
        self.assertEqual(report["platform"], "offscreen")
        self.assertEqual(len(report["steps"]), len(gate.STEPS))

    def test_semantic_rejection_is_unchanged(self):
        """Order and detail guards still reject; retry never masks a bad report."""
        bad = {
            "schema": gate.SCHEMA, "kind": gate.KIND, "platform": "offscreen",
            "source_sha": SHA, "binary_sha256": "b" * 64,
            "driver": gate.COMPILED_DRIVER, "input_mode": "keyboard-only",
            "screen_reader": gate.NOT_RUN, "mint_acceptance": gate.NOT_RUN,
            "visual_approval": gate.NOT_RUN,
        }
        steps = []
        for line in _step_lines().decode("utf-8").splitlines():
            step = gate._parse_step_line(line)
            step["key"] = ""
            steps.append(step)
        bad["steps"] = steps
        with self.assertRaisesRegex(gate.GateError, "step contract"):
            gate.assess(bad, expected_source_sha=SHA)
        bad["steps"][0], bad["steps"][1] = bad["steps"][1], bad["steps"][0]
        with self.assertRaisesRegex(gate.GateError, "step contract"):
            gate.assess(bad, expected_source_sha=SHA)

    def test_retry_cannot_be_disabled_by_a_caller_flag(self):
        """Narrow guard: no public escape hatch that raises the timeout bound."""
        self.assertEqual(gate.MAX_DRIVER_ATTEMPTS, 2)
        self.assertEqual(gate.MIN_TIMEOUT, 2)
        self.assertEqual(gate.MAX_TIMEOUT, 90)
        self.assertFalse(hasattr(gate, "DISABLE_DRIVER_RETRY"))
        self.assertIn("timeout_seconds", gate.run_driver.__code__.co_varnames)


if __name__ == "__main__":
    unittest.main()
