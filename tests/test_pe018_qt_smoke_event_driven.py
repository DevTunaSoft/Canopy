"""Targeted RED/GREEN tests for PE-018 event-driven Qt smoke startup."""
from pathlib import Path
import time
import unittest

from tools.qt_smoke import (
    LIVENESS_SECONDS,
    READY_MARKER,
    StartupFailure,
    observe_startup,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "qt_smoke.py"


class FakeProcess:
    """Bounded fake: scripted poll() results, no OS process, no real waiting."""

    def __init__(self, polls=None):
        self.polls = list(polls or [])
        self.waits = []

    def poll(self):
        return self.polls.pop(0) if self.polls else None

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return None


class EventDrivenStartupTests(unittest.TestCase):
    def test_marker_event_ends_startup_wait(self):
        chunks = iter([b"WINDOW_ACTIVATION_ADAPTER_LOADED\n",
                       READY_MARKER + b"\n"])
        pump = lambda timeout: next(chunks, None)
        process = FakeProcess()
        captured = observe_startup(process, pump=pump,
                                   deadline_seconds=1.0,
                                   liveness_seconds=0.25)
        self.assertIn(READY_MARKER, captured)
        self.assertEqual(len(process.waits), 1)
        self.assertLessEqual(process.waits[0], 0.25 + 1e-6)

    def test_early_exit_before_marker_fails_without_blind_sleep(self):
        process = FakeProcess(polls=[9])
        calls = []
        def pump(timeout):
            calls.append(timeout)
            return None
        started = time.monotonic()
        with self.assertRaises(StartupFailure) as raised:
            observe_startup(process, pump=pump, deadline_seconds=2.0,
                            liveness_seconds=0.25)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(calls, [])
        self.assertIn("exited", str(raised.exception))

    def test_exit_at_readiness_fails_immediately(self):
        process = FakeProcess(polls=[None, 4])
        def pump(timeout):
            return READY_MARKER + b"\n"
        with self.assertRaises(StartupFailure):
            observe_startup(process, pump=pump, deadline_seconds=1.0,
                            liveness_seconds=0.25)
        self.assertEqual(process.waits, [])

    def test_missing_marker_times_out_at_the_explicit_deadline(self):
        process = FakeProcess()
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            observe_startup(process, pump=lambda timeout: None,
                            deadline_seconds=0.2, liveness_seconds=0.25)
        self.assertLess(time.monotonic() - started, 1.0)

    def test_source_no_longer_uses_a_fixed_five_second_sleep(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("time.sleep(5)", text)
        self.assertIn("READY_MARKER", text)
        self.assertIn("observe_startup(process", text)
        self.assertEqual(LIVENESS_SECONDS, 5.0)


if __name__ == "__main__":
    unittest.main()
