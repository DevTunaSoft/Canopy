"""Regression tests for contradictory duplicate window IDs in dock grouping.

Run: python -m unittest tests.test_c100_dock_window_grouping_duplicate_ids -v
No Qt runtime, window manager, D-Bus or Linux Mint host is involved.
"""
import unittest

from canopy_features.dock.window_grouping import (
    WindowGroup,
    WindowGroupingError,
    WindowRecord,
    group_windows_by_desktop_id,
)

TRUSTED = {
    "firefox.desktop": "Browser",
    "org.gnome.Terminal.desktop": "Terminal",
}
UNMAPPED = "com.vendor.Unlisted.desktop"


def rec(window_id, desktop_id):
    return WindowRecord(window_id=window_id, desktop_id=desktop_id)


class ContradictoryDuplicateTests(unittest.TestCase):
    """One opaque window ID cannot be claimed by two desktop IDs."""

    def test_same_id_in_two_trusted_groups_fails_closed(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(
                [rec(8, "firefox.desktop"),
                 rec(8, "org.gnome.Terminal.desktop")], TRUSTED)

    def test_trusted_then_unmapped_sighting_fails_closed(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(
                [rec(8, "firefox.desktop"), rec(8, UNMAPPED)], TRUSTED)

    def test_unmapped_then_trusted_sighting_fails_closed(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(
                [rec(8, UNMAPPED), rec(8, "firefox.desktop")], TRUSTED)

    def test_contradiction_fails_even_after_an_unrelated_group(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(
                [rec(1, "firefox.desktop"),
                 rec(2, "org.gnome.Terminal.desktop"),
                 rec(1, UNMAPPED)], TRUSTED)


class RepeatedSightingTests(unittest.TestCase):
    """Identical repeated sightings keep the existing fold-once behavior."""

    def test_same_id_same_trusted_desktop_still_folded(self):
        result = group_windows_by_desktop_id(
            [rec(42, "firefox.desktop"), rec(42, "firefox.desktop"),
             rec(43, "firefox.desktop")], TRUSTED)
        self.assertEqual(
            result.groups,
            (WindowGroup("firefox.desktop", "Browser", (42, 43)),))
        self.assertEqual(result.duplicates, (42,))
        self.assertEqual(result.unmapped, ())

    def test_same_id_same_unmapped_desktop_still_reported(self):
        result = group_windows_by_desktop_id(
            [rec(4, UNMAPPED), rec(4, UNMAPPED)], TRUSTED)
        self.assertEqual(result.groups, ())
        self.assertEqual(result.unmapped, (rec(4, UNMAPPED),))
        self.assertEqual(result.duplicates, (4,))


if __name__ == "__main__":
    unittest.main()
