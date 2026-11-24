"""Hostile-but-bounded shortcut binding pairs must fail closed.

Pure in-memory contract test: no Qt, compositor, OS key map, desktop service,
screen reader or Mint guest is exercised. A registration pair that passes the
tuple/list type gate but whose declared length disagrees with the elements it
actually yields must raise the module's domain error, never a raw ValueError
from tuple unpacking. Such a raw exception would escape the shortcut-safety
gate as an unhandled error instead of a deterministic verdict.
"""
import unittest

from canopy_features.accessibility.shortcut_conflict_check import (
    KIND_DUPLICATE, ShortcutConflictError, detect_shortcut_conflicts)


class LyingTuple(tuple):
    """Bounded hostile pair: claims two elements, yields a different count."""

    def __len__(self):
        return 2


class LyingList(list):
    """Bounded hostile pair: claims two elements, yields a different count."""

    def __len__(self):
        return 2


class HostileShortcutPairTests(unittest.TestCase):
    def test_lying_length_tuple_pair_fails_closed(self):
        for pair in (LyingTuple(("only-action",)),
                     LyingTuple(("a", "b", "c"))):
            with self.subTest(pair=tuple(pair)):
                with self.assertRaises(ShortcutConflictError):
                    detect_shortcut_conflicts(shell=[pair])

    def test_lying_length_list_pair_fails_closed(self):
        for pair in (LyingList(("only-action",)),
                     LyingList(("a", "b", "c"))):
            with self.subTest(pair=tuple(pair)):
                with self.assertRaises(ShortcutConflictError):
                    detect_shortcut_conflicts(user=[pair])

    def test_honest_pairs_and_duplicate_detection_unchanged(self):
        self.assertTrue(detect_shortcut_conflicts(
            shell=[("files.close", "Ctrl+W")]).ok)
        report = detect_shortcut_conflicts(
            shell=[("files.close", "Ctrl+W"), ("files.close", "CTRL+W")])
        self.assertEqual(len(report.of_kind(KIND_DUPLICATE)), 1)


if __name__ == "__main__":
    unittest.main()
