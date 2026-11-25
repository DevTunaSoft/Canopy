"""Offline unit tests for the WCAG contrast audit component.

No Qt, display, network or Mint guest is used. Real compiled-Qt and Linux Mint
acceptance remain untested here.
"""
from pathlib import Path
import unittest

from canopy_features.accessibility.contrast_audit import (
    AA_LARGE,
    AA_NORMAL,
    AAA_LARGE,
    AAA_NORMAL,
    Color,
    audit_pair,
    composite,
    contrast_ratio,
    find_color_references,
    is_transparent,
    meets_wcag,
    parse_color,
    relative_luminance,
    wcag_level,
)

ROOT = Path(__file__).resolve().parents[1]


class ColorParsingTests(unittest.TestCase):
    def test_hex_forms_expand_and_put_alpha_first(self):
        self.assertEqual(parse_color("#fff"), Color(1.0, 1.0, 1.0, 1.0))
        self.assertEqual(parse_color("#000"), Color(0.0, 0.0, 0.0, 1.0))
        self.assertEqual(parse_color("#ffffff"), Color(1.0, 1.0, 1.0, 1.0))
        self.assertEqual(parse_color("#123456"), Color(18 / 255, 52 / 255, 86 / 255, 1.0))
        # Qt #ARGB and #AARRGGBB place alpha before the RGB channels.
        self.assertEqual(parse_color("#800f"), Color(0.0, 0.0, 1.0, 136 / 255))
        self.assertEqual(parse_color("#690d1a2b"), Color(13 / 255, 26 / 255, 43 / 255, 105 / 255))

    def test_functional_and_named_colors(self):
        self.assertEqual(parse_color("rgb(255, 0, 0)"), Color(1.0, 0.0, 0.0, 1.0))
        self.assertEqual(parse_color("rgba(0, 0, 0, 128)"), Color(0.0, 0.0, 0.0, 128 / 255))
        self.assertEqual(parse_color("  #FFFFFF  "), Color(1.0, 1.0, 1.0, 1.0))
        self.assertEqual(parse_color("Transparent"), Color(0.0, 0.0, 0.0, 0.0))
        self.assertFalse(is_transparent("#ffffffff"))

    def test_malformed_strings_are_rejected(self):
        bad_values = [
            "",
            "   ",
            "#",
            "#12",
            "#12345",
            "#1234567",
            "#123456789",
            "#gggggg",
            "#12gg34",
            "rgb(1,2)",
            "rgba(1,2,3)",
            "rgba(1,2,3,4,5)",
            "rgb(256,0,0)",
            "rgb(-1,0,0)",
            "rgba(0,0,0,300)",
            "rgb(a,b,c)",
            "rgb(1.5,2,3)",
            "not-a-color",
            "rebeccapurple",
        ]
        for value in bad_values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_color(value)

    def test_non_string_input_is_rejected(self):
        for value in (None, 123, b"#ffffff", ["#ffffff"]):
            with self.subTest(value=value), self.assertRaises(TypeError):
                parse_color(value)


class LuminanceAndRatioTests(unittest.TestCase):
    def test_reference_ratios(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0)
        self.assertAlmostEqual(contrast_ratio("#ffffff", "#ffffff"), 1.0)
        self.assertAlmostEqual(contrast_ratio("#000000", "#000000"), 1.0)
        self.assertAlmostEqual(contrast_ratio("#777777", "#ffffff"), 4.478089453577214, places=9)
        self.assertAlmostEqual(contrast_ratio("#767676", "#ffffff"), 4.542224959605253, places=9)
        self.assertAlmostEqual(contrast_ratio("#ff0000", "#ffffff"), 3.9984767707539985, places=9)
        self.assertAlmostEqual(contrast_ratio("#ffffff", "#0000ff"), 8.592471358428805, places=9)

    def test_ratio_is_symmetric_and_bounded(self):
        forward = contrast_ratio("#dceaf5", "#2b3e52")
        self.assertAlmostEqual(forward, contrast_ratio("#2b3e52", "#dceaf5"))
        self.assertGreaterEqual(forward, 1.0)
        self.assertLessEqual(forward, 21.0)

    def test_luminance_bounds_and_ordering(self):
        self.assertEqual(relative_luminance("#000000"), 0.0)
        self.assertEqual(relative_luminance("#ffffff"), 1.0)
        self.assertLess(relative_luminance("#777777"), relative_luminance("#bbbbbb"))


class TransparentColorTests(unittest.TestCase):
    def test_fully_transparent_detection(self):
        for value in ("transparent", "#00ffffff", "#00000000", "rgba(0,0,0,0)"):
            with self.subTest(value=value):
                self.assertTrue(is_transparent(value))

    def test_transparent_color_over_background_matches_background(self):
        self.assertEqual(composite("transparent", "#1a2b3c"), parse_color("#1a2b3c"))
        self.assertAlmostEqual(contrast_ratio("transparent", "#ffffff"), 1.0)
        self.assertAlmostEqual(contrast_ratio("#00000000", "#000000"), 1.0)

    def test_translucent_foreground_is_composited_before_scoring(self):
        blended = composite("#80ffffff", "#000000")
        self.assertEqual(blended.alpha, 1.0)
        self.assertAlmostEqual(blended.red, 0.5019607843137255)
        self.assertAlmostEqual(contrast_ratio("#80ffffff", "#000000"),
                               contrast_ratio("#808080", "#000000"), places=9)

    def test_translucent_input_without_backdrop_is_rejected(self):
        with self.assertRaises(ValueError):
            relative_luminance("#80ffffff")
        with self.assertRaises(ValueError):
            contrast_ratio("#ffffff", "#80ffffff")


class WcagRatingTests(unittest.TestCase):
    def test_normal_and_large_text_thresholds(self):
        for ratio, large, expected in [
            (AAA_NORMAL, False, "AAA"),
            (AA_NORMAL, False, "AA"),
            (AA_NORMAL - 0.01, False, "FAIL"),
            (AAA_LARGE, True, "AAA"),
            (AA_LARGE, True, "AA"),
            (AA_LARGE - 0.01, True, "FAIL"),
        ]:
            with self.subTest(ratio=ratio, large=large):
                self.assertEqual(wcag_level(ratio, large_text=large), expected)

    def test_meets_wcag_and_invalid_arguments(self):
        self.assertTrue(meets_wcag(4.6, level="AA"))
        self.assertFalse(meets_wcag(4.6, level="AAA"))
        self.assertTrue(meets_wcag(3.1, level="AA", large_text=True))
        with self.assertRaises(ValueError):
            meets_wcag(5.0, level="A")
        with self.assertRaises(ValueError):
            wcag_level(-1.0)

    def test_audit_pair_report(self):
        record = audit_pair("#f7f5eb", "#2b3e52")
        self.assertEqual(set(record), {"foreground", "background", "ratio", "level", "aa", "aaa"})
        self.assertGreater(record["ratio"], 1.0)
        self.assertIn(record["level"], ("AA", "AAA", "FAIL"))
        self.assertEqual(record["aa"], record["level"] in ("AA", "AAA"))


class AuthoredSourceScanTests(unittest.TestCase):
    def test_extracts_ordered_distinct_references_and_skips_malformed(self):
        snippet = (
            'color: "#f7f5eb"; border.color: "#aac9f2ff"; '
            'background: transparent; bad: #12345; good: rgb(0, 0, 0); '
            'repeat: "#f7f5eb";'
        )
        self.assertEqual(
            find_color_references(snippet),
            ["#f7f5eb", "#aac9f2ff", "transparent", "rgb(0, 0, 0)"],
        )

    def test_scan_of_real_authored_qml_yields_parseable_references(self):
        source = (ROOT / "prototype" / "classic" / "Main.qml").read_text(encoding="utf-8")
        references = find_color_references(source)
        self.assertGreaterEqual(len(references), 5)
        for reference in references:
            with self.subTest(reference=reference):
                parse_color(reference)

    def test_scan_rejects_non_string(self):
        with self.assertRaises(TypeError):
            find_color_references(None)


if __name__ == "__main__":
    unittest.main()
