"""Offline regression tests for bounded launcher keyboard focus state."""
from __future__ import annotations

import dataclasses
import inspect
import unittest

from canopy_features.launcher import launcher_keyboard_navigation as nav


class GridFocusTests(unittest.TestCase):
    def setUp(self):
        self.grid = nav.make_grid([f"app-{i}" for i in range(7)], columns=3)

    def test_compact_grid_shape(self):
        self.assertEqual(self.grid.rows, 3)
        self.assertEqual(self.grid.columns, 3)
        self.assertEqual(len(self.grid.items), 7)

    def test_empty_grid_has_no_focus(self):
        empty = nav.make_grid([], columns=3)
        self.assertEqual(empty.rows, 0)
        self.assertEqual(nav.focus_index(empty, 0), nav.NO_FOCUS)
        self.assertEqual(nav.move(empty, 0, "right"), nav.NO_FOCUS)
        self.assertIsNone(nav.item_at(empty, 0))

    def test_out_of_range_focus_is_clamped(self):
        self.assertEqual(nav.focus_index(self.grid, -99), 0)
        self.assertEqual(nav.focus_index(self.grid, 999), 6)
        self.assertEqual(nav.item_at(self.grid, 999), "app-6")

    def test_left_and_right_clamp_at_row_edges(self):
        self.assertEqual(nav.move(self.grid, 2, "right"), 2)
        self.assertEqual(nav.move(self.grid, 3, "left"), 3)
        self.assertEqual(nav.move(self.grid, 4, "right"), 5)
        self.assertEqual(nav.move(self.grid, 5, "left"), 4)

    def test_up_and_down_clamp_in_compact_last_row(self):
        self.assertEqual(nav.move(self.grid, 4, "down"), 6)
        self.assertEqual(nav.move(self.grid, 6, "down"), 6)
        self.assertEqual(nav.move(self.grid, 6, "up"), 3)
        self.assertEqual(nav.move(self.grid, 0, "up"), 0)

    def test_home_and_end_address_real_items_only(self):
        self.assertEqual(nav.move(self.grid, 4, "home"), 0)
        self.assertEqual(nav.move(self.grid, 4, "end"), 6)

    def test_unsupported_direction_is_rejected(self):
        for direction in ("diagonal", "", None, 7):
            with self.subTest(direction=direction), self.assertRaises(ValueError):
                nav.move(self.grid, 0, direction)

    def test_grid_and_selection_are_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.grid.columns = 4
        selection = nav.make_selection(["a", "b"])
        with self.assertRaises(dataclasses.FrozenInstanceError):
            selection.index = 1

    def test_grid_validation_is_bounded(self):
        for items, columns in (
            ([f"x{i}" for i in range(nav.MAX_ITEMS + 1)], 3),
            (["a"], nav.MAX_COLUMNS + 1),
            (["a"], 0),
            (["a", "a"], 3),
            ([""], 3),
            (["x" * (nav.MAX_ID_LENGTH + 1)], 3),
            ("not-a-sequence", 3),
            ([7], 3),
        ):
            with self.subTest(items=str(items)[:40], columns=columns), \
                    self.assertRaises(ValueError):
                nav.make_grid(items, columns)

    def test_focus_rejects_non_grid_and_non_integer(self):
        for requested in ("0", 1.5, True, None):
            with self.subTest(requested=requested), self.assertRaises(ValueError):
                nav.focus_index(self.grid, requested)
        with self.assertRaises(ValueError):
            nav.focus_index(["not", "a", "grid"], 0)


class SearchSelectionTests(unittest.TestCase):
    def test_empty_results_select_nothing(self):
        selection = nav.make_selection([], query="no matches")
        self.assertEqual(selection.index, nav.NO_FOCUS)
        self.assertIsNone(nav.selected_item(selection))
        self.assertEqual(nav.move_selection(selection, "next"), selection)

    def test_first_result_is_selected_on_new_query(self):
        selection = nav.make_selection(["firefox", "terminal"])
        self.assertEqual(nav.selected_item(selection), "firefox")

    def test_movement_clamps_at_endpoints(self):
        selection = nav.make_selection(["a", "b", "c"])
        self.assertEqual(nav.selected_item(nav.move_selection(selection, "previous")), "a")
        selection = nav.move_selection(selection, "end")
        self.assertEqual(nav.selected_item(selection), "c")
        self.assertEqual(nav.selected_item(nav.move_selection(selection, "next")), "c")
        self.assertEqual(nav.selected_item(nav.move_selection(selection, "home")), "a")

    def test_stale_index_is_clamped_without_inventing_results(self):
        selection = nav.SearchSelection(results=("only",), index=99)
        self.assertEqual(nav.selected_item(selection), "only")
        stale = nav.SearchSelection(results=("only",), index=-99)
        self.assertEqual(nav.selected_item(stale), "only")

    def test_no_focus_selection_never_claims_an_item(self):
        # NO_FOCUS is the module's explicit "nothing active" sentinel. A
        # selection carrying it alongside results must not report a selected
        # identifier: that is a false navigation-valid claim. An actual
        # navigation may still select the first result afterwards.
        no_focus = nav.SearchSelection(results=("alpha", "beta"), index=nav.NO_FOCUS)
        self.assertIsNone(nav.selected_item(no_focus))
        self.assertEqual(
            nav.selected_item(nav.move_selection(no_focus, "next")), "alpha")

    def test_selection_validation_is_bounded(self):
        for results, query in (
            ([f"x{i}" for i in range(nav.MAX_ITEMS + 1)], ""),
            (["a"], "q" * (nav.MAX_QUERY + 1)),
            (["a"], 7),
            ("not-a-sequence", ""),
            ([""], ""),
            ([None], ""),
        ):
            with self.subTest(results=str(results)[:40], query=str(query)[:20]), \
                    self.assertRaises(ValueError):
                nav.make_selection(results, query)

    def test_invalid_selection_direction_is_rejected(self):
        selection = nav.make_selection(["a"])
        for direction in ("left", "", None):
            with self.subTest(direction=direction), self.assertRaises(ValueError):
                nav.move_selection(selection, direction)


class PurityTests(unittest.TestCase):
    def test_module_has_no_io_time_or_ui_dependencies(self):
        source = inspect.getsource(nav)
        forbidden = ("subprocess", "socket", "threading", "PyQt", "PySide",
                     "QML", " open(", "time.", "requests")
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_module_imports_only_future_and_dataclasses(self):
        imports = [line.strip() for line in inspect.getsource(nav).splitlines()
                   if line.startswith(("import ", "from "))]
        self.assertEqual(imports, [
            "from __future__ import annotations",
            "from dataclasses import dataclass",
        ])


if __name__ == "__main__":
    unittest.main()
