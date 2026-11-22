"""Offline unit tests for the bounded external-window-title label sanitizer.

No Qt, desktop session, Linux Mint guest or compiled application is exercised.
"""
from pathlib import Path
import unittest

from canopy_features.windows.window_title_sanitizer import (
    FALLBACK_LABEL, MAX_LABEL_CHARS, sanitize_window_title_label as sanitize,
)

_SOURCE = (Path(__file__).resolve().parents[1] / "canopy_features" /
           "windows" / "window_title_sanitizer.py")


class WindowTitleSanitizerTests(unittest.TestCase):
    def test_plain_titles_preserved(self):
        self.assertEqual(sanitize("Terminal - Files"), "Terminal - Files")
        self.assertEqual(sanitize("Cafe 日本語"), "Cafe 日本語")

    def test_control_characters_removed_or_separated(self):
        self.assertEqual(sanitize("A\x00B\x01\x02C"), "ABC")
        self.assertEqual(sanitize("A\n\t\rB"), "A B")
        self.assertEqual(sanitize("A\x7fB\x85C"), "ABC")
        self.assertEqual(sanitize("A\x1b[31mRed"), "A[31mRed")

    def test_bidi_overrides_and_surrogates_removed(self):
        self.assertEqual(sanitize("safe\u202eexe.moc"), "safeexe.moc")
        self.assertEqual(sanitize("a\u2066b\u2069c"), "abc")
        self.assertEqual(sanitize("A\ud800B\udfffC"), "ABC")

    def test_whitespace_collapsed_and_stripped(self):
        self.assertEqual(sanitize("  lots   of \n space  "), "lots of space")

    def test_empty_fallback_and_non_string_input(self):
        for bad in ("", "   ", "\x00\x01", None, 123, b"bytes", ["x"]):
            with self.subTest(bad=repr(bad)):
                self.assertEqual(sanitize(bad), FALLBACK_LABEL)

    def test_overlong_string_is_bounded(self):
        raw = "A" * (MAX_LABEL_CHARS * 50)
        output = sanitize(raw)
        self.assertEqual(len(output), MAX_LABEL_CHARS)
        self.assertEqual(output, "A" * MAX_LABEL_CHARS)

    def test_overlong_multibyte_with_controls_stays_bounded(self):
        raw = "\x00".join("🦊" * 200)
        output = sanitize(raw)
        self.assertEqual(len(output), MAX_LABEL_CHARS)
        self.assertEqual(output, "🦊" * MAX_LABEL_CHARS)

    def test_mixed_payload_has_no_unsafe_codepoint(self):
        raw = "A\x00B\nC\u202eD\ud800E\x7f" + "Z" * 200
        output = sanitize(raw)
        self.assertLessEqual(len(output), MAX_LABEL_CHARS)
        for char in output:
            point = ord(char)
            self.assertFalse(
                point < 0x20 or 0x7f <= point <= 0x9f
                or 0xd800 <= point <= 0xdfff
                or 0x202a <= point <= 0x202e
                or 0x2066 <= point <= 0x2069,
                msg="unsafe codepoint in output: %r" % char,
            )

    def test_sanitizing_twice_is_stable(self):
        raw = "  A\x00B\n" + "C" * 100
        once = sanitize(raw)
        self.assertEqual(sanitize(once), once)

    def test_no_polling_or_background_service_imports(self):
        code = _SOURCE.read_text(encoding="utf-8")
        for token in ("QTimer", "Thread", "subprocess", "import socket",
                      "time.sleep", "asyncio", "importlib"):
            with self.subTest(token=token):
                self.assertNotIn(token, code)


if __name__ == "__main__":
    unittest.main()
