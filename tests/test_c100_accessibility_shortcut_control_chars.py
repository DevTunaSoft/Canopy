"""Control characters in shortcut identifiers must not hide real conflicts.

Pure in-memory contract test: no Qt, compositor, OS key map, desktop service,
screen reader or Mint guest is exercised. A non-printable character embedded in
a key sequence must fail closed with the module's domain error instead of
silently changing the canonical sequence and producing a false clean report.
"""
import unittest

from canopy_features.accessibility.shortcut_conflict_check import (
    KIND_COLLISION,
    KIND_DUPLICATE,
    KIND_RESERVED,
    ShortcutConflictError,
    detect_shortcut_conflicts,
    normalize_sequence,
)


class ShortcutControlCharacterTests(unittest.TestCase):
    NON_PRINTABLE = ("\x00", "\x01", "\x1f", "\x7f", "\u200b", "\u202e", "\u00ad")

    def test_normalize_sequence_rejects_embedded_control_characters(self):
        for control in self.NON_PRINTABLE:
            for sequence in ("Ctrl+" + control + "A", "Alt+F" + control + "2",
                             control + "Meta"):
                with self.subTest(control=repr(control), sequence=repr(sequence)):
                    with self.assertRaises(ShortcutConflictError):
                        normalize_sequence(sequence)

    def test_control_character_cannot_bypass_reserved_combo(self):
        for control in self.NON_PRINTABLE:
            with self.subTest(control=repr(control)):
                with self.assertRaises(ShortcutConflictError):
                    detect_shortcut_conflicts(
                        shell=[("shell.run", "Alt+F2" + control)])
        # Control: the unmodified combo is still reported as reserved.
        report = detect_shortcut_conflicts(shell=[("shell.run", "Alt+F2")])
        self.assertEqual([c.sequence for c in report.of_kind(KIND_RESERVED)],
                         ["alt+f2"])

    def test_control_character_cannot_hide_a_collision(self):
        for control in self.NON_PRINTABLE:
            with self.subTest(control=repr(control)):
                with self.assertRaises(ShortcutConflictError):
                    detect_shortcut_conflicts(
                        shell=[("files.close", "Ctrl+W")],
                        user=[("myapp.close", "ctrl+w" + control)],
                    )
        report = detect_shortcut_conflicts(
            shell=[("files.close", "Ctrl+W")],
            user=[("myapp.close", "ctrl+w")],
        )
        self.assertEqual([c.sequence for c in report.of_kind(KIND_COLLISION)],
                         ["ctrl+w"])

    def test_canonicalization_and_duplicate_detection_unchanged(self):
        # Whitespace folding, casefold, modifier aliases and duplicate counts
        # remain available for legitimate Unicode key identifiers.
        self.assertEqual(normalize_sequence(" SHIFT + ctrl + \u00e9 "),
                         "ctrl+shift+\u00e9")
        self.assertEqual(normalize_sequence("CTRL+W"), "ctrl+w")
        report = detect_shortcut_conflicts(
            shell=[("files.close", "CTRL+W"), ("files.close", "ctrl+w")])
        self.assertEqual([c.sequence for c in report.of_kind(KIND_DUPLICATE)],
                         ["ctrl+w"])
        self.assertEqual(report.of_kind(KIND_DUPLICATE)[0].count, 2)
        self.assertEqual(report.of_kind(KIND_COLLISION), ())


if __name__ == "__main__":
    unittest.main()
