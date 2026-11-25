"""Offline unit tests for bounded app relaunch backoff; no Qt or Mint claims."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.reliability.app_launch_backoff import (
    ADMITTED, BACKOFF, RATE_LIMITED, SUSPENDED,
    AppLaunchBackoff, LaunchBackoffError,
)


class FakeClock:
    def __init__(self, start=0.0):
        self.t = float(start)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class ConfigTests(unittest.TestCase):
    def test_rejects_invalid_bounds_and_clock(self):
        bad = [
            {"base_delay": 0}, {"base_delay": -1}, {"base_delay": float("nan")},
            {"base_delay": float("inf")}, {"base_delay": True},
            {"max_delay": 0}, {"base_delay": 2, "max_delay": 1},
            {"max_failures": 0}, {"max_failures": 65}, {"max_failures": True},
            {"max_attempts_per_window": 0},
            {"max_attempts_per_window": 1025},
            {"window_seconds": 0}, {"window_seconds": float("nan")},
            {"max_keys": 0}, {"max_keys": 257}, {"clock": object()},
        ]
        for kwargs in bad:
            with self.subTest(kwargs=repr(kwargs)):
                with self.assertRaises(LaunchBackoffError):
                    AppLaunchBackoff(**kwargs)

    def test_rejects_invalid_keys_without_echoing_input(self):
        controller = AppLaunchBackoff()
        for key in ("", "Browser", "../etc", "has space", "a" * 129, 42, None):
            with self.subTest(key=repr(key)):
                with self.assertRaisesRegex(LaunchBackoffError,
                                            "invalid application key"):
                    controller.admit(key, now=0.0)

    def test_rejects_nonfinite_explicit_time(self):
        controller = AppLaunchBackoff()
        for now in ("0", float("nan"), float("inf"), True):
            with self.subTest(now=repr(now)):
                with self.assertRaises(LaunchBackoffError):
                    controller.admit("files", now=now)

    def test_explicit_time_never_reads_injected_clock(self):
        def boom():
            raise AssertionError("unexpected real/injected clock read")
        controller = AppLaunchBackoff(clock=boom)
        decision = controller.admit("files", now=5.0)
        self.assertEqual((decision.allowed, decision.reason), (True, ADMITTED))

    def test_injected_clock_is_used_when_time_omitted(self):
        controller = AppLaunchBackoff(clock=FakeClock(12.0))
        decision = controller.admit("files")
        self.assertTrue(decision.allowed)

    def test_decision_is_immutable(self):
        controller = AppLaunchBackoff()
        decision = controller.admit("files", now=0.0)
        with self.assertRaises(FrozenInstanceError):
            decision.allowed = False


class RepeatedCrashTests(unittest.TestCase):
    def test_backoff_grows_exponentially_then_caps(self):
        clock = FakeClock()
        controller = AppLaunchBackoff(
            base_delay=1.0, max_delay=8.0, max_failures=10,
            max_attempts_per_window=20, window_seconds=1000.0, clock=clock)
        for attempt, expected in enumerate((1.0, 2.0, 4.0, 8.0, 8.0, 8.0), 1):
            self.assertTrue(controller.admit("browser", now=clock.t).allowed)
            failure = controller.report_failure("browser", now=clock.t)
            self.assertFalse(failure.allowed)
            self.assertEqual(failure.reason, BACKOFF)
            self.assertAlmostEqual(failure.retry_after, expected)
            self.assertEqual(failure.failures, attempt)
            blocked = controller.admit("browser", now=clock.t)
            self.assertFalse(blocked.allowed)
            self.assertEqual(blocked.reason, BACKOFF)
            self.assertAlmostEqual(blocked.retry_after, expected)
            clock.advance(expected)
        self.assertTrue(controller.admit("browser", now=clock.t).allowed)

    def test_repeated_crash_suspends_until_success_or_reset(self):
        clock = FakeClock()
        controller = AppLaunchBackoff(
            max_failures=3, window_seconds=1000.0, clock=clock)
        for _ in range(3):
            controller.admit("files", now=clock.t)
            failure = controller.report_failure("files", now=clock.t)
            self.assertEqual(failure.reason,
                             SUSPENDED if failure.failures == 3 else BACKOFF)
        suspended = controller.admit("files", now=clock.t)
        self.assertFalse(suspended.allowed)
        self.assertEqual(suspended.reason, SUSPENDED)
        self.assertEqual(suspended.retry_after, 0.0)
        clock.advance(10000.0)
        self.assertEqual(controller.admit("files", now=clock.t).reason, SUSPENDED)
        controller.report_success("files")
        self.assertTrue(controller.admit("files", now=clock.t).allowed)

    def test_success_clears_backoff(self):
        controller = AppLaunchBackoff(clock=FakeClock())
        controller.admit("mail", now=0.0)
        controller.report_failure("mail", now=0.0)
        self.assertFalse(controller.admit("mail", now=0.0).allowed)
        controller.report_success("mail")
        self.assertTrue(controller.admit("mail", now=0.0).allowed)


class RateLimitTests(unittest.TestCase):
    def test_rate_limit_saturates_and_recovers_as_window_slides(self):
        clock = FakeClock()
        controller = AppLaunchBackoff(
            max_attempts_per_window=3, window_seconds=10.0, clock=clock)
        for _ in range(3):
            self.assertTrue(controller.admit("mail", now=0.0).allowed)
        saturated = controller.admit("mail", now=0.0)
        self.assertFalse(saturated.allowed)
        self.assertEqual(saturated.reason, RATE_LIMITED)
        self.assertEqual(saturated.retry_after, 10.0)
        self.assertEqual(saturated.failures, 0)

        # A reported success must not restore the exhausted rate budget.
        controller.report_success("mail")
        partial = controller.admit("mail", now=5.0)
        self.assertEqual(partial.reason, RATE_LIMITED)
        self.assertAlmostEqual(partial.retry_after, 5.0)

        # Oldest three attempts expire at t=10; saturation cannot be outrun.
        self.assertTrue(controller.admit("mail", now=10.0).allowed)
        self.assertTrue(controller.admit("mail", now=10.0).allowed)
        self.assertTrue(controller.admit("mail", now=10.0).allowed)
        self.assertEqual(controller.admit("mail", now=10.0).reason, RATE_LIMITED)

    def test_hammering_never_exceeds_window_budget(self):
        controller = AppLaunchBackoff(
            max_attempts_per_window=2, window_seconds=30.0, clock=FakeClock())
        admitted = sum(controller.admit("terminal", now=0.0).allowed
                       for _ in range(200))
        self.assertEqual(admitted, 2)

    def test_backoff_reason_wins_while_delay_exceeds_rate_window(self):
        controller = AppLaunchBackoff(
            base_delay=50.0, max_delay=50.0, max_attempts_per_window=1,
            window_seconds=10.0, clock=FakeClock())
        controller.admit("photos", now=0.0)
        controller.report_failure("photos", now=0.0)
        decision = controller.admit("photos", now=1.0)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, BACKOFF)
        self.assertAlmostEqual(decision.retry_after, 49.0)


class ResourceTests(unittest.TestCase):
    def test_tracked_keys_are_bounded_and_evicted_keys_start_fresh(self):
        clock = FakeClock()
        controller = AppLaunchBackoff(max_keys=2, clock=clock)
        for key in ("browser", "files", "mail"):
            controller.admit(key, now=0.0)
        self.assertLessEqual(controller.tracked_key_count, 2)
        controller.report_failure("mail", now=0.0)
        self.assertFalse(controller.admit("mail", now=0.0).allowed)
        controller.admit("files", now=0.0)  # mail becomes least recently used
        controller.admit("browser", now=0.0)  # evict mail
        self.assertTrue(controller.admit("mail", now=0.0).allowed)
        self.assertLessEqual(controller.tracked_key_count, 2)

    def test_reset_clears_all_state(self):
        controller = AppLaunchBackoff(max_failures=1, clock=FakeClock())
        controller.admit("files", now=0.0)
        controller.report_failure("files", now=0.0)
        controller.reset()
        self.assertEqual(controller.tracked_key_count, 0)
        self.assertTrue(controller.admit("files", now=0.0).allowed)

    def test_no_polling_timers_threads_or_process_launch_in_module(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/reliability/app_launch_backoff.py").read_text(
                    encoding="utf-8")
        for token in ("QTimer", "time.sleep", "Thread(", "asyncio",
                      "subprocess", "import socket", "while True", "Popen",
                      "os.system"):
            with self.subTest(token=token):
                self.assertNotIn(token, code)


if __name__ == "__main__":
    unittest.main()
