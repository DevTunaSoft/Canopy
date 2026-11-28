"""Offline unit tests for the Classic dock display-geometry contract.

No compiled Qt, Linux Mint session or live display is used. All tests run on
the Windows host with the standard library only.
"""

import math
import re
import unittest
from pathlib import Path

from canopy_features.dock.display_geometry_contract import (
    BAR_HEIGHT, DOCK_HEIGHT, DOCK_PADDING, DOCK_SPACING, HORIZONTAL_CLAMP,
    TILE_WIDTH, Rect, dock_logical_rect, round_half_up, to_physical,
    validate_dock_bounds,
)

ROOT = Path(__file__).resolve().parents[1]


class FrozenConstantTests(unittest.TestCase):
    def test_mirrors_match_frozen_classic_ui_source(self):
        theme = (ROOT / "prototype" / "classic" / "Theme.qml").read_text(
            encoding="utf-8")
        tile = (ROOT / "prototype" / "classic" / "DockTile.qml").read_text(
            encoding="utf-8")
        main = (ROOT / "prototype" / "classic" / "Main.qml").read_text(
            encoding="utf-8")

        def theme_int(name):
            match = re.search(r"readonly property int " + name + r":\s*(\d+)",
                              theme)
            self.assertIsNotNone(match, name)
            return int(match.group(1))

        # Theme.qml is pinned to the owner-approved 32/96/14/7 geometry.
        self.assertEqual((theme_int("barHeight"), theme_int("dockSize"),
                          theme_int("dockPadding"), theme_int("dockSpacing")),
                         (32, 96, 14, 7))
        # The Python contract module still carries the pre-remediation
        # legacy mirror. Syncing it is explicitly deferred and is NOT
        # claimed by this test; the geometry assertions below pin that
        # legacy mirror, not the approved UI source.
        self.assertEqual((BAR_HEIGHT, DOCK_HEIGHT, DOCK_PADDING, DOCK_SPACING),
                         (32, 88, 12, 7))
        self.assertIn("width: 58", tile)
        self.assertIn("anchors.bottomMargin: 22", main)
        self.assertIn("root.width - 32", main)


class RoundingTests(unittest.TestCase):
    def test_round_half_up_matches_qt_qround(self):
        cases = [(0.5, 1), (1.5, 2), (2.5, 3), (805.5, 806), (2.49, 2),
                 (-0.5, -1), (-1.5, -2)]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(round_half_up(value), expected)


class ReferenceLayoutTests(unittest.TestCase):
    def test_reference_1200x750_layout_is_valid(self):
        report = validate_dock_bounds(1200, 750, 1.0)
        self.assertTrue(report.ok, report.violations)
        expected = Rect(331.5, 640.0, 537.0, 88.0)
        self.assertEqual(report.logical, expected)
        self.assertEqual(report.physical, Rect(332, 640, 537, 88))
        self.assertEqual(dock_logical_rect(1200, 750), expected)

    def test_tile_count_changes_row_width(self):
        six = dock_logical_rect(1200, 750, tile_count=6)
        eight = dock_logical_rect(1200, 750, tile_count=8)
        self.assertLess(six.width, eight.width)
        self.assertEqual(six.width, 6 * TILE_WIDTH + 5 * DOCK_SPACING
                         + 2 * DOCK_PADDING)


class ScalingTests(unittest.TestCase):
    def test_logical_bounds_are_scale_invariant(self):
        baseline = validate_dock_bounds(1200, 750, 1.0)
        for scale in (1.0, 1.25, 1.5, 2.0, 3.0):
            with self.subTest(scale=scale):
                report = validate_dock_bounds(1200, 750, scale)
                self.assertTrue(report.ok, report.violations)
                self.assertEqual(report.logical, baseline.logical)

    def test_hidpi_integer_scale_reports_physical_extents(self):
        report = validate_dock_bounds(1200, 750, 2.0)
        self.assertTrue(report.ok, report.violations)
        self.assertEqual(report.screen_physical, Rect(0, 0, 2400, 1500))
        self.assertEqual(report.physical, Rect(663, 1280, 1074, 176))

    def test_fractional_150_percent_trap_has_no_false_violation(self):
        report = validate_dock_bounds(1200, 750, 1.5)
        self.assertTrue(report.ok, report.violations)
        # 1200x750 logical is 1800x1125 physical. Physical must never be
        # compared against logical window geometry.
        self.assertEqual(report.screen_logical, Rect(0, 0, 1200, 750))
        self.assertEqual(report.screen_physical, Rect(0, 0, 1800, 1125))
        self.assertEqual(report.physical.width, 806)  # 537 * 1.5 = 805.5

    def test_fractional_125_percent_rounding(self):
        report = validate_dock_bounds(1200, 750, 1.25)
        self.assertTrue(report.ok, report.violations)
        self.assertEqual(report.screen_physical, Rect(0, 0, 1500, 938))

    def test_to_physical_scales_every_field(self):
        self.assertEqual(to_physical(Rect(10, 20, 30, 40), 3.0),
                         Rect(30, 60, 90, 120))

    def test_invalid_scale_is_reported(self):
        for scale in (0, -1, math.nan, math.inf, -math.inf):
            with self.subTest(scale=scale):
                report = validate_dock_bounds(1200, 750, scale)
                self.assertFalse(report.ok)
                self.assertIn("invalid_scale", report.violations)
                self.assertEqual(report.physical, to_physical(report.logical, 1.0))


class TinyScreenTests(unittest.TestCase):
    def test_tiny_screen_clamps_dock_width_and_still_fits(self):
        report = validate_dock_bounds(320, 240, 3.0)
        self.assertTrue(report.ok, report.violations)
        self.assertEqual(report.logical, Rect(16.0, 130.0, 288.0, 88.0))

    def test_short_screen_dock_overlaps_top_bar(self):
        report = validate_dock_bounds(320, 120, 1.0)
        self.assertFalse(report.ok)
        self.assertIn("dock_overlaps_top_bar", report.violations)

    def test_screen_shorter_than_dock_is_above_screen(self):
        report = validate_dock_bounds(200, 80, 1.0)
        self.assertFalse(report.ok)
        self.assertIn("dock_above_screen", report.violations)

    def test_zero_screen_is_invalid(self):
        report = validate_dock_bounds(0, 0, 1.0)
        self.assertFalse(report.ok)
        self.assertIn("invalid_screen", report.violations)
        self.assertIn("dock_nonpositive", report.violations)


class OffscreenAndCenteringTests(unittest.TestCase):
    def test_offscreen_custom_rect_is_rejected(self):
        report = validate_dock_bounds(
            1200, 750, 1.0, dock_rect=Rect(-5, 640, 537, 88))
        self.assertFalse(report.ok)
        self.assertIn("dock_left_out_of_bounds", report.violations)

    def test_centering_tolerance_matches_compiled_check(self):
        base = dock_logical_rect(1200, 750)
        shifted_2 = Rect(base.x - 2.0, base.y, base.width, base.height)
        shifted_3 = Rect(base.x - 3.0, base.y, base.width, base.height)
        self.assertTrue(validate_dock_bounds(
            1200, 750, 1.0, dock_rect=shifted_2).ok)
        self.assertIn("dock_not_centered", validate_dock_bounds(
            1200, 750, 1.0, dock_rect=shifted_3).violations)


if __name__ == "__main__":
    unittest.main()
