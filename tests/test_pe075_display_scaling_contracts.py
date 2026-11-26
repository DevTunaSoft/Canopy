"""Targeted regression tests for PE-075 logical-DPI scaling source contracts.

Pure Python evidence only: no compiled Qt, real monitor change, Linux Mint
guest, polling service or visual claim. The tested boundary converts a host
physical-size + DPI signal into a bounded logical Classic relayout plan.
"""
import ast
import unittest
from pathlib import Path

from canopy_features.dock.display_change_response import (
    EVENT_DPI_CHANGED, MAX_HISTORY, ROOT_HEIGHT, ROOT_WIDTH,
    DisplayChangeError, DisplayEvent, DisplayChangeResponse,
)
from canopy_features.dock.display_geometry_contract import validate_dock_bounds
from canopy_features.dock.display_scaling_contract import (
    MAX_SCALE, DisplayScalingError, logical_size_from_physical, validate_scale,
)

REASON_DPI = "logical_dpi_changed"
REASON_SAME_LOGICAL_SIZE = "logical_size_unchanged"


class ScalingSourceContractTests(unittest.TestCase):
    def test_scaling_modules_are_pure_source_contracts(self):
        root = Path(__file__).resolve().parents[1] / "canopy_features" / "dock"
        for name in ("display_scaling_contract.py", "display_change_response.py"):
            with self.subTest(name=name):
                text = (root / name).read_text(encoding="utf-8")
                for banned in ("import time", "import threading", "asyncio",
                               "QTimer", "QGuiApplication", "QScreen",
                               "while True", "sleep(", "open("):
                    with self.subTest(name=name, banned=banned):
                        self.assertNotIn(banned, text)
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    self.assertNotIsInstance(node, ast.While)

    def test_scale_constant_and_frozen_root_are_read_only_mirrors(self):
        classic = Path(__file__).resolve().parents[1] / "prototype" / "classic"
        main = (classic / "Main.qml").read_text(encoding="utf-8")
        self.assertIn("width: %d" % ROOT_WIDTH, main)
        self.assertIn("height: %d" % ROOT_HEIGHT, main)
        self.assertEqual(MAX_SCALE, 4.0)

    def test_scaling_source_claims_no_visual_or_asset_change(self):
        source = (Path(__file__).resolve().parents[1] / "canopy_features"
                  / "dock" / "display_scaling_contract.py").read_text(encoding="utf-8")
        for token in ("QML", "png", "svg", "QColor", "write("):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


class LogicalSizeConversionTests(unittest.TestCase):
    def test_physical_pixels_convert_to_logical_classic_sizes(self):
        cases = (
            ((1920, 1080, 1.0), (1920, 1080)),
            ((1920, 1080, 1.5), (1280, 720)),
            ((2560, 1440, 2.0), (1280, 720)),
            ((1920, 1080, 1.25), (1536, 864)),
            ((1366, 768, 1.25), (1093, 614)),
        )
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(logical_size_from_physical(*args), expected)

    def test_conversion_uses_round_half_up_not_bankers_rounding(self):
        self.assertEqual(logical_size_from_physical(901, 751, 2.0), (451, 376))

    def test_hostile_scale_and_geometry_fail_closed(self):
        for scale in (None, True, False, 0, -1.0, 5.0, float("nan"),
                      float("inf"), "1.5", object(), [1.5]):
            with self.subTest(scale=repr(scale)[:40]):
                with self.assertRaises(DisplayScalingError):
                    validate_scale(scale)
                with self.assertRaises(DisplayScalingError):
                    logical_size_from_physical(1920, 1080, scale)
        for width, height in ((0, 1080), (-1, 1080), (1920, 0),
                              (True, 1080), (10 ** 9, 1080), (1920, None)):
            with self.subTest(width=width, height=height):
                with self.assertRaises(DisplayScalingError):
                    logical_size_from_physical(width, height, 1.0)


class LogicalDpiBoundaryTests(unittest.TestCase):
    def test_dpi_change_returns_bounded_logical_relayout(self):
        response = DisplayChangeResponse()
        plan = response.handle(DisplayEvent(
            EVENT_DPI_CHANGED, connector="DP-1", width=1920, height=1080,
            scale=2.0))

        self.assertEqual(plan.kind, "relayout")
        self.assertEqual(plan.reason, REASON_DPI)
        self.assertEqual(plan.size, (960, 540))
        self.assertEqual(response.last_safe_size, (960, 540))
        self.assertTrue(validate_dock_bounds(*plan.size).ok)

    def test_dpi_change_never_leaks_physical_pixels_into_layout(self):
        response = DisplayChangeResponse()
        plan = response.handle(DisplayEvent(
            EVENT_DPI_CHANGED, connector="HDMI-1", width=1920, height=1080,
            scale=1.5))

        self.assertEqual(plan.size, (1200, 720))
        self.assertLessEqual(plan.size[0], ROOT_WIDTH)
        self.assertLessEqual(plan.size[1], ROOT_HEIGHT)
        self.assertNotEqual(plan.size, (1920, 1080))
        self.assertTrue(validate_dock_bounds(*plan.size, scale=1.5).ok)

    def test_below_minimum_logical_screen_holds_last_safe_layout(self):
        response = DisplayChangeResponse()
        response.handle(DisplayEvent(
            EVENT_DPI_CHANGED, width=1920, height=1080, scale=2.0))
        plan = response.handle(DisplayEvent(
            EVENT_DPI_CHANGED, width=900, height=600, scale=2.0))

        self.assertEqual(plan.kind, "hold")
        self.assertEqual(plan.reason, "below_minimum")
        self.assertEqual(plan.size, (960, 540))
        self.assertEqual(response.last_safe_size, (960, 540))

    def test_same_logical_size_is_no_op_even_when_dpi_signal_differs(self):
        response = DisplayChangeResponse()
        first = response.handle(DisplayEvent(
            EVENT_DPI_CHANGED, width=1920, height=1080, scale=2.0))
        second = response.handle(DisplayEvent(
            EVENT_DPI_CHANGED, width=2880, height=1620, scale=3.0))
        third = response.handle(DisplayEvent(
            EVENT_DPI_CHANGED, width=1920, height=1080, scale=2.0))

        self.assertEqual(first.size, (960, 540))
        self.assertEqual(second.kind, "no_op")
        self.assertEqual(second.reason, REASON_SAME_LOGICAL_SIZE)
        self.assertEqual(second.size, first.size)
        self.assertEqual(third.kind, "no_op")
        self.assertEqual(third.reason, REASON_SAME_LOGICAL_SIZE)
        self.assertEqual(len(response.history), 3)

    def test_hostile_dpi_events_never_raise_and_are_delivered_as_holds(self):
        response = DisplayChangeResponse()
        seen = []
        response.subscribe(seen.append)
        hostile = (
            None, True, 42, "1920x1080", object(), {},
            {"kind": EVENT_DPI_CHANGED, "width": 1920, "height": 1080,
             "scale": "1.5"},
            DisplayEvent(EVENT_DPI_CHANGED, width=1920, height=1080,
                         scale=float("nan")),
            DisplayEvent(EVENT_DPI_CHANGED, width=1920, height=1080, scale=0),
            DisplayEvent(EVENT_DPI_CHANGED, width=1920, height=1080, scale=4.1),
            DisplayEvent(EVENT_DPI_CHANGED, width=True, height=1080, scale=2.0),
            DisplayEvent(EVENT_DPI_CHANGED, width=1920, height=10 ** 9,
                         scale=1.0),
            DisplayEvent(EVENT_DPI_CHANGED, width=None, height=1080, scale=1.0),
        )
        for value in hostile:
            with self.subTest(value=repr(value)[:60]):
                plan = response.handle(value)
                self.assertEqual(plan.kind, "hold")
                self.assertEqual(plan.reason, "invalid_event")
                self.assertEqual(plan.size, (1200, 750))
                self.assertTrue(validate_dock_bounds(*plan.size).ok)
        self.assertEqual(len(seen), len(hostile))

    def test_dpi_subscriptions_are_push_only_and_deduplicated(self):
        response = DisplayChangeResponse()
        seen = []
        token = response.subscribe(seen.append)
        event = DisplayEvent(EVENT_DPI_CHANGED, width=1920, height=1080,
                             scale=2.0)

        first = response.handle(event)
        duplicate = response.handle(event)

        self.assertEqual(seen, [first])
        self.assertEqual(duplicate.kind, "no_op")
        self.assertTrue(response.unsubscribe(token))
        response.handle(DisplayEvent(EVENT_DPI_CHANGED, width=2560,
                                     height=1440, scale=2.0))
        self.assertEqual(len(seen), 1)

    def test_failing_dpi_subscriber_does_not_crash_dispatch(self):
        def broken(_plan):
            raise RuntimeError("synthetic subscriber failure")

        response = DisplayChangeResponse()
        seen = []
        response.subscribe(broken)
        response.subscribe(seen.append)

        plan = response.handle(DisplayEvent(
            EVENT_DPI_CHANGED, width=1920, height=1080, scale=2.0))

        self.assertEqual(seen, [plan])
        self.assertEqual(response.failed_notifications, 1)

    def test_dpi_history_stays_bounded(self):
        response = DisplayChangeResponse()
        for index in range(MAX_HISTORY + 10):
            response.handle(DisplayEvent(
                EVENT_DPI_CHANGED, width=1920 + index % 2, height=1080,
                scale=2.0))
        self.assertEqual(len(response.history), MAX_HISTORY)
        self.assertEqual(response.history[-1].sequence, MAX_HISTORY + 10)

    def test_dedicated_host_seam_matches_handle_event(self):
        direct = DisplayChangeResponse().handle(DisplayEvent(
            EVENT_DPI_CHANGED, connector="DP-2", width=1920, height=1080,
            scale=2.0))
        seam = DisplayChangeResponse().handle_logical_dpi_change(
            1920, 1080, 2.0, connector="DP-2")

        self.assertEqual(direct, seam)
        self.assertEqual(seam.reason, REASON_DPI)

    def test_api_misuse_still_raises_the_response_domain_error(self):
        response = DisplayChangeResponse()
        with self.assertRaises(DisplayChangeError):
            response.subscribe("not callable")
        with self.assertRaises(DisplayChangeError):
            response.unsubscribe("not an int")


if __name__ == "__main__":
    unittest.main()
