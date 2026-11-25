"""Offline tests for screen-independent keyboard action intents.

Pure Python only: no Qt, desktop session or Linux Mint runtime is involved.
"""
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
import unittest

from canopy_features.accessibility.keyboard_action_map import (
    DEFAULT_ACTIONS, MAX_ACTIONS, DuplicateShortcutError, InaccessibleActionError,
    KeyboardActionError, KeyboardActionIntent, KeyboardActionMap,
    normalize_shortcut,
)


class NormalizationTests(unittest.TestCase):
    def test_canonical_form_ignores_case_and_modifier_order(self):
        self.assertEqual(normalize_shortcut("ctrl+shift+f"), "Ctrl+Shift+F")
        self.assertEqual(normalize_shortcut(" Shift + CTRL + f "), "Ctrl+Shift+F")
        self.assertEqual(normalize_shortcut("Ctrl+Space"), "Ctrl+Space")
        self.assertEqual(normalize_shortcut("Escape"), "Escape")
        self.assertEqual(normalize_shortcut("f1"), "F1")

    def test_malformed_sequences_fail_closed(self):
        bad = ("", "Ctrl++W", "Ctrl+", "Ctrl+Ctrl+W", "Ctrl+Shift+Alt+Meta+W",
               "Ctrl+Unknown", "Ctrl", "W+Ctrl", None, 42, b"Ctrl+W")
        for sequence in bad:
            with self.subTest(sequence=sequence):
                with self.assertRaises(KeyboardActionError):
                    normalize_shortcut(sequence)


class IntentTests(unittest.TestCase):
    def test_intent_is_frozen_screen_independent_and_normalized(self):
        intent = KeyboardActionIntent("files.close", "Close Files", "ctrl+w")
        self.assertEqual(intent.shortcut, "Ctrl+W")
        self.assertEqual({field.name for field in fields(intent)},
                         {"action_id", "label", "shortcut", "available"})
        with self.assertRaises(FrozenInstanceError):
            intent.label = "Changed"

    def test_intents_without_accessible_name_are_rejected(self):
        for label in ("", "   ", "Close\nFiles", "x" * 200, "\ud800"):
            with self.subTest(label=repr(label)):
                with self.assertRaises(InaccessibleActionError):
                    KeyboardActionIntent("files.bad", label)

    def test_invalid_ids_availability_and_shortcuts_are_rejected(self):
        for action_id in ("Files.Close", "9files", "files..close", "x" * 65, 7):
            with self.subTest(action_id=action_id):
                with self.assertRaises(KeyboardActionError):
                    KeyboardActionIntent(action_id, "Valid name")
        with self.assertRaises(KeyboardActionError):
            KeyboardActionIntent("files.open", "Valid name", available="yes")
        with self.assertRaises(KeyboardActionError):
            KeyboardActionIntent("files.open", "Valid name", "Ctrl+Bogus")


class CatalogTests(unittest.TestCase):
    def test_default_catalog_mirrors_existing_actions_without_conflicts(self):
        actions = KeyboardActionMap()
        self.assertEqual(len(actions), len(DEFAULT_ACTIONS))
        self.assertEqual(len(actions.accessible_shortcuts()), 4)
        self.assertEqual(actions.resolve("ctrl+space").action_id, "launcher.toggle")
        self.assertEqual(actions.resolve("Escape").action_id, "launcher.dismiss")
        self.assertEqual(actions.resolve("ctrl+shift+f").action_id, "files.open")
        self.assertEqual(actions.resolve("Ctrl+W").action_id, "files.close")
        self.assertIsNone(actions.resolve("Ctrl+Q"))
        self.assertTrue(all(access.label.strip() for access in actions))

    def test_duplicate_shortcuts_are_detected_across_spelling_variants(self):
        intents = [
            KeyboardActionIntent("files.close", "Close Files", "Ctrl+W"),
            KeyboardActionIntent("window.close", "Close window", "ctrl + w"),
        ]
        with self.assertRaises(DuplicateShortcutError) as caught:
            KeyboardActionMap(intents)
        self.assertEqual(caught.exception.shortcut, "Ctrl+W")
        self.assertEqual(caught.exception.first_id, "files.close")
        self.assertEqual(caught.exception.second_id, "window.close")

    def test_duplicate_id_is_rejected(self):
        intent = KeyboardActionIntent("files.find", "Find in Files")
        with self.assertRaisesRegex(KeyboardActionError, "duplicate"):
            KeyboardActionMap([intent, intent])

    def test_inaccessible_action_is_cataloged_but_never_resolved(self):
        actions = KeyboardActionMap([
            KeyboardActionIntent("files.close", "Close Files", "Ctrl+W"),
            KeyboardActionIntent("files.location", "Current Files location",
                                 "ctrl+w", available=False),
        ])
        hidden = actions.get("files.location")
        self.assertIsNotNone(hidden)
        self.assertFalse(actions.is_accessible("files.location"))
        self.assertNotIn(hidden, actions.accessible_actions())
        self.assertNotIn("files.location", actions.accessible_shortcuts().values())
        self.assertEqual(actions.resolve("Ctrl+W").action_id, "files.close")
        self.assertFalse(actions.is_accessible("files.unknown"))

    def test_default_disabled_menu_action_stays_inaccessible(self):
        actions = KeyboardActionMap()
        self.assertIsNotNone(actions.get("files.location"))
        self.assertFalse(actions.is_accessible("files.location"))
        self.assertNotIn("files.location", actions.accessible_shortcuts().values())

    def test_rebuild_is_explicit_invalidation_and_detects_new_conflicts(self):
        actions = KeyboardActionMap([
            KeyboardActionIntent("files.close", "Close Files", "Ctrl+W"),
            KeyboardActionIntent("files.location", "Current Files location",
                                 "ctrl+l", available=False),
        ])
        enabled = actions.with_availability("files.location", True)
        self.assertFalse(actions.is_accessible("files.location"))
        self.assertTrue(enabled.is_accessible("files.location"))
        self.assertEqual(enabled.resolve("Ctrl+L").action_id, "files.location")
        self.assertIsNone(actions.resolve("Ctrl+L"))

        conflict = KeyboardActionMap([
            KeyboardActionIntent("files.close", "Close Files", "Ctrl+W"),
            KeyboardActionIntent("files.duplicate", "Duplicate close",
                                 "ctrl+w", available=False),
        ])
        with self.assertRaises(DuplicateShortcutError):
            conflict.with_availability("files.duplicate", True)

    def test_catalog_bounds_and_immutable_views(self):
        too_many = [
            KeyboardActionIntent("files.action_%02d" % index, "Action %d" % index)
            for index in range(MAX_ACTIONS + 1)
        ]
        with self.assertRaises(KeyboardActionError):
            KeyboardActionMap(too_many)
        actions = KeyboardActionMap()
        with self.assertRaises(TypeError):
            actions.accessible_shortcuts()["Ctrl+Q"] = "bad"
        with self.assertRaises(FrozenInstanceError):
            actions.get("files.close").shortcut = "Ctrl+Q"
        with self.assertRaises(KeyboardActionError):
            actions.get(42)
        with self.assertRaises(KeyboardActionError):
            actions.resolve("Ctrl+Q+ nonsense +")
        with self.assertRaises(KeyboardActionError):
            KeyboardActionMap("not-a-list")
        with self.assertRaises(KeyboardActionError):
            KeyboardActionMap([object()])

    def test_module_is_pure_offline_without_polling_or_platform_branches(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/accessibility/keyboard_action_map.py").read_text()
        for forbidden in ("QTimer", "time.sleep", "socket", "subprocess",
                          "Thread(", "asyncio", "while True", "import os",
                          "import sys", "platform.system"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, code)
        # Same host-independent result on repeated calls; no OS state consulted.
        expected = tuple(normalize_shortcut(s) for s in
                         ("ctrl+w", "Ctrl+W", "CTRL+W"))
        self.assertEqual(expected, ("Ctrl+W", "Ctrl+W", "Ctrl+W"))


if __name__ == "__main__":
    unittest.main()
