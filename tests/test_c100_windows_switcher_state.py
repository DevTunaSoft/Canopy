"""Offline unit tests for deterministic keyboard window-switch selection state.

No real windows, keys, Qt or OS services are involved. Every assertion is a
pure in-memory transition on SwitcherState.
"""
import unittest
from pathlib import Path

from canopy_features.windows.switcher_state import (
    MAX_WINDOWS, SwitcherError, SwitcherState, SwitchState,
)

SOURCE = (Path(__file__).resolve().parents[1] /
          "canopy_features" / "windows" / "switcher_state.py")


class SwitcherStateTests(unittest.TestCase):
    def test_begin_next_previous_confirm_lifecycle(self):
        state = SwitcherState(["a", "b", "c"], current="a")
        self.assertFalse(state.active)
        self.assertIsNone(state.selected)
        self.assertEqual(state.begin(), "a")
        self.assertTrue(state.active)
        self.assertEqual(state.next(), "b")
        self.assertEqual(state.next(), "c")
        self.assertEqual(state.previous(), "b")
        self.assertEqual(state.confirm(), "b")
        self.assertEqual(state.current, "b")
        self.assertFalse(state.active)
        self.assertIsNone(state.selected)

    def test_next_wraps_from_last_to_first(self):
        state = SwitcherState(["a", "b", "c"], current="c")
        self.assertEqual(state.begin(), "c")
        self.assertEqual(state.next(), "a")
        self.assertEqual(state.next(), "b")
        self.assertEqual(state.next(), "c")

    def test_previous_wraps_from_first_to_last(self):
        state = SwitcherState(["a", "b", "c"], current="a")
        self.assertEqual(state.begin(), "a")
        self.assertEqual(state.previous(), "c")
        self.assertEqual(state.previous(), "b")
        self.assertEqual(state.previous(), "a")

    def test_cancel_keeps_current_and_ends_cycle(self):
        state = SwitcherState(["a", "b"], current="a")
        state.begin()
        state.next()
        self.assertEqual(state.cancel(), "a")
        self.assertEqual(state.current, "a")
        self.assertFalse(state.active)
        self.assertIsNone(state.selected)

    def test_selected_window_dies_moves_to_successor_with_wrap(self):
        state = SwitcherState(["a", "b", "c"], current="a")
        state.begin()
        state.next()
        state.next()
        self.assertEqual(state.selected, "c")  # last window selected
        self.assertTrue(state.remove("c"))
        self.assertEqual(state.order, ("a", "b"))
        self.assertEqual(state.selected, "a")  # successor wraps to first
        self.assertEqual(state.next(), "b")
        self.assertEqual(state.next(), "a")

    def test_non_selected_window_dies_keeps_selection_and_wrap(self):
        state = SwitcherState(["a", "b", "c", "d"], current="a")
        state.begin()
        state.next()
        state.next()
        self.assertEqual(state.selected, "c")
        self.assertTrue(state.remove("a"))  # an earlier window dies
        self.assertEqual(state.selected, "c")
        self.assertEqual(state.order, ("b", "c", "d"))
        self.assertEqual(state.next(), "d")
        self.assertEqual(state.next(), "b")  # wraps over survivors

    def test_current_window_dies_updates_focus_deterministically(self):
        state = SwitcherState(["a", "b", "c"], current="a")
        state.begin()
        state.next()  # selected b, current a
        self.assertEqual(state.selected, "b")
        self.assertTrue(state.remove("a"))
        self.assertEqual(state.current, "b")
        self.assertEqual(state.selected, "b")
        self.assertEqual(state.confirm(), "b")

    def test_last_window_dies_deactivates_cleanly(self):
        state = SwitcherState(["a"], current="a")
        self.assertEqual(state.begin(), "a")
        self.assertTrue(state.remove("a"))
        self.assertEqual(state.order, ())
        self.assertIsNone(state.selected)
        self.assertIsNone(state.current)
        self.assertFalse(state.active)

    def test_remove_unknown_is_noop_and_preserves_state(self):
        state = SwitcherState(["a", "b"], current="a")
        state.begin()
        before = state.snapshot()
        self.assertFalse(state.remove("z"))
        self.assertEqual(state.snapshot(), before)

    def test_same_operations_produce_same_snapshots(self):
        def run():
            state = SwitcherState(["a", "b", "c"], current="a")
            results = [state.snapshot()]
            for name in ("begin", "next", "next", "previous", "confirm"):
                getattr(state, name)()
                results.append(state.snapshot())
            return results

        self.assertEqual(run(), run())

    def test_select_jump_and_validation(self):
        state = SwitcherState(["a", "b", "c"], current="a")
        state.begin()
        self.assertEqual(state.select("c"), "c")
        self.assertEqual(state.selected, "c")
        with self.assertRaises(SwitcherError):
            state.select("z")

    def test_transitions_require_active_selection(self):
        state = SwitcherState(["a", "b"], current="a")
        for operation in (state.next, state.previous, state.confirm,
                          state.cancel):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(SwitcherError):
                    operation()
        with self.assertRaises(SwitcherError):
            state.select("b")

    def test_focus_only_when_idle_and_only_for_tracked_ids(self):
        state = SwitcherState(["a", "b"], current="a")
        self.assertEqual(state.focus("b"), "b")
        self.assertEqual(state.current, "b")
        with self.assertRaises(SwitcherError):
            state.focus("z")
        state.begin()
        with self.assertRaises(SwitcherError):
            state.focus("a")

    def test_empty_switcher_begin_is_idle_noop(self):
        state = SwitcherState([])
        self.assertIsNone(state.begin())
        self.assertFalse(state.active)
        self.assertIsNone(state.selected)

    def test_rejects_invalid_duplicate_and_overbound_windows(self):
        for windows in (
            "ab",                            # bare str is not a list/tuple
            ["a", "a"],                      # duplicate id
            [""],                            # empty id
            [0], [-1], [True],               # invalid ints / bool
            [None], [object()],              # wrong type
            list(range(1, MAX_WINDOWS + 2)),  # one over the hard bound
        ):
            with self.subTest(windows=repr(windows)[:40]):
                with self.assertRaises(SwitcherError):
                    SwitcherState(windows)

        self.assertEqual(
            len(SwitcherState(list(range(1, MAX_WINDOWS + 1))).order),
            MAX_WINDOWS)

    def test_rejects_unknown_or_invalid_current(self):
        for current in ("z", object(), True, -1):
            with self.subTest(current=repr(current)):
                with self.assertRaises(SwitcherError):
                    SwitcherState(["a", "b"], current=current)

    def test_snapshot_is_immutable_value_view(self):
        state = SwitcherState(["a", "b"], current="a")
        snap = state.snapshot()
        self.assertIsInstance(snap, SwitchState)
        self.assertIsInstance(snap.order, tuple)
        with self.assertRaises(Exception):
            snap.active = True

    def test_no_polling_threads_network_or_gui_imports(self):
        code = SOURCE.read_text(encoding="utf-8")
        for forbidden in ("import threading", "import socket", "import time",
                          "QTimer", "subprocess", "asyncio", "Thread(",
                          "while True", "time.sleep", "import random"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
