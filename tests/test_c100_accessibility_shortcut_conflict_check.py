"""Offline unit tests for shortcut collision detection (no Qt, OS or Mint claims)."""
import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.accessibility.shortcut_conflict_check import (
    Conflict, ConflictReport, KIND_COLLISION, KIND_DUPLICATE, KIND_RESERVED,
    MAX_REGISTRATIONS, RESERVED_COMBOS, ShortcutConflictError,
    SOURCE_SHELL, SOURCE_USER, detect_shortcut_conflicts, normalize_sequence,
)

MODULE = (Path(__file__).resolve().parents[1] /
          "canopy_features/accessibility/shortcut_conflict_check.py")


class NormalizeSequenceTests(unittest.TestCase):
    def test_canonicalizes_case_whitespace_and_modifier_order(self):
        self.assertEqual(normalize_sequence("Ctrl+Shift+F"), "ctrl+shift+f")
        self.assertEqual(normalize_sequence("SHIFT + ctrl + f"), "ctrl+shift+f")
        self.assertEqual(normalize_sequence("Ctrl+Alt+Delete"), "ctrl+alt+delete")
        self.assertEqual(normalize_sequence("Win+D"), "meta+d")
        self.assertEqual(normalize_sequence("F1"), "f1")
        self.assertEqual(normalize_sequence("Page Up"), "pageup")

    def test_single_modifier_token_is_a_key(self):
        self.assertEqual(normalize_sequence("Super"), "meta")
        self.assertEqual(normalize_sequence("Meta"), "meta")

    def test_rejects_malformed_sequences(self):
        for value in ("", "   ", "Ctrl+", "+Ctrl", "Ctrl++", "Ctrl+Alt",
                      "A+B", "Ctrl+Ctrl+A", "C" * 65, None, 7, True,
                      "A+B+C+D+E+F+G"):
            with self.subTest(value=value):
                with self.assertRaises(ShortcutConflictError):
                    normalize_sequence(value)


class DetectShortcutConflictsTests(unittest.TestCase):
    def test_real_classic_shell_bindings_are_clean(self):
        # Bindings mirror prototype/classic/Main.qml without parsing that file.
        shell = [("launcher.toggle", "Ctrl+Space"),
                 ("files.close", "Ctrl+W"),
                 ("files.open", "Ctrl+Shift+F")]
        report = detect_shortcut_conflicts(shell=shell)
        self.assertTrue(report.ok)
        self.assertEqual(report.conflicts, ())

    def test_reserved_combos_are_reported_for_both_sources(self):
        shell = [("shell.run", "Alt+F2"), ("shell.logout", "Ctrl+Alt+Delete")]
        user = [("user.overview", "Super")]
        report = detect_shortcut_conflicts(shell=shell, user=user)
        reserved = report.of_kind(KIND_RESERVED)
        self.assertEqual(len(reserved), 3)
        self.assertEqual({c.sequence for c in reserved},
                         {"alt+f2", "ctrl+alt+delete", "meta"})
        self.assertEqual({c.sources[0] for c in reserved}, {SOURCE_SHELL, SOURCE_USER})
        self.assertFalse(report.ok)

    def test_shell_user_collision_is_reported_with_both_owners(self):
        report = detect_shortcut_conflicts(
            shell=[("files.close", "Ctrl+W")],
            user=[("myapp.close", "ctrl+w")],
        )
        collisions = report.of_kind(KIND_COLLISION)
        self.assertEqual(len(collisions), 1)
        conflict = collisions[0]
        self.assertEqual(conflict.sequence, "ctrl+w")
        self.assertEqual(conflict.actions, ("files.close", "myapp.close"))
        self.assertEqual(conflict.sources, (SOURCE_SHELL, SOURCE_USER))
        self.assertEqual(conflict.count, 2)

    def test_normalization_equivalence_creates_collision(self):
        report = detect_shortcut_conflicts(
            shell=[("files.open", "Ctrl+Shift+F")],
            user=[("custom.open", "shift+ctrl+f")],
        )
        self.assertEqual([c.sequence for c in report.of_kind(KIND_COLLISION)],
                         ["ctrl+shift+f"])

    def test_duplicate_action_registration_is_reported(self):
        report = detect_shortcut_conflicts(
            shell=[("files.close", "Ctrl+W"), ("files.close", "Ctrl+W")])
        duplicates = report.of_kind(KIND_DUPLICATE)
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0].actions, ("files.close",))
        self.assertEqual(duplicates[0].sources, (SOURCE_SHELL,))
        self.assertEqual(duplicates[0].count, 2)
        self.assertEqual(report.of_kind(KIND_COLLISION), ())

    def test_two_actions_on_one_combo_is_collision_not_duplicate(self):
        report = detect_shortcut_conflicts(
            user=[("one", "Ctrl+E"), ("two", "Ctrl+E")])
        self.assertEqual(len(report.of_kind(KIND_COLLISION)), 1)
        self.assertEqual(report.of_kind(KIND_DUPLICATE), ())

    def test_same_action_with_two_combos_is_allowed(self):
        report = detect_shortcut_conflicts(
            shell=[("save", "Ctrl+S"), ("save", "Ctrl+Shift+S")])
        self.assertTrue(report.ok)

    def test_distinct_sequences_do_not_collide(self):
        report = detect_shortcut_conflicts(
            shell=[("files.close", "Ctrl+W")],
            user=[("custom", "Ctrl+Shift+W")],
        )
        self.assertTrue(report.ok)

    def test_custom_reserved_set_replaces_default(self):
        user = [("user.mail", "Ctrl+E"), ("user.run", "Alt+F2")]
        default = detect_shortcut_conflicts(user=user)
        self.assertEqual([c.sequence for c in default.of_kind(KIND_RESERVED)],
                         ["alt+f2"])
        report = detect_shortcut_conflicts(user=user, reserved={"ctrl+e"})
        self.assertEqual([c.sequence for c in report.of_kind(KIND_RESERVED)],
                         ["ctrl+e"])
        self.assertIn("alt+f2", RESERVED_COMBOS)

    def test_report_is_immutable_deterministic_and_filterable(self):
        shell = [("files.close", "Ctrl+W"), ("shell.run", "Alt+F2")]
        first = detect_shortcut_conflicts(shell=shell)
        second = detect_shortcut_conflicts(shell=shell)
        self.assertEqual(first.conflicts, second.conflicts)
        with self.assertRaises(TypeError):
            first.conflicts[0] = Conflict("x", "y", (), (), 1)
        with self.assertRaises(FrozenInstanceError):
            first.conflicts[0].kind = "other"
        self.assertIsInstance(first, ConflictReport)
        self.assertEqual(first.of_kind(KIND_COLLISION), ())

    def test_bounds_and_bad_inputs_fail_closed(self):
        with self.assertRaises(ShortcutConflictError):
            detect_shortcut_conflicts(shell=[("a", "Ctrl+A")] * (MAX_REGISTRATIONS + 1))
        with self.assertRaises(ShortcutConflictError):
            detect_shortcut_conflicts(shell=[("x" * 65, "Ctrl+A")])
        with self.assertRaises(ShortcutConflictError):
            detect_shortcut_conflicts(shell=["Ctrl+A"])
        with self.assertRaises(ShortcutConflictError):
            detect_shortcut_conflicts(user=[("a", "Ctrl+A")], reserved="Ctrl+A")

    def test_module_has_no_polling_threads_or_network(self):
        # Source contract: pure in-memory checker, one stdlib import only.
        tree = ast.parse(MODULE.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        self.assertEqual(imported, {"dataclasses"})


if __name__ == "__main__":
    unittest.main()
