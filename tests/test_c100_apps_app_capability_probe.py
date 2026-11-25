"""Offline tests for the read-only app capability probe.

No binary is executed and no real session is required. Unavailable tools and
unsupported sessions are explicit negative controls. A synthetic Cinnamon
environment is not a real Linux Mint test.
"""
import json
import unittest
from pathlib import Path

from canopy_features.apps.app_capability_probe import (
    LAUNCH_TOOLS,
    assess,
    collect,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "canopy_features" / "apps" / "app_capability_probe.py"


class AppCapabilityProbeTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "XDG_SESSION_TYPE": "x11",
            "DISPLAY": ":99",
            "XDG_CURRENT_DESKTOP": "X-Cinnamon",
            "XDG_RUNTIME_DIR": "/run/user/1000",
        }
        self.available = {name: True for name in LAUNCH_TOOLS}

    def report(self, **kwargs):
        return assess(kwargs.get("env", self.env),
                      kwargs.get("available", self.available))

    def test_capable_session_stays_probe_only(self):
        report = self.report()
        self.assertEqual(report["status"], "CAPABLE")
        self.assertEqual(report["session_type"], "x11")
        self.assertEqual(report["desktop_family"], "cinnamon")
        self.assertTrue(report["graphical_display_present"])
        self.assertTrue(report["probe_only"])
        self.assertFalse(report["app_launch_attempted"])
        for key in ("desktop_acceptance", "visual_acceptance", "qt_runtime_test"):
            self.assertEqual(report[key], "NOT_RUN")
        self.assertEqual(report["blockers"], [])

    def test_each_unavailable_tool_is_reported(self):
        for tool in LAUNCH_TOOLS:
            with self.subTest(tool=tool):
                available = dict(self.available)
                available[tool] = False
                report = self.report(available=available)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertFalse(report["launch_tools"][tool])
                self.assertIn(tool, " ".join(report["blockers"]))

    def test_all_tools_unavailable_blocks(self):
        report = self.report(available={name: False for name in LAUNCH_TOOLS})
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("no resolvable desktop app launch tool",
                      " ".join(report["blockers"]))
        self.assertEqual(report["desktop_acceptance"], "NOT_RUN")

    def test_unsupported_session_types_block(self):
        for value in ("tty", "unspecified", "", "X11-session"):
            with self.subTest(session=value):
                env = dict(self.env, XDG_SESSION_TYPE=value)
                report = self.report(env=env)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertEqual(report["session_type"], "other-or-unknown")
                self.assertFalse(report["graphical_display_present"])
        missing = dict(self.env)
        missing.pop("XDG_SESSION_TYPE")
        self.assertEqual(self.report(env=missing)["status"], "BLOCKED")

    def test_display_is_not_borrowed_across_session_types(self):
        cases = [
            {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":99",
             "XDG_CURRENT_DESKTOP": "X-Cinnamon"},
            {"XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": "wayland-0",
             "XDG_CURRENT_DESKTOP": "X-Cinnamon"},
        ]
        for env in cases:
            with self.subTest(session=env["XDG_SESSION_TYPE"]):
                report = self.report(env=env)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertFalse(report["graphical_display_present"])

    def test_wayland_session_with_own_display_is_capable(self):
        env = {
            "XDG_SESSION_TYPE": "WAYLAND",
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_CURRENT_DESKTOP": "GNOME:X-Cinnamon",
        }
        report = self.report(env=env)
        self.assertEqual(report["status"], "CAPABLE")
        self.assertEqual(report["session_type"], "wayland")
        self.assertEqual(report["desktop_family"], "cinnamon")
        self.assertFalse(report["runtime_dir_present"])

    def test_desktop_family_requires_exact_tokens(self):
        cases = {
            "X-Cinnamon": "cinnamon",
            "X-Cinnamon:GNOME": "cinnamon",
            "NotX-Cinnamon": "other-or-unknown",
            "X-Cinnamon-Fake": "other-or-unknown",
            "": "unknown",
        }
        for desktop, expected in cases.items():
            with self.subTest(desktop=desktop):
                report = self.report(env=dict(self.env, XDG_CURRENT_DESKTOP=desktop))
                self.assertEqual(report["desktop_family"], expected)

    def test_no_private_environment_values_in_report(self):
        env = dict(
            self.env,
            DISPLAY=":77-private-token",
            XDG_CURRENT_DESKTOP="GNOME:hidden-value",
            XDG_RUNTIME_DIR="/home/secret/runtime",
            HOME="/home/secret",
            CANOPY_SECRET="very secret",
        )
        serial = json.dumps(self.report(env=env))
        for token in (":77-private-token", "hidden-value", "/home/secret",
                      "CANOPY_SECRET", "very secret"):
            self.assertNotIn(token, serial)

    def test_report_keys_and_tool_names_are_bounded(self):
        available = dict(self.available)
        available["unexpected-tool"] = True
        report = self.report(available=available)
        self.assertEqual(set(report["launch_tools"]), set(LAUNCH_TOOLS))
        self.assertNotIn("unexpected-tool", json.dumps(report))
        huge = dict(self.env, DISPLAY=":" + "9" * 5000)
        self.assertEqual(self.report(env=huge)["status"], "BLOCKED")

    def test_collect_resolves_only_allowlisted_names(self):
        calls = []

        def resolver(name):
            calls.append(name)
            return "/resolved/" + name

        report = collect(environ=self.env, which=resolver)
        self.assertEqual(calls, list(LAUNCH_TOOLS))
        self.assertEqual(report["status"], "CAPABLE")
        self.assertFalse(report["app_launch_attempted"])

    def test_collect_with_unavailable_tools_and_unsupported_session(self):
        report = collect(
            environ={"XDG_SESSION_TYPE": "tty", "DISPLAY": ":99"},
            which=lambda name: None,
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["blockers"], [
            "unsupported or undeclared session type",
            "no resolvable desktop app launch tool",
        ])
        self.assertFalse(report["app_launch_attempted"])

    def test_source_has_no_process_execution(self):
        source = MODULE.read_text(encoding="utf-8")
        for token in ("subprocess", "Popen", "os.system", "QProcess"):
            self.assertNotIn(token, source)

    def test_real_host_collect_is_bounded(self):
        # Runs on this Windows host too: PATH resolution and env reads only.
        report = collect()
        self.assertIn(report["status"], ("CAPABLE", "BLOCKED"))
        self.assertEqual(set(report["launch_tools"]), set(LAUNCH_TOOLS))
        self.assertFalse(report["app_launch_attempted"])
        self.assertEqual(report["desktop_acceptance"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
