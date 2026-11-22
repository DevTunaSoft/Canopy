"""Offline tests for bounded, explicitly observed application process events.

No real process, clock, clock read, desktop session or Qt runtime is used.
These tests verify Python logic only; they are not Mint or compiled-Qt evidence.
"""

from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.apps.process_exit_events import (
    CRASH_LOOP, DEFAULT_MAX_EVENTS, EXIT, KINDS, MAX_APPS, MAX_EVENTS,
    MAX_EXIT_CODE, MAX_PID, PID_REUSED, PROTOCOL_VERSION, START,
    ProcessEvent, ProcessEventError, ProcessLifecycle,
)


class ProcessLifecycleTests(unittest.TestCase):
    def test_start_clean_exit_and_immutable_bounded_events(self):
        tracker = ProcessLifecycle()
        self.assertEqual(PROTOCOL_VERSION, 1)
        self.assertEqual(KINDS, frozenset({START, EXIT, PID_REUSED, CRASH_LOOP}))
        self.assertEqual(DEFAULT_MAX_EVENTS, 128)

        started = tracker.start("editor", 4242, 1)
        self.assertEqual(
            [(e.kind, e.sequence, e.app_id, e.pid, e.generation, e.observed_at)
             for e in started],
            [(START, 1, "editor", 4242, 1, 1)],
        )
        self.assertEqual(tracker.live_generation("editor"), 1)
        self.assertIsNone(tracker.live_generation("browser"))
        ended = tracker.exit("editor", 4242, 1, 2, 0)
        self.assertEqual(
            [(e.kind, e.sequence, e.exit_code) for e in ended],
            [(EXIT, 2, 0)],
        )
        self.assertIsNone(tracker.live_generation("editor"))

        event = tracker.events()[0]
        self.assertIsInstance(event, ProcessEvent)
        with self.assertRaises(FrozenInstanceError):
            event.kind = PID_REUSED
        self.assertEqual([e.sequence for e in tracker.events()], [1, 2])
        self.assertEqual(tracker.event_count, 2)

    def test_pid_reuse_stale_exit_is_ignored(self):
        tracker = ProcessLifecycle()
        tracker.start("editor", 100, 1)
        tracker.exit("editor", 100, 1, 2, 0)
        second = tracker.start("browser", 100, 3)
        self.assertEqual(second[0].generation, 2)

        stale = tracker.exit("editor", 100, 1, 4, 1)
        self.assertEqual(stale, ())
        self.assertEqual(tracker.live_generation("browser"), 2)
        self.assertEqual(tracker.event_count, 3)

        # The rejected observation did not advance monotonic time.
        fresh = tracker.exit("browser", 100, 2, 3.5, 0)
        self.assertEqual([e.kind for e in fresh], [EXIT])
        self.assertEqual([e.kind for e in tracker.events()],
                         [START, EXIT, START, EXIT])

    def test_pid_reuse_with_missed_exit_forces_retirement(self):
        tracker = ProcessLifecycle()
        tracker.start("editor", 200, 1)
        reused = tracker.start("browser", 200, 2)
        self.assertEqual(
            [(e.kind, e.app_id, e.generation) for e in reused],
            [(PID_REUSED, "editor", 1), (START, "browser", 2)],
        )
        self.assertIsNone(tracker.live_generation("editor"))
        self.assertEqual(tracker.live_generation("browser"), 2)

        self.assertEqual(tracker.exit("editor", 200, 1, 3, 1), ())
        self.assertEqual([e.kind for e in tracker.exit("browser", 200, 2, 4, 0)],
                         [EXIT])

    def test_crash_loop_detected_once_then_rearmed(self):
        tracker = ProcessLifecycle()
        clock = 1
        for _ in range(3):
            tracker.start("viewer", 300, clock)
            clock += 0.5
            tracker.exit("viewer", 300, tracker.live_generation("viewer")
                         or 0, clock, 1)
            clock += 0.5
        self.assertTrue(tracker.is_crash_looping("viewer"))
        self.assertEqual([e.kind for e in tracker.events()].count(CRASH_LOOP), 1)
        self.assertEqual(tracker.events()[-1].kind, CRASH_LOOP)
        self.assertEqual(tracker.events()[-1].exit_code, 1)

        tracker.start("viewer", 300, clock)
        clock += 1
        fourth = tracker.exit("viewer", 300, tracker.live_generation("viewer"),
                              clock, 9)
        self.assertEqual([e.kind for e in fourth], [EXIT])
        self.assertEqual([e.kind for e in tracker.events()].count(CRASH_LOOP), 1)

        tracker.start("viewer", 300, clock + 1)
        recovered = tracker.exit("viewer", 300,
                                 tracker.live_generation("viewer"), clock + 2, 0)
        self.assertEqual([e.kind for e in recovered], [EXIT])
        self.assertFalse(tracker.is_crash_looping("viewer"))

        for attempt, moment in enumerate((clock + 3, clock + 5, clock + 7)):
            tracker.start("viewer", 300, moment)
            fresh = tracker.exit("viewer", 300,
                                 tracker.live_generation("viewer"),
                                 moment + 1, 1)
            if attempt < 2:
                self.assertEqual([e.kind for e in fresh], [EXIT])
                self.assertFalse(tracker.is_crash_looping("viewer"))
            else:
                self.assertEqual([e.kind for e in fresh], [EXIT, CRASH_LOOP])
                self.assertTrue(tracker.is_crash_looping("viewer"))
        self.assertEqual([e.kind for e in tracker.events()].count(CRASH_LOOP), 2)

    def test_crash_window_ignores_old_failures(self):
        tracker = ProcessLifecycle(crash_window=10, crash_threshold=2)
        for moment in (1, 5):
            tracker.start("shell", 500, moment)
            tracker.exit("shell", 500, tracker.live_generation("shell"),
                         moment + 0.5, 1)
        self.assertTrue(tracker.is_crash_looping("shell"))

        tracker.clear_crash_state("shell")
        self.assertFalse(tracker.is_crash_looping("shell"))
        for moment in (20, 21):
            tracker.start("shell", 500, moment)
            tracker.exit("shell", 500, tracker.live_generation("shell"),
                         moment + 0.5, 1)
        self.assertTrue(tracker.is_crash_looping("shell"))
        self.assertEqual([e.kind for e in tracker.events()].count(CRASH_LOOP), 2)

    def test_event_history_and_stored_state_are_bounded(self):
        tracker = ProcessLifecycle(max_events=4, max_apps=2)
        for index in range(6):
            app = "app" + str(index % 2)
            tracker.start(app, 600 + index, index)
            tracker.exit(app, 600 + index,
                         tracker.live_generation(app), index + 0.5, 0)
        self.assertEqual(tracker.event_count, 4)
        self.assertEqual([e.sequence for e in tracker.events()], [9, 10, 11, 12])
        self.assertLessEqual(len(tracker._live_by_app), 2)
        self.assertLessEqual(len(tracker._live_by_pid), 2)
        self.assertLessEqual(len(tracker._recent_exits), 2)
        self.assertLessEqual(len(tracker._crash_looping), 2)
        for recent in tracker._recent_exits.values():
            self.assertLessEqual(len(recent), 16)

    def test_application_limit_fails_closed(self):
        tracker = ProcessLifecycle(max_apps=1)
        tracker.start("first", 700, 1)
        with self.assertRaisesRegex(ProcessEventError, "application limit"):
            tracker.start("second", 701, 2)
        self.assertEqual(tracker.event_count, 1)
        self.assertEqual(tracker.live_generation("first"), 1)

        # A free slot can be reused after an explicit clean exit.
        tracker.exit("first", 700, 1, 3, 0)
        tracker.start("second", 701, 4)
        self.assertEqual(tracker.live_generation("second"), 2)

    def test_invalid_observations_rejected_without_mutation(self):
        tracker = ProcessLifecycle()
        tracker.start("valid", 800, 10)
        cases = (
            ("bad id", lambda: tracker.start("Bad", 801, 11)),
            ("bad pid", lambda: tracker.start("valid", 0, 11)),
            ("huge pid", lambda: tracker.start("valid", MAX_PID + 1, 11)),
            ("bool pid", lambda: tracker.start("valid", True, 11)),
            ("backwards time", lambda: tracker.start("valid", 801, 9)),
            ("nan time", lambda: tracker.start("valid", 801, float("nan"))),
            ("infinite time", lambda: tracker.start("valid", 801, float("inf"))),
            ("string time", lambda: tracker.start("valid", 801, "11")),
            ("bad generation", lambda: tracker.exit("valid", 800, 0, 11)),
            ("bool generation", lambda: tracker.exit("valid", 800, True, 11)),
            ("bad exit code", lambda: tracker.exit("valid", 800, 1, 11, 256)),
            ("bool exit code", lambda: tracker.exit("valid", 800, 1, 11, True)),
        )
        for label, action in cases:
            with self.subTest(label=label):
                with self.assertRaises(ProcessEventError):
                    action()
        self.assertEqual(tracker.event_count, 1)
        self.assertEqual(tracker.live_generation("valid"), 1)
        self.assertEqual(MAX_EXIT_CODE, 255)

        for kwargs in ({"max_events": 0}, {"max_events": MAX_EVENTS + 1},
                       {"max_apps": True}, {"crash_window": -1},
                       {"crash_threshold": 0}, {"crash_threshold": 1.0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ProcessEventError):
                    ProcessLifecycle(**kwargs)

    def test_source_has_no_os_clock_poll_or_network_capability(self):
        code = (Path(__file__).resolve().parents[1]
                / "canopy_features/apps/process_exit_events.py").read_text()
        for forbidden in ("import os", "import time", "import signal",
                          "import subprocess", "import threading",
                          "import asyncio", "import socket", "import importlib",
                          "QTimer", "Thread(", "time.sleep", "while True"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)

    def test_replay_is_deterministic_and_platform_neutral(self):
        def replay():
            tracker = ProcessLifecycle()
            tracker.start("browser", 999999, 1)
            tracker.start("browser", 999999, 2)
            tracker.exit("browser", 999999, 1, 3, 1)  # stale generation
            for attempt in range(3):
                moment = 4 + attempt * 2
                tracker.start("browser", 999999, moment)
                tracker.exit("browser", 999999,
                             tracker.live_generation("browser"),
                             moment + 1, 1)
            return tracker.events()

        first, second = replay(), replay()
        self.assertEqual(first, second)
        self.assertEqual([e.kind for e in first[:3]],
                         [START, PID_REUSED, START])
        self.assertEqual(first[-1].kind, CRASH_LOOP)
        self.assertEqual(first[-1].pid, 999999)

    def test_reset_close_and_crash_state_cleanup(self):
        tracker = ProcessLifecycle()
        for attempt in range(3):
            moment = 1 + attempt
            tracker.start("notes", 900, moment)
            tracker.exit("notes", 900, tracker.live_generation("notes"),
                         moment + 0.5, 1)
        self.assertTrue(tracker.is_crash_looping("notes"))

        tracker.clear_crash_state("notes")
        self.assertFalse(tracker.is_crash_looping("notes"))
        tracker.reset()
        self.assertEqual(tracker.event_count, 0)
        self.assertIsNone(tracker.live_generation("notes"))
        self.assertFalse(tracker.closed)

        tracker.start("notes", 901, 1)
        tracker.close()
        tracker.close()
        self.assertTrue(tracker.closed)
        self.assertEqual(tracker.event_count, 0)
        for action in (lambda: tracker.start("notes", 902, 2),
                       lambda: tracker.exit("notes", 901, 1, 2),
                       lambda: tracker.clear_crash_state("notes"),
                       tracker.reset):
            with self.assertRaises(ProcessEventError):
                action()
        with self.assertRaises(ProcessEventError):
            tracker.is_crash_looping("Invalid")


if __name__ == "__main__":
    unittest.main()
