"""Offline unit tests for high-contrast token validation.

No real Qt, desktop, screen reader, or Linux Mint behavior is claimed here.
"""
from pathlib import Path
import unittest

from canopy_features.accessibility.high_contrast_options import (
    ColorToken, HighContrastError, HighContrastOption, MAX_TOKENS,
    MIN_CONTRAST_RATIO, contrast_ratio, parse_hex_color,
    relative_luminance, validate_option, validate_token,
)


def _token(label="Text", foreground="#000000", background="#FFFFFF"):
    return ColorToken(label=label, foreground=foreground, background=background)


class ParseHexColorTests(unittest.TestCase):
    def test_valid_short_and_long_forms(self):
        self.assertEqual(parse_hex_color("#000"), (0, 0, 0))
        self.assertEqual(parse_hex_color("#fff"), (255, 255, 255))
        self.assertEqual(parse_hex_color("#537da4"), (0x53, 0x7d, 0xa4))
        self.assertEqual(parse_hex_color("#ABCDEF"), (0xAB, 0xCD, 0xEF))

    def test_invalid_hex_colors_rejected(self):
        invalid = (
            "", "fff", "#", "#ff", "#12345", "#1234567", "#12345678",
            "#gggggg", "#12x456", "#FFFF%F", "#00000 ", "  #000000",
            None, 0, 1234, b"#000000", ["#000000"],
        )
        for value in invalid:
            with self.subTest(value=repr(value)):
                with self.assertRaises(HighContrastError):
                    parse_hex_color(value)


class ContrastMathTests(unittest.TestCase):
    def test_known_wcag_ratios(self):
        self.assertEqual(contrast_ratio("#000000", "#FFFFFF"), 21.0)
        self.assertEqual(contrast_ratio("#FFFFFF", "#000000"), 21.0)
        self.assertEqual(contrast_ratio("#000000", "#000000"), 1.0)
        mid_gray = contrast_ratio("#808080", "#FFFFFF")
        self.assertGreater(mid_gray, 1.0)
        self.assertLess(mid_gray, MIN_CONTRAST_RATIO)

    def test_relative_luminance_bounds_and_ordering(self):
        self.assertEqual(relative_luminance((0, 0, 0)), 0.0)
        self.assertAlmostEqual(relative_luminance((255, 255, 255)), 1.0)
        self.assertLess(relative_luminance((0, 0, 0)),
                        relative_luminance((0, 0, 255)))
        self.assertLess(relative_luminance((0, 0, 255)),
                        relative_luminance((255, 255, 255)))


class TokenValidationTests(unittest.TestCase):
    def test_valid_high_contrast_token_passes(self):
        result = validate_token(_token())
        self.assertTrue(result.passed)
        self.assertEqual(result.ratio, 21.0)
        self.assertEqual(result.problems, ())

    def test_missing_label_is_reported(self):
        for label in ("", "   ", "\t\n", None, 7):
            with self.subTest(label=repr(label)):
                result = validate_token(_token(label=label))
                self.assertFalse(result.passed)
                self.assertIn("missing label", result.problems)
                self.assertEqual(result.label, "")
                self.assertEqual(result.ratio, 21.0)

    def test_invalid_hex_colors_are_reported_not_raised(self):
        result = validate_token(_token(foreground="#zzzzzz", background="bad"))
        self.assertFalse(result.passed)
        self.assertIn("invalid foreground hex", result.problems)
        self.assertIn("invalid background hex", result.problems)
        self.assertIsNone(result.ratio)

    def test_low_contrast_token_fails(self):
        result = validate_token(_token(foreground="#808080"))
        self.assertFalse(result.passed)
        self.assertIn("contrast below minimum", result.problems)
        self.assertLess(result.ratio, MIN_CONTRAST_RATIO)

    def test_overlong_label_flagged_and_bounded(self):
        label = "X" * (MAX_TOKENS * 100)
        result = validate_token(_token(label=label))
        self.assertIn("label too long", result.problems)
        self.assertEqual(len(result.label), 80)

    def test_wrong_types_raise(self):
        for bad in (None, "text", {"label": "x"}):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(HighContrastError):
                    validate_token(bad)
        for bad_ratio in (True, 0, 22, "7", float("nan")):
            with self.subTest(min_ratio=repr(bad_ratio)):
                with self.assertRaises(HighContrastError):
                    validate_token(_token(), min_ratio=bad_ratio)


class OptionValidationTests(unittest.TestCase):
    def test_valid_option_reports_all_pass(self):
        option = HighContrastOption(
            name="Black on white",
            tokens=(
                _token("Window text", "#000000", "#FFFFFF"),
                _token("Link text", "#000000", "#FFFFFF"),
            ),
        )
        report = validate_option(option)
        self.assertTrue(report.passed)
        self.assertEqual(report.name, "Black on white")
        self.assertEqual(len(report.results), 2)
        self.assertEqual(report.problems, ())

    def test_missing_labels_aggregate_and_fail_option(self):
        option = HighContrastOption(
            name="Broken labels",
            tokens=(_token(""), _token("   "), _token("Good")),
        )
        report = validate_option(option)
        self.assertFalse(report.passed)
        self.assertEqual([r.passed for r in report.results],
                         [False, False, True])
        missing = [p for p in report.problems if p.endswith("missing label")]
        self.assertEqual(len(missing), 2)

    def test_invalid_hex_aggregates_and_fails_option(self):
        option = HighContrastOption(
            name="Broken colors",
            tokens=(_token("Bad fg", "#12345678", "#FFFFFF"),
                    _token("Bad bg", "#000000", "white"),
                    _token("Good")),
        )
        report = validate_option(option)
        self.assertFalse(report.passed)
        self.assertIn("Bad fg: invalid foreground hex", report.problems)
        self.assertIn("Bad bg: invalid background hex", report.problems)

    def test_missing_option_name_and_empty_option(self):
        empty = validate_option(HighContrastOption(name="  ", tokens=()))
        self.assertFalse(empty.passed)
        self.assertIn("missing option name", empty.problems)
        self.assertIn("no tokens", empty.problems)

    def test_token_count_is_hard_bounded(self):
        too_many = HighContrastOption(
            name="Too big",
            tokens=tuple(_token("T%d" % i) for i in range(MAX_TOKENS + 1)),
        )
        with self.assertRaisesRegex(HighContrastError, "exceeds"):
            validate_option(too_many)
        with self.assertRaises(HighContrastError):
            validate_option("not an option")


class NoServicesOrFileWritesTests(unittest.TestCase):
    def test_module_is_pure_offline_and_bounded(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/accessibility/high_contrast_options.py").read_text()
        for forbidden in ("QTimer", "import socket", "subprocess",
                          "time.sleep", "threading", "import os", "open(",
                          ".write(", "while True", "asyncio", "requests"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
