"""Offline unit tests for the composed launcher search view.

Verifies that bounded Unicode-aware ranking and keyboard focus state are
reconciled into one immutable, fail-closed host record. No Qt, desktop
database, process launch, filesystem walk or desktop claim is involved.
"""
import unittest
from dataclasses import FrozenInstanceError

from canopy_features.launcher.app_search_casefold import ANY, EXACT, PREFIX
from canopy_features.launcher.launcher_keyboard_navigation import NO_FOCUS
from canopy_features.launcher.launcher_search_view import (
    MAX_RESULTS,
    STATUS_EMPTY,
    STATUS_READY,
    SearchView,
    SearchViewError,
    compose_search_view,
    move_focus,
)

NAMES = ("Firefox", "Files", "Konsole", "GNU Image Manipulation Program")


class ComposeSearchViewTests(unittest.TestCase):
    def test_prefix_query_ranks_and_selects_first_result(self):
        view = compose_search_view("fi", NAMES)
        self.assertEqual(view.status, STATUS_READY)
        self.assertEqual([m.name for m in view.results], ["Firefox", "Files"])
        self.assertEqual([m.score for m in view.results], [PREFIX, PREFIX])
        self.assertEqual(view.selected_index, 0)
        self.assertEqual(view.selected_name, "Firefox")

    def test_focus_above_result_count_clamps_to_last(self):
        view = compose_search_view("fi", NAMES, focus=999)
        self.assertEqual(view.selected_index, 1)
        self.assertEqual(view.selected_name, "Files")

    def test_negative_focus_clamps_to_first(self):
        view = compose_search_view("fi", NAMES, focus=-25)
        self.assertEqual(view.selected_index, 0)
        self.assertEqual(view.selected_name, "Firefox")

    def test_no_match_is_empty_with_no_focus(self):
        view = compose_search_view("zzzzqqq", NAMES)
        self.assertEqual(view.status, STATUS_EMPTY)
        self.assertEqual(view.results, ())
        self.assertEqual(view.selected_index, NO_FOCUS)
        self.assertIsNone(view.selected_name)

    def test_blank_query_returns_all_catalog_entries_in_order(self):
        view = compose_search_view("   ", NAMES)
        self.assertEqual(view.status, STATUS_READY)
        self.assertEqual([m.name for m in view.results], list(NAMES))
        self.assertTrue(all(m.score == ANY for m in view.results))
        self.assertEqual(view.selected_name, "Firefox")

    def test_limit_bounds_results(self):
        view = compose_search_view("", NAMES, limit=2)
        self.assertEqual(len(view.results), 2)
        self.assertEqual(view.selected_index, 0)

    def test_nfkc_equivalent_query_matches_exactly(self):
        view = compose_search_view("cafe\u0301", ("Caf\u00e9",))
        self.assertEqual(view.status, STATUS_READY)
        self.assertEqual(view.results[0].score, EXACT)
        self.assertEqual(view.selected_name, "Caf\u00e9")

    def test_focus_stays_in_agreement_with_ranked_names(self):
        view = compose_search_view("", NAMES, focus=3)
        self.assertEqual(view.selected_name, view.results[view.selected_index].name)
        self.assertEqual(view.selected_name, NAMES[3])

    def test_caller_name_sequence_is_not_mutated(self):
        names = list(NAMES)
        compose_search_view("fi", names)
        self.assertEqual(names, list(NAMES))

    def test_frozen_record_rejects_assignment(self):
        view = compose_search_view("fi", NAMES)
        with self.assertRaises(FrozenInstanceError):
            view.selected_index = 5

    def test_to_dict_is_plain_bounded_data(self):
        view = compose_search_view("fi", NAMES)
        payload = view.to_dict()
        self.assertEqual(
            set(payload),
            {"key", "results", "selected_index", "selected_name", "status"},
        )
        self.assertIsInstance(payload["key"], str)
        self.assertIsInstance(payload["results"], list)
        self.assertIsInstance(payload["selected_index"], int)
        self.assertIsInstance(payload["status"], str)


class SearchViewInputValidationTests(unittest.TestCase):
    def test_bool_focus_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("fi", NAMES, focus=True)

    def test_string_focus_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("fi", NAMES, focus="0")

    def test_float_focus_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("fi", NAMES, focus=1.0)

    def test_zero_limit_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("fi", NAMES, limit=0)

    def test_limit_above_max_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("fi", NAMES, limit=MAX_RESULTS + 1)

    def test_bool_limit_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("fi", NAMES, limit=True)

    def test_float_limit_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("fi", NAMES, limit=1.5)

    def test_non_string_query_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view(None, NAMES)

    def test_oversized_query_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("a" * 129, NAMES)

    def test_wrong_type_name_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("fi", ["Firefox", 7])

    def test_oversized_catalog_is_rejected(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("fi", ["App" + str(i) for i in range(4097)])


class MoveFocusTests(unittest.TestCase):
    def test_next_advances_and_clamps_at_end(self):
        view = compose_search_view("", NAMES)
        moved = move_focus(view, "next")
        self.assertEqual(moved.selected_index, 1)
        self.assertEqual(moved.results, view.results)
        last = move_focus(compose_search_view("", NAMES, focus=99), "next")
        self.assertEqual(last.selected_index, len(NAMES) - 1)

    def test_previous_clamps_at_start(self):
        view = compose_search_view("", NAMES)
        moved = move_focus(view, "previous")
        self.assertEqual(moved.selected_index, 0)
        self.assertEqual(moved.selected_name, "Firefox")

    def test_home_and_end_select_boundaries(self):
        view = compose_search_view("", NAMES)
        self.assertEqual(move_focus(view, "end").selected_name, NAMES[-1])
        self.assertEqual(move_focus(view, "home").selected_name, NAMES[0])

    def test_every_move_keeps_focus_and_name_in_agreement(self):
        for direction in ("next", "previous", "home", "end"):
            moved = move_focus(compose_search_view("", NAMES, focus=2), direction)
            self.assertEqual(moved.selected_name, moved.results[moved.selected_index].name)

    def test_empty_view_move_is_a_no_op(self):
        view = compose_search_view("zzzzqqq", NAMES)
        self.assertIs(move_focus(view, "next"), view)

    def test_unsupported_direction_is_rejected(self):
        view = compose_search_view("", NAMES)
        with self.assertRaises(SearchViewError):
            move_focus(view, "diagonal")

    def test_wrong_type_direction_is_rejected(self):
        view = compose_search_view("", NAMES)
        with self.assertRaises(SearchViewError):
            move_focus(view, 3)

    def test_wrong_type_view_is_rejected(self):
        with self.assertRaises(SearchViewError):
            move_focus("not a view", "next")

    def test_original_view_is_unchanged_after_move(self):
        view = compose_search_view("", NAMES)
        move_focus(view, "end")
        self.assertEqual(view.selected_index, 0)


if __name__ == "__main__":
    unittest.main()
