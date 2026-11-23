"""Regression: bool window ids must not alias tracked int ids in select/focus.

``_valid_id`` explicitly rejects bool, but ``select``/``focus`` used plain
membership against the order tuple; ``True == 1`` made a bool match a tracked
int id and be stored as selected/current. These offline unit tests pin the
fail-closed boundary. No windows, keys, Qt or OS services are involved.
"""
import unittest

from canopy_features.windows.switcher_state import SwitcherError, SwitcherState


class SwitcherBoolIdTests(unittest.TestCase):
    def test_select_rejects_bool_aliasing_tracked_int_id(self):
        state = SwitcherState([1, 2, 3], current=1)
        state.begin()
        self.assertEqual(state.selected, 1)
        before = state.snapshot()
        with self.assertRaises(SwitcherError):
            state.select(True)
        self.assertEqual(state.snapshot(), before)
        self.assertIs(state.selected, 1)

    def test_focus_rejects_bool_aliasing_tracked_int_id(self):
        state = SwitcherState([1, 2, 3], current=1)
        before = state.snapshot()
        with self.assertRaises(SwitcherError):
            state.focus(True)
        self.assertEqual(state.snapshot(), before)
        self.assertIs(state.current, 1)

    def test_confirm_never_persists_a_bool_as_current(self):
        state = SwitcherState([1, 2, 3], current=1)
        state.begin()
        self.assertEqual(state.select(2), 2)
        with self.assertRaises(SwitcherError):
            state.select(True)
        self.assertIs(state.selected, 2)
        self.assertIs(state.confirm(), 2)
        self.assertIs(state.current, 2)

    def test_bool_rejected_even_without_an_int_id_tracked(self):
        state = SwitcherState(["a", "b"], current="a")
        state.begin()
        with self.assertRaises(SwitcherError):
            state.select(True)
        with self.assertRaises(SwitcherError):
            state.focus(True)

    def test_valid_int_and_string_ids_still_work(self):
        state = SwitcherState([1, 2, 3], current=1)
        state.begin()
        self.assertEqual(state.select(3), 3)
        self.assertIs(state.selected, 3)
        state.cancel()  # focus is only legal while idle
        self.assertEqual(state.focus(2), 2)
        self.assertIs(state.current, 2)
        names = SwitcherState(["a", "b"], current="a")
        names.begin()
        self.assertEqual(names.select("b"), "b")
        names.cancel()
        self.assertEqual(names.focus("a"), "a")

    def test_focus_none_still_clears_focus(self):
        state = SwitcherState([1, 2, 3], current=1)
        self.assertIsNone(state.focus(None))
        self.assertIsNone(state.current)


if __name__ == "__main__":
    unittest.main()
