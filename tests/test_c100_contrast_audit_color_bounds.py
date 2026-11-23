"""Regression: out-of-range Color channels must fail closed in contrast audit.

``Color`` documents channels/alpha in the closed range [0, 1], and
``relative_luminance``/``contrast_ratio`` document outputs in [0, 1] and
[1, 21].  Passing a Color whose channels leave [0, 1] used to be accepted and
produced out-of-range luminance/contrast.  These tests pin the fail-closed
contract at the public validators.  Pure in-memory Python: no Qt, no display,
no I/O and no visual asset is touched.
"""
import math
import unittest

from canopy_features.accessibility.contrast_audit import (
    Color,
    audit_pair,
    composite,
    contrast_ratio,
    is_transparent,
    relative_luminance,
)


class OutOfRangeColorTests(unittest.TestCase):
    def test_relative_luminance_rejects_channels_above_one(self):
        for bad in (Color(2.0, 0.0, 0.0), Color(0.0, 1.5, 0.0), Color(0.0, 0.0, 8.0)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                relative_luminance(bad)

    def test_relative_luminance_rejects_negative_channels(self):
        for bad in (Color(-0.1, 0.0, 0.0), Color(0.0, -2.0, 0.0), Color(0.0, 0.0, -0.5)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                relative_luminance(bad)

    def test_relative_luminance_rejects_non_finite_channels(self):
        for bad in (
            Color(float("nan"), 0.0, 0.0),
            Color(0.0, float("inf"), 0.0),
            Color(0.0, 0.0, float("-inf")),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                relative_luminance(bad)

    def test_contrast_ratio_rejects_out_of_range_foreground(self):
        for bad in (Color(2.0, 0.0, 0.0), Color(-1.0, 0.0, 0.0)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                contrast_ratio(bad, "#000000")

    def test_contrast_ratio_rejects_out_of_range_background(self):
        for bad in (Color(2.0, 0.0, 0.0), Color(0.0, 0.0, -1.0)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                contrast_ratio("#ffffff", bad)

    def test_composite_rejects_out_of_range_alpha_and_channels(self):
        for bad in (Color(0.0, 0.0, 0.0, 2.0), Color(0.0, 0.0, 0.0, -0.1), Color(2.0, 0.0, 0.0)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                composite(bad, "#000000")

    def test_is_transparent_rejects_out_of_range_alpha(self):
        for bad in (Color(0.0, 0.0, 0.0, 1.5), Color(0.0, 0.0, 0.0, -0.5)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                is_transparent(bad)

    def test_audit_pair_rejects_out_of_range_color(self):
        with self.assertRaises(ValueError):
            audit_pair(Color(2.0, 0.0, 0.0), "#ffffff")


class ValidColorControls(unittest.TestCase):
    """Valid Colors must be unaffected (negative control)."""

    def test_reference_values_still_hold(self):
        self.assertEqual(relative_luminance(Color(0.0, 0.0, 0.0)), 0.0)
        self.assertEqual(relative_luminance(Color(1.0, 1.0, 1.0)), 1.0)
        self.assertEqual(contrast_ratio(Color(0.0, 0.0, 0.0), Color(1.0, 1.0, 1.0)), 21.0)
        self.assertTrue(is_transparent(Color(0.0, 0.0, 0.0, 0.0)))
        self.assertFalse(is_transparent(Color(1.0, 1.0, 1.0, 1.0)))

    def test_boundary_channels_are_accepted(self):
        for color in (
            Color(0.0, 0.0, 0.0),
            Color(1.0, 1.0, 1.0),
            Color(0.0, 1.0, 0.5, 1.0),
        ):
            with self.subTest(color=color):
                self.assertTrue(0.0 <= relative_luminance(color) <= 1.0)

    def test_composite_of_valid_colors_stays_bounded(self):
        result = composite(Color(1.0, 0.0, 0.0, 0.5), Color(0.0, 0.0, 0.0, 1.0))
        self.assertTrue(math.isfinite(result.red))
        self.assertTrue(0.0 <= result.red <= 1.0)
        self.assertEqual(result.alpha, 1.0)


if __name__ == "__main__":
    unittest.main()
