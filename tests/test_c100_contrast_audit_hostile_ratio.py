"""Regression: public ratio validators must fail closed on hostile ratios.

``wcag_level`` and ``meets_wcag`` document a finite real ``ratio``. Wrong-type
or non-finite values used to leak raw ``TypeError``/``InvalidOperation`` or,
for infinity, return ``AAA``/``True`` -- a false contrast-pass claim. These
tests pin the fail-closed contract without changing any colour, artwork,
threshold or approved visual asset. Pure in-memory Python: no Qt, no display,
no I/O and no network.
"""
import unittest
from decimal import Decimal

from canopy_features.accessibility.contrast_audit import (
    AA_LARGE,
    AA_NORMAL,
    AAA_LARGE,
    AAA_NORMAL,
    audit_pair,
    meets_wcag,
    wcag_level,
)


class HostileRatioTests(unittest.TestCase):
    def test_wrong_type_ratio_raises_domain_error(self):
        # Bounded, finite wrong-type values: a string that looks like a passing
        # ratio, containers, complex numbers, bool, Decimal (not a documented
        # float) and Decimal NaN used to escape as raw built-in exceptions.
        for value in (
            "4.6",
            None,
            [4.6],
            {"ratio": 4.6},
            (4.6,),
            4.6j,
            True,
            Decimal("7"),
            Decimal("NaN"),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    wcag_level(value)  # type: ignore[arg-type]
                with self.subTest(value=value, api="meets_wcag"):
                    with self.assertRaises(ValueError):
                        meets_wcag(value)  # type: ignore[arg-type]

    def test_non_finite_ratio_never_claims_pass(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    wcag_level(value)
                with self.subTest(value=value, level="AAA"):
                    with self.assertRaises(ValueError):
                        meets_wcag(value, level="AAA")

    def test_oversized_integer_ratio_raises_domain_error(self):
        # float() of a huge int overflows; that OverflowError must not escape.
        with self.assertRaises(ValueError):
            wcag_level(10 ** 400)


class ValidRatioControls(unittest.TestCase):
    """Documented real ratios keep their exact thresholds (negative control)."""

    def test_real_ratio_thresholds_unchanged(self):
        for value, expected in (
            (0, "FAIL"),
            (AA_NORMAL, "AA"),
            (AAA_NORMAL, "AAA"),
        ):
            with self.subTest(value=value):
                self.assertEqual(wcag_level(value), expected)
        self.assertTrue(meets_wcag(AA_NORMAL, level="AA"))
        self.assertFalse(meets_wcag(AA_NORMAL, level="AAA"))
        self.assertFalse(meets_wcag(AA_NORMAL - 0.01, level="AA"))
        self.assertEqual(wcag_level(AA_LARGE, large_text=True), "AA")
        self.assertEqual(wcag_level(AAA_LARGE, large_text=True), "AAA")

    def test_audit_pair_flags_stay_consistent(self):
        record = audit_pair("#767676", "#ffffff")
        self.assertEqual(record["aa"], record["level"] in ("AA", "AAA"))
        self.assertEqual(record["aaa"], record["level"] == "AAA")


if __name__ == "__main__":
    unittest.main()
