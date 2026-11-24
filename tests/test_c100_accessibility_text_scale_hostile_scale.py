"""Hostile wrong-type text-scale values must fail closed in resolve_fallback.

Contract: a bounded, wrong-type ``scale`` cannot define a usable text scale, so
``resolve_fallback`` must return a ``Fallback(ok=False, base_px=None, ...)``
with a domain reason. It must never escape a raw ``TypeError`` from formatting
the scale into the no-fallback reason string.
"""
import unittest

from canopy_features.accessibility import text_scale_bounds as tsb


class HostileScaleFallbackTests(unittest.TestCase):
    def setUp(self):
        self.roomy = tsb.classify_layout(1200, 750)
        self.compact = tsb.classify_layout(800, 750)

    def test_wrong_type_scale_fails_closed_without_raw_exception(self):
        # Finite-size hostile values: no unbounded iterables or generators.
        hostile = ("1.0", None, [1], {"px": 1}, object(), 1 + 2j)
        for scale in hostile:
            for layout in (self.roomy, self.compact):
                with self.subTest(scale=type(scale).__name__, layout=layout):
                    result = tsb.resolve_fallback(12, scale, layout)
                    self.assertIsInstance(result, tsb.Fallback)
                    self.assertFalse(result.ok)
                    self.assertIsNone(result.base_px)
                    self.assertIsInstance(result.reason, str)
                    self.assertTrue(result.reason)

    def test_wrong_type_scale_never_reports_a_bounds_safe_scale(self):
        for scale in ("1.0", None, [1], {"px": 1}):
            with self.subTest(scale=type(scale).__name__):
                result = tsb.resolve_fallback(12, scale, self.roomy)
                self.assertFalse(result.ok)
                self.assertNotEqual(result.base_px, 12.0)

    def test_valid_numeric_scales_keep_documented_no_fallback_reason(self):
        # Guard the unchanged contract for legal but out-of-range scales.
        for scale in (0.01, 100.0):
            with self.subTest(scale=scale):
                result = tsb.resolve_fallback(11, scale, self.roomy)
                self.assertFalse(result.ok)
                self.assertIsNone(result.base_px)
                self.assertIn("no available font size", result.reason)

    def test_wrong_type_scale_with_non_string_reason_object_is_safe(self):
        # A hostile object whose __repr__/__str__ misbehaves must still not
        # leak an exception while the no-fallback reason is assembled.
        class BrokenRepr:
            def __repr__(self):
                raise RuntimeError("hostile repr")

            __str__ = __repr__

        result = tsb.resolve_fallback(12, BrokenRepr(), self.roomy)
        self.assertIsInstance(result, tsb.Fallback)
        self.assertFalse(result.ok)
        self.assertIsNone(result.base_px)


if __name__ == "__main__":
    unittest.main()
