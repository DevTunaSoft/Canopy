"""Offline tests for read-only X11/Wayland runtime capability detection."""

import json
import unittest
from unittest.mock import patch

from canopy_features.windows.session_backend_detect import (
    BACKEND_HEADLESS,
    BACKEND_WAYLAND,
    BACKEND_X11,
    detect,
    valid_x11_display,
    valid_wayland_display,
)


class SessionBackendDetectTests(unittest.TestCase):
    def test_x11_session_uses_valid_display(self):
        report = detect({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"})
        self.assertEqual(report["backend"], BACKEND_X11)
        self.assertTrue(report["x11_hint"])
        self.assertFalse(report["wayland_hint"])
        self.assertEqual(report["x11_display"], ":0")
        self.assertFalse(report["headless"])
        self.assertTrue(report["probe_only"])

    def test_wayland_session_ignores_xwayland_display(self):
        report = detect({
            "XDG_SESSION_TYPE": "wayland",
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": ":0",
        })
        self.assertEqual(report["backend"], BACKEND_WAYLAND)
        self.assertTrue(report["wayland_hint"])
        self.assertEqual(report["wayland_display"], "wayland-0")

    def test_session_type_case_and_whitespace_normalized(self):
        report = detect({
            "XDG_SESSION_TYPE": "  Wayland  ",
            "WAYLAND_DISPLAY": "wayland-1",
        })
        self.assertEqual(report["session_type"], "wayland")
        self.assertEqual(report["backend"], BACKEND_WAYLAND)

    def test_headless_tty_has_no_graphical_backend(self):
        report = detect({"XDG_SESSION_TYPE": "tty"})
        self.assertEqual(report["backend"], BACKEND_HEADLESS)
        self.assertTrue(report["headless"])
        self.assertFalse(report["x11_hint"])
        self.assertFalse(report["wayland_hint"])
        self.assertIsNone(report["x11_display"])
        self.assertIsNone(report["wayland_display"])

    def test_missing_environment_defaults_to_headless(self):
        report = detect({})
        self.assertEqual(report["backend"], BACKEND_HEADLESS)
        self.assertEqual(report["session_type"], "unknown")
        self.assertEqual(report["invalid_display_vars"], [])
        self.assertTrue(any("no graphical display" in note for note in report["notes"]))

    def test_invalid_displays_never_produce_a_graphical_backend(self):
        bad_values = ("", "   ", "not-a-display", ":abc", "::", ":999999",
                      "localhost:", "space here", ":0;echo hacked", ":0\n:1")
        for value in bad_values:
            with self.subTest(x11=value):
                report = detect({"XDG_SESSION_TYPE": "x11", "DISPLAY": value})
                self.assertEqual(report["backend"], BACKEND_HEADLESS)
                self.assertFalse(report["x11_hint"])
                self.assertIn("DISPLAY", report["invalid_display_vars"])
        for value in bad_values + ("../etc/passwd", "/run/../etc/passwd", "wayland 0"):
            with self.subTest(wayland=value):
                report = detect({
                    "XDG_SESSION_TYPE": "wayland",
                    "WAYLAND_DISPLAY": value,
                })
                self.assertEqual(report["backend"], BACKEND_HEADLESS)
                self.assertFalse(report["wayland_hint"])
                self.assertIn("WAYLAND_DISPLAY", report["invalid_display_vars"])

    def test_valid_display_syntax(self):
        for value in (":0", ":0.0", "localhost:10.0", "unix/:0", "[::1]:0"):
            with self.subTest(x11=value):
                self.assertTrue(valid_x11_display(value))
        for value in ("wayland-0", "wayland-1", "/run/user/1000/wayland-0"):
            with self.subTest(wayland=value):
                self.assertTrue(valid_wayland_display(value))
        self.assertFalse(valid_x11_display(None))
        self.assertFalse(valid_wayland_display(None))

    def test_non_string_and_oversized_values_rejected(self):
        report = detect({
            "XDG_SESSION_TYPE": "x11",
            "DISPLAY": 1234,
            "WAYLAND_DISPLAY": "w" * 500,
        })
        self.assertFalse(report["x11_hint"])
        self.assertFalse(report["wayland_hint"])
        self.assertEqual(report["backend"], BACKEND_HEADLESS)
        self.assertEqual(report["invalid_display_vars"],
                         ["DISPLAY", "WAYLAND_DISPLAY"])

    def test_declared_session_requires_matching_display(self):
        report = detect({
            "XDG_SESSION_TYPE": "x11",
            "WAYLAND_DISPLAY": "wayland-0",
        })
        self.assertEqual(report["backend"], BACKEND_HEADLESS)
        self.assertTrue(report["wayland_hint"])
        self.assertTrue(any("lacks a valid DISPLAY" in n for n in report["notes"]))

    def test_backend_inferred_without_session_type(self):
        wayland = detect({"WAYLAND_DISPLAY": "wayland-0"})
        self.assertEqual(wayland["backend"], BACKEND_WAYLAND)
        self.assertTrue(any("inferred" in n for n in wayland["notes"]))
        x11 = detect({"DISPLAY": ":0"})
        self.assertEqual(x11["backend"], BACKEND_X11)
        both = detect({"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"})
        self.assertEqual(both["backend"], BACKEND_WAYLAND)
        self.assertTrue(any("both display variables" in n for n in both["notes"]))

    def test_default_reads_os_environ(self):
        with patch.dict("os.environ", {
            "XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0",
        }, clear=True):
            report = detect()
        self.assertEqual(report["backend"], BACKEND_WAYLAND)

    def test_report_is_json_serializable_and_bounded(self):
        report = detect({
            "XDG_SESSION_TYPE": "other" * 40,
            "DISPLAY": ":0",
        })
        self.assertEqual(len(report["session_type"]), 32)
        self.assertLessEqual(len(report["notes"]), 8)
        self.assertEqual(json.loads(json.dumps(report)), report)


if __name__ == "__main__":
    unittest.main()
