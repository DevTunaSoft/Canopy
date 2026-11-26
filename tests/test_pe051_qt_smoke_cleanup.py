"""PE-051 regression tests: bounded Qt helper cleanup on every exit path."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

import tools.qt_smoke as qt_smoke
from tools.qt_smoke import (
    CLEANUP_TIMEOUT_SECONDS,
    MAX_STARTUP_BYTES,
    READY_DEADLINE_SECONDS,
    READY_MARKER,
    StartupFailure,
    cleanup_process,
    observe_startup,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "qt_smoke.py"


class TrackingProcess:
    """In-memory process double recording every cleanup call."""

    def __init__(self, polls=None, communicate_error=None):
        self.polls = list(polls or [])
        self.returncode = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.communicate_calls = []
        self.waits = []
        self.communicate_error = communicate_error

    def poll(self):
        if self.polls:
            code = self.polls.pop(0)
            if code is not None:
                self.returncode = code
        return self.returncode

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return None

    def terminate(self):
        self.terminate_calls += 1
        if self.returncode is None:
            self.returncode = 1

    def kill(self):
        self.kill_calls += 1
        self.returncode = 9

    def communicate(self, timeout=None):
        self.communicate_calls.append(timeout)
        if self.communicate_error is not None:
            error = self.communicate_error
            self.communicate_error = None
            raise error
        return b"", b""


class CleanupRegressionTests(unittest.TestCase):
    def test_timeout_reaps_a_real_child_before_raising(self):
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        started = time.monotonic()
        try:
            with self.assertRaises(TimeoutError) as raised:
                observe_startup(child, pump=lambda timeout: None,
                                deadline_seconds=0.2, liveness_seconds=0.25)
            elapsed = time.monotonic() - started
            self.assertIn("readiness", str(raised.exception))
            self.assertLess(elapsed, 6.0)
            self.assertIsNotNone(child.poll(),
                                 "helper is still resident after deadline")
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=3)

    def test_early_exit_reaps_pipes_before_raising(self):
        process = TrackingProcess(polls=[7])

        def forbidden_pump(timeout):
            self.fail("pump must not be called when the child already exited")

        with self.assertRaises(StartupFailure) as raised:
            observe_startup(process, pump=forbidden_pump,
                            deadline_seconds=1.0, liveness_seconds=0.25)
        self.assertIn("exited", str(raised.exception))
        self.assertEqual(process.communicate_calls, [CLEANUP_TIMEOUT_SECONDS])
        self.assertEqual(process.terminate_calls, 0)
        self.assertEqual(process.returncode, 7)

    def test_closed_channel_terminates_live_helper(self):
        process = TrackingProcess()
        with self.assertRaises(StartupFailure):
            observe_startup(process, pump=lambda timeout: b"",
                            deadline_seconds=1.0, liveness_seconds=0.25)
        self.assertEqual(process.terminate_calls, 1)
        self.assertEqual(process.communicate_calls, [CLEANUP_TIMEOUT_SECONDS])
        self.assertIsNotNone(process.returncode)

    def test_exit_at_readiness_still_cleans_up(self):
        process = TrackingProcess(polls=[None, 3])
        with self.assertRaises(StartupFailure):
            observe_startup(process, pump=lambda timeout: READY_MARKER + b"\n",
                            deadline_seconds=1.0, liveness_seconds=0.25)
        self.assertEqual(process.communicate_calls, [CLEANUP_TIMEOUT_SECONDS])
        self.assertEqual(process.returncode, 3)

    def test_main_failure_path_reaps_child_before_returning_one(self):
        real_popen = subprocess.Popen
        launched = []

        def popen(argv, **kwargs):
            child = real_popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                **kwargs)
            launched.append(child)
            return child

        real_observe = qt_smoke.observe_startup

        def fast_observe(process, **kwargs):
            kwargs["deadline_seconds"] = 0.2
            kwargs["pump"] = lambda timeout: None
            return real_observe(process, **kwargs)

        with mock.patch.object(qt_smoke.subprocess, "Popen", popen), \
                mock.patch.object(qt_smoke, "observe_startup", fast_observe), \
                mock.patch.object(sys, "argv", ["qt_smoke.py", sys.executable]), \
                contextlib.redirect_stderr(io.StringIO()):
            return_code = qt_smoke.main()

        self.assertEqual(return_code, 1)
        self.assertEqual(len(launched), 1)
        self.assertIsNotNone(launched[0].poll(),
                             "main returned 1 with a resident helper")
        if launched[0].poll() is None:
            launched[0].kill()
        launched[0].communicate(timeout=3)

    def test_stuck_helper_is_killed_with_a_second_bounded_wait(self):
        process = TrackingProcess(communicate_error=subprocess.TimeoutExpired(
            "helper", CLEANUP_TIMEOUT_SECONDS))
        cleanup_process(process, timeout_seconds=0.05)
        self.assertEqual(process.kill_calls, 1)
        self.assertEqual(process.communicate_calls, [0.05, 0.05])

    def test_cleanup_failure_does_not_mask_the_original_error(self):
        process = TrackingProcess(polls=[7],
                                  communicate_error=OSError("pipe already gone"))

        def forbidden_pump(timeout):
            self.fail("pump must not be called when the child already exited")

        with self.assertRaises(StartupFailure):
            observe_startup(process, pump=forbidden_pump,
                            deadline_seconds=1.0, liveness_seconds=0.25)

    def test_product_contract_bounds_are_preserved(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertEqual(READY_DEADLINE_SECONDS, 12.0)
        self.assertEqual(MAX_STARTUP_BYTES, 262144)
        self.assertNotIn("time.sleep(", text)
        self.assertIn("cleanup_process(process)", text)


if __name__ == "__main__":
    unittest.main()
