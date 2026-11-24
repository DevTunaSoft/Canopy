"""Regression tests for duplicate result IDs in a launcher search view.

A READY view whose result list repeats an identifier lets the focus index
change while selected_name stays the same: a false navigation-valid claim.
Such a view cannot come from compose_search_view, but move_focus accepts a
host/replayed record directly and must fail closed on duplicate IDs just as
the validating keyboard factory does. Pure data only: no Qt, process, I/O or
visual claim.
"""
import unittest

from canopy_features.launcher.app_search_casefold import Match
from canopy_features.launcher.launcher_search_view import (
    STATUS_READY,
    SearchView,
    SearchViewError,
    compose_search_view,
    move_focus,
)


def duplicate_view():
    """A bounded READY record carrying the same result ID twice."""
    return SearchView(
        key="firefox",
        results=(Match("Firefox", 2, 0), Match("Firefox", 2, 1)),
        selected_index=0,
        selected_name="Firefox",
        status=STATUS_READY,
    )


class DuplicateResultIdViewTests(unittest.TestCase):
    def test_duplicate_ids_never_yield_a_valid_move(self):
        view = duplicate_view()
        for direction in ("next", "previous", "home", "end"):
            with self.subTest(direction=direction):
                with self.assertRaises(SearchViewError):
                    move_focus(view, direction)

    def test_duplicate_ids_are_rejected_at_compose_time(self):
        with self.assertRaises(SearchViewError):
            compose_search_view("firefox", ("Firefox", "Firefox"))

    def test_unique_view_still_moves_focus(self):
        view = compose_search_view("fi", ("Firefox", "Files"))
        moved = move_focus(view, "next")
        self.assertEqual(moved.status, STATUS_READY)
        self.assertEqual(moved.selected_index, 1)
        self.assertEqual(moved.selected_name, "Files")
        self.assertEqual(view.selected_index, 0)


if __name__ == "__main__":
    unittest.main()
