"""Targeted regression tests for PE-025 Classic display-change response.

Pure-Python evidence only: no compiled Qt, real monitor, Linux Mint guest,
polling service or visual claim. The tested module consumes host-supplied
display events and returns a bounded, safe Classic relayout plan.
"""
import unittest
from pathlib import Path

from canopy_features.dock.display_change_response import (
    EVENT_RESOLUTION_CHANGED, MAX_HISTORY, MAX_SUBSCRIBERS,
    MIN_HEIGHT, MIN_WIDTH, ROOT_HEIGHT, ROOT_WIDTH,
    DisplayChangeError, DisplayEvent, DisplayChangeResponse,
)
from canopy_features.dock.display_geometry_contract import validate_dock_bounds
from canopy_features.reliability.screen_topology_change import (
    Monitor, ScreenTopologyModel, Topology,
)


class FrozenGeometryTests(unittest.TestCase):
    def test_response_constants_match_frozen_classic_qml(self):
        classic = Path(__file__).resolve().parents[1] / "prototype" / "classic"
        main = (classic / "Main.qml").read_text(encoding="utf-8")
        self.assertIn("width: %d" % ROOT_WIDTH, main)
        self.assertIn("height: %d" % ROOT_HEIGHT, main)
        self.assertIn("minimumWidth: %d" % MIN_WIDTH, main)
        self.assertIn("minimumHeight: %d" % MIN_HEIGHT, main)
        # The response never invents a new presentation size: every plan is
        # bounded by the existing root and minimum constants above.
        plan = DisplayChangeResponse().handle(DisplayEvent(
            EVENT_RESOLUTION_CHANGED, width=3840, height=2160))
        self.assertLessEqual(plan.size[0], ROOT_WIDTH)
        self.assertLessEqual(plan.size[1], ROOT_HEIGHT)


class ResolutionChangeTests(unittest.TestCase):
    def test_resolution_change_returns_bounded_relayout_without_exception(self):
        response = DisplayChangeResponse()
        event = DisplayEvent(EVENT_RESOLUTION_CHANGED, connector="HDMI-1",
                             width=1920, height=1080, previous=(1366, 768))

        plan = response.handle(event)

        self.assertEqual(plan.kind, "relayout")
        self.assertEqual(plan.size, (1200, 750))
        self.assertTrue(validate_dock_bounds(*plan.size).ok)
        self.assertEqual(response.last_safe_size, (1200, 750))

    def test_below_minimum_display_holds_last_safe_layout(self):
        response = DisplayChangeResponse()
        response.handle(DisplayEvent(EVENT_RESOLUTION_CHANGED, connector="HDMI-1",
                                     width=760, height=500))
        plan = response.handle(DisplayEvent(EVENT_RESOLUTION_CHANGED,
                                            connector="HDMI-1", width=640,
                                            height=400))

        self.assertEqual(plan.kind, "hold")
        self.assertEqual(plan.size, (760, 500))
        self.assertEqual(plan.reason, "below_minimum")
        self.assertEqual(response.last_safe_size, (760, 500))

    def test_hostile_display_events_never_crash_dispatch(self):
        response = DisplayChangeResponse()
        hostile = (
            None, True, 42, "1920x1080", object(), {},
            {"kind": EVENT_RESOLUTION_CHANGED, "width": "1920", "height": 1080},
            DisplayEvent(EVENT_RESOLUTION_CHANGED, width=True, height=1080),
            DisplayEvent(EVENT_RESOLUTION_CHANGED, width=float("nan"), height=1080),
            DisplayEvent(EVENT_RESOLUTION_CHANGED, width=-1, height=0),
            DisplayEvent(EVENT_RESOLUTION_CHANGED, width=10 ** 9, height=10 ** 9),
            DisplayEvent(EVENT_RESOLUTION_CHANGED, width=1920, height=5000),
        )
        for value in hostile:
            with self.subTest(value=repr(value)[:60]):
                plan = response.handle(value)
                self.assertIn(plan.kind, {"relayout", "hold", "suspend", "no_op"})
                self.assertEqual(len(plan.size), 2)
                self.assertTrue(all(type(v) is int and v > 0 for v in plan.size))
                self.assertTrue(validate_dock_bounds(*plan.size).ok)
                self.assertEqual(plan.reason, "invalid_event")


class EventDrivenTests(unittest.TestCase):
    def test_subscriptions_are_push_only_deduplicated_and_revocable(self):
        response = DisplayChangeResponse()
        seen = []
        token = response.subscribe(seen.append)
        event = DisplayEvent(EVENT_RESOLUTION_CHANGED, connector="DP-1",
                             width=1920, height=1080)

        plan = response.handle(event)
        duplicate = response.handle(event)

        self.assertEqual(seen, [plan])
        self.assertEqual(duplicate.kind, "no_op")
        self.assertTrue(response.unsubscribe(token))
        response.handle(DisplayEvent(EVENT_RESOLUTION_CHANGED, connector="DP-1",
                                     width=1600, height=900))
        self.assertEqual(len(seen), 1)

    def test_module_has_no_polling_loop_or_background_worker(self):
        source = Path(__file__).resolve().parents[1] / "canopy_features" / "dock" \
            / "display_change_response.py"
        text = source.read_text(encoding="utf-8")
        for banned in ("import time", "import threading", "asyncio", "QTimer",
                       "while True", "sleep("):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, text)

    def test_failing_subscriber_does_not_crash_dispatch(self):
        def broken(_plan):
            raise RuntimeError("synthetic subscriber failure")

        response = DisplayChangeResponse()
        seen = []
        response.subscribe(broken)
        response.subscribe(seen.append)

        plan = response.handle(DisplayEvent(
            EVENT_RESOLUTION_CHANGED, connector="HDMI-1",
            width=1920, height=1080))

        self.assertEqual(seen, [plan])
        self.assertEqual(response.failed_notifications, 1)

    def test_subscriber_limit_and_history_are_bounded(self):
        response = DisplayChangeResponse()
        for _ in range(MAX_SUBSCRIBERS):
            response.subscribe(lambda _plan: None)
        with self.assertRaises(DisplayChangeError):
            response.subscribe(lambda _plan: None)

        for index in range(MAX_HISTORY + 10):
            response.handle(DisplayEvent(
                EVENT_RESOLUTION_CHANGED, connector="DP-1",
                width=1920 + index % 2, height=1080))
        self.assertEqual(len(response.history), MAX_HISTORY)
        self.assertEqual(response.history[-1].sequence, MAX_HISTORY + 10)


class RecoveryAdapterTests(unittest.TestCase):
    def test_existing_recovery_result_drives_a_safe_relayout(self):
        model = ScreenTopologyModel()
        model.apply(Topology([Monitor("HDMI-1", 1920, 1080, True)]))
        result = model.apply(Topology([Monitor("HDMI-1", 2560, 1440, True)]))
        response = DisplayChangeResponse()

        plan = response.handle_recovery_result(result)

        self.assertEqual(plan.kind, "relayout")
        self.assertEqual(plan.reason, "resolution_changed")
        self.assertEqual(plan.size, (1200, 750))

    def test_empty_recovery_result_suspends_without_a_resize(self):
        result = ScreenTopologyModel().apply(Topology(()))
        response = DisplayChangeResponse()

        plan = response.handle_recovery_result(result)

        self.assertEqual(plan.kind, "suspend")
        self.assertEqual(plan.reason, "no_display")
        self.assertEqual(response.last_safe_size, (1200, 750))

    def test_malformed_recovery_result_never_crashes(self):
        response = DisplayChangeResponse()
        for value in (None, True, object(), {"sequence": 1}):
            with self.subTest(value=repr(value)[:40]):
                plan = response.handle_recovery_result(value)
                self.assertEqual(plan.kind, "hold")
                self.assertEqual(plan.reason, "invalid_event")


if __name__ == "__main__":
    unittest.main()
