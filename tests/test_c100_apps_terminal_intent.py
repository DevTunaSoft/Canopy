"""Offline unit tests for the inert terminal-intent preparation component.

No Qt, GIO, display or network is used. These tests cover successful
preparation, the missing-terminal case, injection and elevation attempts, and
drift against the compiled launcher's terminal allowlist.
"""

import re
import unittest
from pathlib import Path

from canopy_features.apps.terminal_intent import (
    TERMINAL_DESKTOP_IDS,
    TerminalIntent,
    prepare_terminal_intent,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "canopy_features" / "apps" / "terminal_intent.py"
LAUNCHER_CPP = ROOT / "prototype" / "classic" / "SystemAppLauncher.cpp"


class TerminalIntentTests(unittest.TestCase):
    def test_valid_request_prepared_as_explicit_intent(self):
        result = prepare_terminal_intent("Terminal", installed=("mate-terminal.desktop",))
        self.assertEqual(result.status, "PREPARED")
        self.assertTrue(result.success)
        self.assertIsInstance(result.intent, TerminalIntent)
        intent = result.intent
        self.assertEqual(intent.desktop_id, "mate-terminal.desktop")
        self.assertEqual(intent.candidates, TERMINAL_DESKTOP_IDS)
        self.assertEqual(intent.launch_surface, "gio-desktop-app-info")
        self.assertFalse(intent.elevated)
        self.assertEqual(intent.argv, ())

    def test_first_available_candidate_wins_by_priority(self):
        installed = ("xfce4-terminal.desktop", "org.gnome.Terminal.desktop")
        result = prepare_terminal_intent("Terminal", installed=installed)
        self.assertEqual(result.intent.desktop_id, "org.gnome.Terminal.desktop")

    def test_exact_desktop_id_request_accepted(self):
        result = prepare_terminal_intent(
            "xfce4-terminal.desktop", installed=("xfce4-terminal.desktop",)
        )
        self.assertEqual(result.status, "PREPARED")
        self.assertEqual(result.intent.desktop_id, "xfce4-terminal.desktop")

    def test_unknown_availability_uses_preferred_candidate(self):
        result = prepare_terminal_intent("Terminal")
        self.assertEqual(result.status, "PREPARED")
        self.assertEqual(result.intent.desktop_id, TERMINAL_DESKTOP_IDS[0])

    def test_missing_terminal_is_unavailable_not_fabricated(self):
        cases = ((), ("firefox.desktop",), ("gnome-terminal",), ("TERMINAL.desktop",))
        for installed in cases:
            with self.subTest(installed=installed):
                result = prepare_terminal_intent("Terminal", installed=installed)
                self.assertEqual(result.status, "UNAVAILABLE")
                self.assertFalse(result.success)
                self.assertIsNone(result.intent)
                self.assertIn("no terminal", result.reason)

    def test_injection_attempts_are_rejected(self):
        attempts = (
            "Terminal; rm -rf /",
            "Terminal && sudo",
            "Terminal | tee /tmp/pwned",
            "Terminal > /tmp/pwned",
            "$(id)",
            "`id`",
            "Terminal\necho hi",
            "Terminal\techo hi",
            "gnome-terminal.desktop\x00evil",
            "sudo gnome-terminal",
            "pkexec gnome-terminal",
            "doas xfce4-terminal",
            "gksu mate-terminal",
            "su -c evil",
            "sh -c 'evil'",
            "bash -c evil",
            "cmd /c evil",
            "/usr/bin/gnome-terminal",
            "../gnome-terminal.desktop",
            "http://evil.example/terminal",
            "file:///etc/passwd",
            "gnome-terminal.desktop -- bash",
            "gnome-terminal.desktop -e evil",
            "Exec=evil",
            "%COMSPEC%",
            "gnome-terminal.desktop &",
        )
        for raw in attempts:
            with self.subTest(request=raw):
                result = prepare_terminal_intent(raw, installed=TERMINAL_DESKTOP_IDS)
                self.assertEqual(result.status, "REJECTED")
                self.assertFalse(result.success)
                self.assertIsNone(result.intent)
                self.assertTrue(result.reason)

    def test_elevated_flag_never_prepares_a_privileged_intent(self):
        result = prepare_terminal_intent(
            "Terminal", installed=TERMINAL_DESKTOP_IDS, elevated=True
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertIsNone(result.intent)
        self.assertIn("elevated", result.reason)

    def test_prepared_mapping_stays_argument_free_and_non_elevated(self):
        result = prepare_terminal_intent("Terminal", installed=("gnome-terminal.desktop",))
        data = result.intent.to_mapping()
        self.assertEqual(data["desktop_id"], "gnome-terminal.desktop")
        self.assertFalse(data["elevated"])
        self.assertEqual(data["argv"], [])
        self.assertEqual(data["candidates"], list(TERMINAL_DESKTOP_IDS))

    def test_non_string_request_rejected(self):
        for value in (None, 123, ["Terminal"], {"app": "Terminal"}):
            with self.subTest(value=value):
                result = prepare_terminal_intent(value)
                self.assertEqual(result.status, "REJECTED")
                self.assertIsNone(result.intent)

    def test_preparation_is_pure_and_bounded(self):
        expected = prepare_terminal_intent("Terminal", installed=("xfce4-terminal.desktop",))
        for _ in range(100):
            self.assertEqual(
                prepare_terminal_intent("Terminal", installed=("xfce4-terminal.desktop",)),
                expected,
            )

    def test_allowlist_matches_compiled_launcher(self):
        cpp = LAUNCHER_CPP.read_text(encoding="utf-8")
        marker = '{QStringLiteral("Terminal"), {'
        start = cpp.index(marker) + len(marker)
        end = cpp.index("}}", start)
        found = tuple(re.findall(r'QStringLiteral\("([^"]+\.desktop)"\)', cpp[start:end]))
        self.assertEqual(found, TERMINAL_DESKTOP_IDS)

    def test_module_is_inert_with_no_execution_or_privilege_code(self):
        source = MODULE.read_text(encoding="utf-8")
        forbidden = (
            "import subprocess",
            "os.system",
            "import socket",
            "Popen",
            "check_call",
            "import pty",
            "os.exec",
        )
        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, source)


if __name__ == "__main__":
    unittest.main()
