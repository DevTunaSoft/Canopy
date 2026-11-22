"""Offline unit tests for C100 focus-selection recovery.

These exercise the pure-Python state model only. They do not test a real Qt
window, a compositor, Linux Mint, or any live desktop focus behavior.
"""

import threading
import unittest
from dataclasses import FrozenInstanceError

from canopy_features.reliability.focus_reconciliation import (
    DEFAULT_MAX_WINDOWS,
    FocusError,
    FocusResult,
    FocusSelection,
)


class FocusSelectionTests(unittest.TestCase):
    def test_initial_selection_is_first_window(self):
        selection = FocusSelection(["a", "b", "c"])
        self.assertEqual(selection.windows, ("a", "b", "c"))
        self.assertEqual(selection.focus, "a")
        self.assertEqual(len(selection), 3)

    def test_add_focuses_first_then_keeps_focus(self):
        selection = FocusSelection()
        self.assertIsNone(selection.focus)
        first = selection.add("a")
        self.assertTrue(first.changed)
        self.assertEqual(first.reason, "focused-first")
        later = selection.add("b")
        self.assertFalse(later.changed)
        self.assertEqual(selection.focus, "a")

    def test_focus_window_selects_and_rejects_unknown(self):
        selection = FocusSelection(["a", "b"])
        result = selection.focus_window("b")
        self.assertEqual(result.previous, "a")
        self.assertEqual(result.current, "b")
        self.assertEqual(selection.focus, "b")
        with self.assertRaises(FocusError):
            selection.focus_window("missing")
        self.assertEqual(selection.focus, "b")

    def test_focus_tracks_identity_not_positional_index(self):
        selection = FocusSelection(["a", "b", "c"])
        selection.focus_window("c")
        selection.remove("a")
        self.assertEqual(selection.focus, "c")
        self.assertEqual(selection.next().current, "b")

    def test_window_death_of_focused_window_recovers_to_next(self):
        selection = FocusSelection(["a", "b", "c"])
        selection.focus_window("b")
        result = selection.remove("b")
        self.assertTrue(result.changed)
        self.assertEqual(result.reason, "recovered-next")
        self.assertEqual(result.previous, "b")
        self.assertEqual(result.current, "c")
        self.assertEqual(selection.focus, "c")
        self.assertEqual(selection.windows, ("a", "c"))

    def test_window_death_of_last_focused_window_wraps_to_previous(self):
        selection = FocusSelection(["a", "b", "c"])
        selection.focus_window("c")
        result = selection.remove("c")
        self.assertEqual(result.reason, "recovered-previous")
        self.assertEqual(selection.focus, "b")

    def test_window_death_of_unfocused_window_keeps_focus(self):
        selection = FocusSelection(["a", "b", "c"])
        selection.focus_window("b")
        result = selection.remove("a")
        self.assertFalse(result.changed)
        self.assertEqual(result.reason, "removed-unfocused")
        self.assertEqual(selection.focus, "b")

    def test_last_window_death_clears_focus(self):
        selection = FocusSelection(["only"])
        result = selection.remove("only")
        self.assertTrue(result.changed)
        self.assertEqual(result.reason, "focus-lost-empty")
        self.assertIsNone(selection.focus)
        self.assertEqual(len(selection), 0)
        empty = selection.next()
        self.assertEqual(empty.current, None)
        self.assertFalse(empty.changed)
        self.assertEqual(empty.reason, "empty")

    def test_removing_unknown_window_is_noop(self):
        selection = FocusSelection(["a"])
        result = selection.remove("missing")
        self.assertFalse(result.changed)
        self.assertEqual(result.reason, "already-absent")
        self.assertEqual(selection.focus, "a")

    def test_repeated_next_shortcut_wraps_deterministically(self):
        selection = FocusSelection(["a", "b", "c"])
        seen = [selection.focus]
        for _ in range(2 * len(selection)):
            seen.append(selection.next().current)
        self.assertEqual(seen, ["a", "b", "c", "a", "b", "c", "a"])

    def test_repeated_previous_shortcut_wraps_deterministically(self):
        selection = FocusSelection(["a", "b", "c"])
        seen = [selection.focus]
        for _ in range(2 * len(selection)):
            seen.append(selection.previous().current)
        self.assertEqual(seen, ["a", "c", "b", "a", "c", "b", "a"])

    def test_repeated_shortcuts_after_window_death_stay_valid(self):
        selection = FocusSelection(["a", "b", "c"])
        selection.focus_window("b")
        selection.remove("b")
        self.assertEqual(selection.focus, "c")
        seen = [selection.focus]
        for _ in range(7):
            seen.append(selection.next().current)
        self.assertEqual(seen, ["c", "a", "c", "a", "c", "a", "c", "a"])

    def test_repeated_shortcuts_under_window_churn_stay_bounded(self):
        selection = FocusSelection(range(8))
        for step in range(60):
            if step % 3 == 0:
                selection.next()
            elif step % 3 == 1 and len(selection) > 1:
                selection.previous()
            else:
                victim = selection.windows[step % len(selection)]
                selection.remove(victim)
                if len(selection) == 0:
                    selection.add(step)
            self.assertLessEqual(len(selection), DEFAULT_MAX_WINDOWS)
            self.assertIn(selection.focus, selection.windows)
        self.assertLessEqual(len(selection), DEFAULT_MAX_WINDOWS)

    def test_capacity_bound_is_enforced(self):
        selection = FocusSelection(range(5), max_windows=5)
        with self.assertRaises(FocusError):
            selection.add(5)
        self.assertEqual(len(selection), 5)
        with self.assertRaises(FocusError):
            FocusSelection(max_windows=0)

    def test_invalid_window_ids_rejected_without_state_change(self):
        selection = FocusSelection(["a"])
        for bad in (None, ["x"], "x" * (DEFAULT_MAX_WINDOWS + 1)):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(FocusError):
                    selection.add(bad)
                with self.assertRaises(FocusError):
                    selection.remove(bad)
        self.assertEqual(selection.windows, ("a",))
        self.assertEqual(selection.focus, "a")

    def test_result_is_immutable(self):
        result = FocusResult("a", "b", "selected", True)
        with self.assertRaises(FrozenInstanceError):
            result.current = "c"

    def test_operations_spawn_no_background_threads(self):
        before = threading.active_count()
        selection = FocusSelection(range(16))
        for _ in range(32):
            selection.next()
            selection.previous()
            if selection.windows:
                selection.remove(selection.windows[-1])
        self.assertEqual(threading.active_count(), before)


if __name__ == "__main__":
    unittest.main()
