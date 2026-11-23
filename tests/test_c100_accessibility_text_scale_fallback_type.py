"""Malformed available_sizes in resolve_fallback must fail closed, not raise.

The documented contract is a Fallback(ok=False, reason="no available font
size fits ...") result when no usable size is supplied, never a raw TypeError
from sorting/ordering caller input. See tests/test_c100_accessibility_text_scale_bounds.py
for the valid-input contract this complements.
"""
import unittest

from canopy_features.accessibility import text_scale_bounds as tsb


class FallbackMalformedSizesTests(unittest.TestCase):
    def setUp(self):
        self.compact = tsb.classify_layout(800, 750)

    def assert_no_fallback(self, sizes):
        result = tsb.resolve_fallback(
            22, 1.0, self.compact, available_sizes=sizes)
        self.assertIsInstance(result, tsb.Fallback)
        self.assertFalse(result.ok)
        self.assertIsNone(result.base_px)
        self.assertIn("no available font size", result.reason)

    def test_none_has_no_fallback(self):
        self.assert_no_fallback(None)

    def test_non_iterable_sizes_have_no_fallback(self):
        for sizes in (7, 3.5, True):
            with self.subTest(sizes=sizes):
                self.assert_no_fallback(sizes)

    def test_non_numeric_entries_have_no_fallback(self):
        for sizes in (["x"], [{"px": 12}], [["12"]], [None], [object()]):
            with self.subTest(sizes=sizes):
                self.assert_no_fallback(sizes)

    def test_huge_int_sizes_have_no_fallback(self):
        # Arbitrarily large ints cannot be ordered against a float base_px.
        for sizes in ([10 ** 400], [-(10 ** 400)], [2, 10 ** 400]):
            with self.subTest(sizes=sizes):
                result = tsb.resolve_fallback(
                    22, 1.0, self.compact, available_sizes=sizes)
                self.assertIsInstance(result, tsb.Fallback)
                self.assertFalse(result.ok)

    def test_valid_entries_survive_malformed_companions(self):
        # A bad entry must be skipped, not abort the whole fallback search.
        result = tsb.resolve_fallback(
            22, 1.0, self.compact, available_sizes=[11, "x", 19])
        self.assertTrue(result.ok)
        self.assertEqual(result.base_px, 19.0)
        self.assertIn("fell back", result.reason)

    def test_valid_controls_unchanged(self):
        default = tsb.resolve_fallback(22, 1.0, self.compact)
        self.assertTrue(default.ok)
        self.assertEqual(default.base_px, 19.0)

        roomy = tsb.classify_layout(1200, 750)
        fitted = tsb.resolve_fallback(11, 1.0, roomy)
        self.assertTrue(fitted.ok)
        self.assertEqual(fitted.base_px, 11.0)
        self.assertEqual(fitted.reason, "")

        self.assert_no_fallback(())


if __name__ == "__main__":
    unittest.main()
