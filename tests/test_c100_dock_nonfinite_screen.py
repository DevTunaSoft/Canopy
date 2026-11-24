"""Regression tests: non-finite screen dimensions must not crash the contract.

``validate_dock_bounds`` documents "no exception is raised for invalid inputs".
A NaN or infinite screen dimension reached ``round_half_up`` and raised
ValueError/OverflowError instead of returning a GeometryReport carrying an
``invalid_screen`` violation. These tests pin the fail-closed contract.
"""

import math
import unittest

from canopy_features.dock.display_geometry_contract import (
    GeometryReport, Rect, validate_dock_bounds)

NONFINITE = (math.nan, math.inf, -math.inf)


def _rect_fields(rect):
    return (rect.x, rect.y, rect.width, rect.height)


class NonFiniteScreenTests(unittest.TestCase):
    def _check_no_crash(self, width, height, **kwargs):
        report = validate_dock_bounds(width, height, 1.0, **kwargs)
        self.assertIsInstance(report, GeometryReport)
        self.assertFalse(report.ok)
        self.assertIn("invalid_screen", report.violations)
        return report

    def test_nonfinite_width_and_height_return_report(self):
        for bad in NONFINITE:
            with self.subTest(axis="width", value=bad):
                self._check_no_crash(bad, 750.0)
            with self.subTest(axis="height", value=bad):
                self._check_no_crash(1200.0, bad)

    def test_nonfinite_screen_physical_extents_are_finite(self):
        for bad in NONFINITE:
            for width, height in ((bad, 750.0), (1200.0, bad)):
                with self.subTest(width=width, height=height):
                    report = self._check_no_crash(width, height)
                    for rect in (report.logical, report.physical,
                                 report.screen_logical, report.screen_physical):
                        for value in _rect_fields(rect):
                            self.assertTrue(math.isfinite(value),
                                            "non-finite report field: %r" % (value,))

    def test_nonfinite_screen_with_dock_rect_override(self):
        for bad in NONFINITE:
            with self.subTest(value=bad):
                report = self._check_no_crash(
                    bad, 750.0, dock_rect=Rect(331.5, 640.0, 537.0, 88.0))
                for value in _rect_fields(report.physical):
                    self.assertTrue(math.isfinite(value))

    def test_valid_zero_and_invalid_scale_contract_unchanged(self):
        # Controls: the fix must not perturb the documented valid/invalid cases.
        self.assertTrue(validate_dock_bounds(1200, 750, 1.0).ok)
        zero = validate_dock_bounds(0, 0, 1.0)
        self.assertFalse(zero.ok)
        self.assertIn("invalid_screen", zero.violations)
        self.assertIn("dock_nonpositive", zero.violations)
        bad_scale = validate_dock_bounds(1200, 750, math.nan)
        self.assertIn("invalid_scale", bad_scale.violations)


if __name__ == "__main__":
    unittest.main()
