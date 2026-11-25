"""Offline display-backend tests: no Qt, no Mint guest, no real display."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
import unittest
from unittest.mock import patch

from canopy_features.mint.display_backends import SOFTWARE_BACKEND, collect, main, plan

X11 = {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}
WAYLAND = {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0"}


class DisplayBackendTests(unittest.TestCase):
    def test_x11_session_with_display_selects_xcb(self):
        report = plan(X11)
        self.assertEqual(report["backend"], "xcb")
        self.assertFalse(report["software_render"])
        self.assertTrue(report["display_present"])
        self.assertEqual(report["env_overlay"], {"QT_QPA_PLATFORM": "xcb"})
        self.assertEqual(report["reasons"], [])

    def test_wayland_session_with_socket_selects_wayland(self):
        report = plan(WAYLAND)
        self.assertEqual(report["backend"], "wayland")
        self.assertFalse(report["software_render"])
        self.assertEqual(report["qt_qpa_platform"], "wayland")
        self.assertEqual(report["reasons"], [])

    def test_no_display_uses_software_render_fallback(self):
        report = plan({})
        self.assertEqual(report["backend"], SOFTWARE_BACKEND)
        self.assertEqual(report["backend"], "offscreen")
        self.assertTrue(report["software_render"])
        self.assertFalse(report["display_present"])
        self.assertEqual(report["env_overlay"], {"QT_QPA_PLATFORM": "offscreen"})
        self.assertIn("session type missing or unsupported", " ".join(report["reasons"]))

    def test_x11_session_without_display_falls_back(self):
        report = plan({"XDG_SESSION_TYPE": "x11"})
        self.assertTrue(report["software_render"])
        self.assertEqual(report["session_type"], "x11")
        self.assertIn("no display is present", " ".join(report["reasons"]))

    def test_display_is_not_borrowed_across_session_types(self):
        cases = [
            {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"},
            {"XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": "wayland-0"},
            {"XDG_SESSION_TYPE": "x11", "DISPLAY": "", "WAYLAND_DISPLAY": "wayland-0"},
        ]
        for env in cases:
            with self.subTest(env=env):
                report = plan(env)
                self.assertEqual(report["backend"], "offscreen")
                self.assertFalse(report["display_present"])
                self.assertTrue(report["software_render"])

    def test_unknown_session_never_uses_a_display(self):
        for session in ("", "tty", "unspecified"):
            with self.subTest(session=session):
                report = plan({
                    "XDG_SESSION_TYPE": session,
                    "DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0",
                })
                self.assertEqual(report["session_type"], "unknown")
                self.assertTrue(report["software_render"])
                self.assertFalse(report["display_present"])

    def test_unsafe_qt_platform_override_is_not_passed_through(self):
        native = plan(dict(X11, QT_QPA_PLATFORM="linuxfb"))
        self.assertEqual(native["backend"], "xcb")
        fallback = plan({"QT_QPA_PLATFORM": "linuxfb"})
        self.assertEqual(fallback["backend"], "offscreen")

    def test_report_leaks_no_raw_display_or_environment_secrets(self):
        report = plan(dict(X11, WAYLAND_DISPLAY="wayland-secret",
                           CANOPY_SECRET="very secret"))
        serialized = json.dumps(report)
        for token in (":0", "wayland-secret", "CANOPY_SECRET", "very secret"):
            self.assertNotIn(token, serialized)

    def test_report_always_stays_probe_only(self):
        for env in ({}, X11, WAYLAND):
            with self.subTest(env=env):
                report = plan(env)
                self.assertEqual(report["schema_version"], 1)
                self.assertTrue(report["probe_only"])
                self.assertEqual(report["runtime_functional_test"], "NOT_RUN")
                self.assertEqual(report["mint_guest_acceptance"], "NOT_RUN")
                self.assertEqual(report["visual_acceptance"], "NOT_RUN")

    def test_report_size_does_not_grow_with_environment(self):
        report = plan(dict(X11, LARGE="x" * 100000))
        self.assertLess(len(json.dumps(report)), 1200)

    def test_collect_uses_current_environment_only(self):
        with patch.dict(os.environ, X11, clear=True):
            self.assertEqual(collect()["backend"], "xcb")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(collect()["backend"], "offscreen")

    def test_windows_host_without_graphical_variables_falls_back(self):
        # A Windows CI host has no XDG_SESSION_TYPE/DISPLAY/WAYLAND_DISPLAY.
        host = {key: value for key, value in os.environ.items()
                if key not in ("XDG_SESSION_TYPE", "DISPLAY", "WAYLAND_DISPLAY")}
        self.assertEqual(plan(host)["backend"], "offscreen")
        # The real host probe stays bounded and makes no Mint or Qt claim.
        live = collect()
        self.assertIn(live["backend"], ("xcb", "wayland", "offscreen"))
        self.assertEqual(live["mint_guest_acceptance"], "NOT_RUN")

    def test_cli_offline_text_and_json(self):
        out = StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(out):
            return_code = main([])
        self.assertEqual(return_code, 0)
        self.assertIn("DISPLAY_BACKEND_OFFSCREEN", out.getvalue())
        self.assertIn("SOFTWARE_FALLBACK: session type missing or unsupported",
                      out.getvalue())
        out = StringIO()
        with patch.dict(os.environ, X11, clear=True), redirect_stdout(out):
            return_code = main(["--json"])
        self.assertEqual(return_code, 0)
        self.assertEqual(json.loads(out.getvalue())["backend"], "xcb")


if __name__ == "__main__":
    unittest.main()
