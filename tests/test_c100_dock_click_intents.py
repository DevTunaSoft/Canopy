"""Offline unit tests for the dock activation -> safe intent mapper.

No Qt, GIO, desktop session, network or Mint guest is required. These tests
exercise the pure Python trust boundary on whatever host runs them (Windows
here). They are not evidence of a working compiled Qt desktop.
"""

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_features.dock.click_intents import (
    APPROVED_DOCK_NAMES,
    ClickIntent,
    DockClickMapper,
    IntentKind,
)


class UntrustedIdTests(unittest.TestCase):
    def setUp(self):
        self.mapper = DockClickMapper(installed=APPROVED_DOCK_NAMES)

    def test_non_string_activations_rejected_without_state_change(self):
        hostile = (None, 123, True, b"Files", ["Files"], {"name": "Files"},
                   3.14, object())
        for value in hostile:
            with self.subTest(value=repr(value)):
                before = self.mapper.state_size
                intent = self.mapper.resolve(value)
                self.assertEqual(intent.kind, IntentKind.REJECT)
                self.assertEqual(intent.reason, "untrusted-id")
                self.assertEqual(intent.name, "")
                self.assertFalse(intent.actionable)
                self.assertEqual(self.mapper.state_size, before)

    def test_unknown_variant_and_injection_ids_rejected(self):
        hostile = (
            "", " ", "files", "FILES", " Files", "Files ", "Files\n",
            "Files;rm -rf /", "/usr/bin/files", "file:///etc/passwd",
            "org.gnome.Nautilus.desktop", "Files\x00", "Fïles", "Ｆｉｌｅｓ",
            "x" * 10000, "../Files", "Browser\r\nExec=sh",
        )
        for value in hostile:
            with self.subTest(value=repr(value)):
                intent = self.mapper.resolve(value)
                self.assertEqual(intent.kind, IntentKind.REJECT)
                self.assertEqual(intent.reason, "untrusted-id")
                self.assertEqual(intent.name, "")

    def test_frozen_intent_cannot_be_mutated(self):
        intent = self.mapper.resolve("Files")
        self.assertEqual(intent.kind, IntentKind.LAUNCH)
        with self.assertRaises(FrozenInstanceError):
            intent.kind = IntentKind.FOCUS
        with self.assertRaises(FrozenInstanceError):
            intent.reason = "tampered"


class MissingTargetTests(unittest.TestCase):
    def test_approved_but_not_installed_is_rejected(self):
        mapper = DockClickMapper(installed=("Files",))
        for name in ("Browser", "Mail", "Terminal"):
            with self.subTest(name=name):
                intent = mapper.resolve(name)
                self.assertEqual(intent.kind, IntentKind.REJECT)
                self.assertEqual(intent.reason, "missing-target")
                self.assertEqual(intent.name, name)
                self.assertFalse(intent.actionable)

    def test_launcher_disabled_never_emits_launch(self):
        mapper = DockClickMapper(installed=APPROVED_DOCK_NAMES,
                                 launcher_enabled=False)
        for name in APPROVED_DOCK_NAMES:
            with self.subTest(name=name):
                intent = mapper.resolve(name)
                self.assertNotEqual(intent.kind, IntentKind.LAUNCH)
                self.assertEqual(intent.reason, "missing-target")

    def test_installed_and_not_running_launches(self):
        mapper = DockClickMapper(installed=("Files", "Terminal"))
        first = mapper.resolve("Terminal")
        self.assertEqual(first.kind, IntentKind.LAUNCH)
        self.assertEqual(first.name, "Terminal")
        self.assertEqual(first.reason, "installed")
        self.assertTrue(first.actionable)

    def test_unknown_entries_in_snapshots_are_ignored(self):
        mapper = DockClickMapper(installed=("Files", "org.gnome.Nautilus.desktop",
                                            "/bin/sh", 42, None))
        self.assertEqual(mapper.state_size, 1)
        self.assertEqual(mapper.resolve("Files").kind, IntentKind.LAUNCH)
        self.assertEqual(mapper.resolve("org.gnome.Nautilus.desktop").reason,
                         "untrusted-id")


class RepeatedClickTests(unittest.TestCase):
    def test_second_click_while_launch_pending_is_ignored(self):
        mapper = DockClickMapper(installed=("Files",))
        self.assertEqual(mapper.resolve("Files").kind, IntentKind.LAUNCH)
        second = mapper.resolve("Files")
        self.assertEqual(second.kind, IntentKind.IGNORE)
        self.assertEqual(second.reason, "launch-pending")
        self.assertFalse(second.actionable)

    def test_focus_after_host_reports_running(self):
        mapper = DockClickMapper(installed=("Files",))
        self.assertEqual(mapper.resolve("Files").kind, IntentKind.LAUNCH)
        mapper.observe(running=("Files",))
        intent = mapper.resolve("Files")
        self.assertEqual(intent.kind, IntentKind.FOCUS)
        self.assertEqual(intent.reason, "running")
        self.assertTrue(intent.actionable)

    def test_already_running_click_focuses_without_launch(self):
        mapper = DockClickMapper(installed=("Files",), running=("Files",))
        intent = mapper.resolve("Files")
        self.assertEqual(intent.kind, IntentKind.FOCUS)
        self.assertEqual(intent.reason, "running")

    def test_many_repeated_clicks_keep_state_bounded(self):
        mapper = DockClickMapper(installed=APPROVED_DOCK_NAMES)
        for name in APPROVED_DOCK_NAMES:
            for _ in range(500):
                mapper.resolve(name)
        self.assertLessEqual(mapper.state_size, len(APPROVED_DOCK_NAMES))
        self.assertEqual(mapper.state_size, len(APPROVED_DOCK_NAMES))
        # Rejections still produce no pending launch for an unknown name.
        for _ in range(500):
            self.assertEqual(mapper.resolve("nope").reason, "untrusted-id")
        self.assertLessEqual(mapper.state_size, len(APPROVED_DOCK_NAMES))

    def test_uninstalled_pending_launch_is_cleared(self):
        mapper = DockClickMapper(installed=("Files",))
        self.assertEqual(mapper.resolve("Files").kind, IntentKind.LAUNCH)
        mapper.observe(installed=())
        # Pending cleared; still a valid name but no target now.
        self.assertEqual(mapper.resolve("Files").reason, "missing-target")


class PlatformNeutralTests(unittest.TestCase):
    def test_no_polling_threads_network_or_os_calls(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features" / "dock" / "click_intents.py").read_text(encoding="utf-8")
        for banned in ("QTimer", "subprocess", "socket", "Thread(",
                       "import threading", "asyncio", "time.sleep", "import os",
                       "g_app_info_launch", "QProcess"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, code)

    def test_allowlist_matches_host_launcher_labels(self):
        self.assertEqual(APPROVED_DOCK_NAMES, frozenset((
            "Browser", "Mail", "Files", "Calendar",
            "Photos", "Music", "Terminal", "Settings",
        )))


if __name__ == "__main__":
    unittest.main()
