"""Offline tests for Classic text-scale bounds and font fallback policy."""
import math
import unittest

from canopy_features.accessibility import text_scale_bounds as tsb


class LayoutClassificationTests(unittest.TestCase):
    def test_compact_threshold_matches_main_cpp(self):
        self.assertTrue(tsb.classify_layout(800, 500).compact)
        self.assertFalse(tsb.classify_layout(801, 500).compact)

    def test_condensed_threshold_matches_preview_window(self):
        self.assertTrue(tsb.classify_layout(1200, 389).condensed)
        self.assertFalse(tsb.classify_layout(1200, 390).condensed)

    def test_hidpi_threshold(self):
        self.assertTrue(tsb.classify_layout(1200, 750, 1.5).hidpi)
        self.assertFalse(tsb.classify_layout(1200, 750, 1.49).hidpi)

    def test_layout_is_tight_when_compact_or_condensed(self):
        self.assertTrue(tsb.classify_layout(800, 750).tight_fit)
        self.assertTrue(tsb.classify_layout(1200, 389).tight_fit)
        self.assertFalse(tsb.classify_layout(1200, 750).tight_fit)

    def test_invalid_viewport_rejected(self):
        with self.assertRaises(ValueError):
            tsb.classify_layout(0, 750)
        with self.assertRaises(ValueError):
            tsb.classify_layout(1200, float("nan"))


class EffectivePixelsTests(unittest.TestCase):
    def test_logical_and_physical_pixels(self):
        logical, physical = tsb.effective_pixels(13, 1.5, 2.0)
        self.assertAlmostEqual(logical, 19.5)
        self.assertAlmostEqual(physical, 39.0)

    def test_hidpi_keeps_logical_size(self):
        logical, physical = tsb.effective_pixels(13, 1.0, 1.5)
        self.assertAlmostEqual(logical, 13.0)
        self.assertAlmostEqual(physical, 19.5)


class ScaleValidationTests(unittest.TestCase):
    def test_accepts_documented_range(self):
        for scale in (0.5, 1.0, 2.0, 3.0):
            self.assertEqual(tsb.validate_scale(scale), [])

    def test_rejects_out_of_range(self):
        for scale in (0.0, -1.0, 3.01, 100.0):
            self.assertTrue(tsb.validate_scale(scale))

    def test_rejects_non_finite_and_wrong_types(self):
        for scale in (float("inf"), float("nan"), "1", True):
            self.assertTrue(tsb.validate_scale(scale))


class TextBoundsTests(unittest.TestCase):
    def test_all_shipped_sizes_fit_at_native_scale(self):
        layout = tsb.classify_layout(1200, 750)
        for size in tsb.FONT_SIZES_PX:
            with self.subTest(size=size):
                self.assertTrue(tsb.check_text(size, 1.0, layout).ok)

    def test_extreme_low_scale_is_unreadable(self):
        layout = tsb.classify_layout(1200, 750)
        report = tsb.check_text(10, 0.01, layout)
        self.assertFalse(report.ok)
        self.assertTrue(any("readable minimum" in r for r in report.reasons))

    def test_extreme_high_scale_overflows(self):
        layout = tsb.classify_layout(1200, 750)
        report = tsb.check_text(22, 10.0, layout)
        self.assertFalse(report.ok)
        self.assertTrue(any("fitting cap" in r for r in report.reasons))

    def test_compact_layout_uses_19px_cap(self):
        roomy = tsb.classify_layout(1200, 750)
        compact = tsb.classify_layout(800, 750)
        self.assertTrue(tsb.check_text(22, 1.0, roomy).ok)
        report = tsb.check_text(22, 1.0, compact)
        self.assertFalse(report.ok)
        self.assertTrue(any("19" in r for r in report.reasons))

    def test_hidpi_reports_physical_size_without_changing_fit(self):
        layout = tsb.classify_layout(1200, 750, 2.0)
        report = tsb.check_text(11, 1.0, layout, 2.0)
        self.assertTrue(report.ok)
        self.assertTrue(layout.hidpi)
        self.assertAlmostEqual(report.logical_px, 11.0)
        self.assertAlmostEqual(report.physical_px, 22.0)

    def test_invalid_inputs_do_not_crash(self):
        layout = tsb.classify_layout(1200, 750)
        for base, scale, dpr in ((0, 1.0, 1.0), (12, 1.0, float("inf")),
                                 (12, 1.0, 5.0), (12, 1.0, 1.0)):
            with self.subTest(base=base, scale=scale, dpr=dpr):
                report = tsb.check_text(base, scale, layout, dpr)
                self.assertIsInstance(report.ok, bool)
        bad_layout = tsb.check_text(12, 1.0, "not a layout")
        self.assertFalse(bad_layout.ok)
        self.assertTrue(not math.isnan(bad_layout.logical_px))


class FontFallbackTests(unittest.TestCase):
    def test_closest_fit_is_chosen(self):
        compact = tsb.classify_layout(800, 750)
        fallback = tsb.resolve_fallback(22, 1.0, compact)
        self.assertTrue(fallback.ok)
        self.assertEqual(fallback.base_px, 19.0)
        self.assertIn("fell back", fallback.reason)

    def test_no_fallback_when_size_already_fits(self):
        roomy = tsb.classify_layout(1200, 750)
        fallback = tsb.resolve_fallback(11, 1.0, roomy)
        self.assertTrue(fallback.ok)
        self.assertEqual(fallback.base_px, 11.0)
        self.assertEqual(fallback.reason, "")

    def test_low_scale_falls_back_to_larger_size(self):
        roomy = tsb.classify_layout(1200, 750)
        fallback = tsb.resolve_fallback(10, 0.5, roomy)
        self.assertTrue(fallback.ok)
        self.assertEqual(fallback.base_px, 22.0)
        self.assertTrue(tsb.check_text(22, 0.5, roomy).ok)

    def test_extreme_scales_have_no_fitting_font(self):
        roomy = tsb.classify_layout(1200, 750)
        for scale in (0.01, 100.0):
            with self.subTest(scale=scale):
                fallback = tsb.resolve_fallback(11, scale, roomy)
                self.assertFalse(fallback.ok)
                self.assertIsNone(fallback.base_px)
                self.assertIn("no available font size", fallback.reason)

    def test_empty_font_set_has_no_fallback(self):
        compact = tsb.classify_layout(800, 750)
        fallback = tsb.resolve_fallback(22, 1.0, compact, available_sizes=())
        self.assertFalse(fallback.ok)

    def test_family_fallback(self):
        available = ("Inter", "DejaVu Sans")
        self.assertEqual(tsb.resolve_font_family("Inter", available), "Inter")
        self.assertEqual(tsb.resolve_font_family("Missing", available),
                         tsb.GENERIC_FAMILY)


if __name__ == "__main__":
    unittest.main()
