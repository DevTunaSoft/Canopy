"""Offline unit tests for user/shell shortcut collision detection.

These tests run on the host Python interpreter. They do not compile Qt, grab
OS keys, run a Linux Mint session or prove the desktop is wired up.
"""
from pathlib import Path
import re
import unittest

from canopy_features.accessibility import shortcut_conflict_check as checker
from canopy_features.accessibility.shortcut_conflict_check import (
    CONFLICT_DUPLICATE_ACTION,
    CONFLICT_DUPLICATE_SEQUENCE,
    CONFLICT_RESERVED_COMBO,
    MAX_REGISTRATIONS,
    SHELL_RESERVED_SEQUENCES,
    ShortcutRegistration,
    ShortcutRegistry,
    canonicalize_sequence,
    detect_conflicts,
)

ROOT = Path(__file__).resolve().parents[1]
MAIN_QML = ROOT / "prototype" / "classic" / "Main.qml"


def shell_registrations():
    """The three real shell bindings from the compiled Classic QML source."""
    return (
        ShortcutRegistration("launcher.toggle", "Ctrl+Space", checker.SHELL_SOURCE),
        ShortcutRegistration("files.close", "Ctrl+W", checker.SHELL_SOURCE),
        ShortcutRegistration("files.open", "Ctrl+Shift+F", checker.SHELL_SOURCE),
    )


class CanonicalSequenceTests(unittest.TestCase):
    def test_modifiers_aliases_and_order_are_normalized(self):
        cases = {
            "ctrl+space": "Ctrl+Space",
            "Control+Space": "Ctrl+Space",
            "shift+ctrl+f": "Ctrl+Shift+F",
            "meta+alt+ctrl+shift+F": "Ctrl+Alt+Shift+Meta+F",
            "alt+return": "Alt+Enter",
            "esc": "Escape",
            " CMD+S ": "Meta+S",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(canonicalize_sequence(raw), expected)

    def test_malformed_sequences_are_rejected(self):
        for raw in ("", "   ", "Ctrl+", "++", "Ctrl+A+B", "Key-A",
                    "x" * (checker.MAX_SEQUENCE_LENGTH + 1), None, 7):
            with self.subTest(raw=raw):
                with self.assertRaises((ValueError, TypeError)):
                    canonicalize_sequence(raw)


class ConflictDetectionTests(unittest.TestCase):
    def test_real_shell_registrations_have_no_conflict(self):
        self.assertEqual(detect_conflicts(shell_registrations()), ())

    def test_user_registration_on_reserved_combo_is_reported(self):
        conflicts = detect_conflicts(shell_registrations() + (
            ShortcutRegistration("user.custom", "ctrl+space"),
        ))
        reserved = [item for item in conflicts if item.kind == CONFLICT_RESERVED_COMBO]
        self.assertEqual(len(reserved), 1)
        self.assertEqual(reserved[0].sequence, "Ctrl+Space")
        self.assertEqual(reserved[0].action, "user.custom")
        self.assertEqual(reserved[0].sources, (checker.USER_SOURCE,))
        self.assertIn("user.custom", reserved[0].message)

    def test_all_three_reserved_combos_are_exercised(self):
        for combo in sorted(SHELL_RESERVED_SEQUENCES):
            with self.subTest(combo=combo):
                conflicts = detect_conflicts((
                    ShortcutRegistration("user." + combo, combo),
                ))
                self.assertEqual([item.kind for item in conflicts], [CONFLICT_RESERVED_COMBO])

    def test_duplicate_combo_between_user_and_shell_is_reported(self):
        conflicts = detect_conflicts((
            ShortcutRegistration("files.close", "Ctrl+W", checker.SHELL_SOURCE),
            ShortcutRegistration("userclose", "ctrl+w"),
        ))
        duplicate = [item for item in conflicts if item.kind == CONFLICT_DUPLICATE_SEQUENCE]
        self.assertEqual(len(duplicate), 1)
        self.assertEqual(duplicate[0].sequence, "Ctrl+W")
        self.assertEqual(duplicate[0].sources, (checker.SHELL_SOURCE, checker.USER_SOURCE))

    def test_duplicate_combo_that_is_not_reserved_is_still_reported(self):
        conflicts = detect_conflicts((
            ShortcutRegistration("shell.alt", "Alt+F6", checker.SHELL_SOURCE),
            ShortcutRegistration("user.alt", "alt+f6"),
        ))
        self.assertEqual([item.kind for item in conflicts], [CONFLICT_DUPLICATE_SEQUENCE])

    def test_duplicate_action_with_distinct_combos_is_reported(self):
        conflicts = detect_conflicts((
            ShortcutRegistration("files.close", "Ctrl+W", checker.SHELL_SOURCE),
            ShortcutRegistration("files.close", "Alt+W"),
        ))
        duplicate = [item for item in conflicts if item.kind == CONFLICT_DUPLICATE_ACTION]
        self.assertEqual(len(duplicate), 1)
        self.assertEqual(duplicate[0].action, "files.close")
        self.assertNotIn(CONFLICT_DUPLICATE_SEQUENCE, [item.kind for item in conflicts])

    def test_reserved_combo_and_duplicate_combo_both_reported(self):
        conflicts = detect_conflicts((
            ShortcutRegistration("launcher.toggle", "Ctrl+Space", checker.SHELL_SOURCE),
            ShortcutRegistration("user.toggle", "Ctrl+Space"),
        ))
        self.assertEqual(
            [item.kind for item in conflicts],
            [CONFLICT_DUPLICATE_SEQUENCE, CONFLICT_RESERVED_COMBO],
        )

    def test_disabled_registrations_are_ignored(self):
        conflicts = detect_conflicts(shell_registrations() + (
            ShortcutRegistration("user.disabled", "Ctrl+Space", enabled=False),
            ShortcutRegistration("files.close", "Alt+Z", enabled=False),
        ))
        self.assertEqual(conflicts, ())

    def test_custom_reserved_set_is_supported(self):
        conflicts = detect_conflicts(
            (ShortcutRegistration("user.custom", "F9"),),
            reserved=["f9"],
        )
        self.assertEqual([item.kind for item in conflicts], [CONFLICT_RESERVED_COMBO])

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            detect_conflicts((ShortcutRegistration("", "Ctrl+A"),))
        with self.assertRaises(ValueError):
            detect_conflicts((ShortcutRegistration("x", "Ctrl+A", source="other"),))
        with self.assertRaises(TypeError):
            detect_conflicts(("not-a-registration",))
        with self.assertRaises(ValueError):
            detect_conflicts(
                ShortcutRegistration("a" + str(index), "F2")
                for index in range(MAX_REGISTRATIONS + 1)
            )

    def test_results_are_deterministic(self):
        registrations = (
            ShortcutRegistration("files.close", "Ctrl+W", checker.SHELL_SOURCE),
            ShortcutRegistration("duplicate", "Ctrl+W"),
            ShortcutRegistration("files.close", "Alt+W"),
        )
        first = detect_conflicts(registrations)
        second = detect_conflicts(reversed(registrations))
        self.assertEqual(first, second)
        self.assertIsInstance(first, tuple)


class ShortcutRegistryTests(unittest.TestCase):
    def test_register_reports_conflict_then_unregister_clears_it(self):
        registry = ShortcutRegistry()
        for registration in shell_registrations():
            self.assertEqual(registry.register(registration), ())
        conflicts = registry.register(ShortcutRegistration("user.custom", "Control+Space"))
        self.assertEqual(
            {item.kind for item in conflicts},
            {CONFLICT_RESERVED_COMBO, CONFLICT_DUPLICATE_SEQUENCE},
        )
        self.assertTrue(registry.unregister("user.custom", checker.USER_SOURCE))
        self.assertEqual(registry.conflicts(), ())
        self.assertEqual(len(registry.registrations), 3)

    def test_registry_rejects_overflow(self):
        registry = ShortcutRegistry()
        for index in range(MAX_REGISTRATIONS):
            registry.register(ShortcutRegistration("action" + str(index), "F2"))
        with self.assertRaises(ValueError):
            registry.register(ShortcutRegistration("overflow", "F3"))


class ClassicSourceGuardTests(unittest.TestCase):
    def test_reserved_combos_match_compiled_qml_and_source_has_no_collision(self):
        qml = MAIN_QML.read_text(encoding="utf-8")
        sequences = re.findall(r'sequence:\s*"([^"]+)"', qml)
        self.assertTrue(sequences)
        canonical = {canonicalize_sequence(sequence) for sequence in sequences}
        self.assertEqual(canonical, set(SHELL_RESERVED_SEQUENCES))
        registrations = tuple(
            ShortcutRegistration("qml." + item, item, checker.SHELL_SOURCE)
            for item in sequences
        )
        self.assertEqual(detect_conflicts(registrations), ())


if __name__ == "__main__":
    unittest.main()
