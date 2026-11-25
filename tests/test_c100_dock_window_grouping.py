"""Offline unit tests for bounded dock window grouping by desktop ID.

Run: py -3 -m unittest tests.test_c100_dock_window_grouping -v
No Qt runtime, window manager, D-Bus or Linux Mint host is involved.
"""
import unittest
from dataclasses import FrozenInstanceError
from types import MappingProxyType

from canopy_features.dock.window_grouping import (
    GroupingResult,
    WindowGroup,
    WindowGroupingError,
    WindowRecord,
    group_windows_by_desktop_id,
)

TRUSTED = {
    "org.gnome.Nautilus.desktop": "Files",
    "firefox.desktop": "Browser",
    "org.gnome.Terminal.desktop": "Terminal",
}


def rec(window_id, desktop_id):
    return WindowRecord(window_id=window_id, desktop_id=desktop_id)


class CoreGroupingTests(unittest.TestCase):
    def test_groups_multiple_windows_of_same_app_into_one_group(self):
        result = group_windows_by_desktop_id(
            [rec(11, "firefox.desktop"),
             rec(12, "firefox.desktop"),
             rec(13, "firefox.desktop")],
            TRUSTED)
        self.assertEqual(result.groups, (
            WindowGroup("firefox.desktop", "Browser", (11, 12, 13)),
        ))
        self.assertEqual(result.unmapped, ())
        self.assertEqual(result.duplicates, ())

    def test_single_window_still_forms_a_group(self):
        result = group_windows_by_desktop_id(
            [rec(7, "org.gnome.Nautilus.desktop")], TRUSTED)
        self.assertEqual(result.groups, (
            WindowGroup("org.gnome.Nautilus.desktop", "Files", (7,)),
        ))

    def test_multiple_apps_produce_separate_groups_in_first_seen_order(self):
        result = group_windows_by_desktop_id(
            [rec(1, "firefox.desktop"),
             rec(2, "org.gnome.Terminal.desktop"),
             rec(3, "firefox.desktop")],
            TRUSTED)
        self.assertEqual(result.groups, (
            WindowGroup("firefox.desktop", "Browser", (1, 3)),
            WindowGroup("org.gnome.Terminal.desktop", "Terminal", (2,)),
        ))

    def test_empty_input_returns_empty_result(self):
        result = group_windows_by_desktop_id([], TRUSTED)
        self.assertEqual(result, GroupingResult((), (), ()))

    def test_deterministic_for_same_input(self):
        windows = [rec(1, "firefox.desktop"), rec(2, "org.gnome.Nautilus.desktop")]
        first = group_windows_by_desktop_id(windows, TRUSTED)
        second = group_windows_by_desktop_id(windows, TRUSTED)
        self.assertEqual(first, second)


class MissingMappingTests(unittest.TestCase):
    def test_unknown_desktop_id_is_unmapped_and_not_guessed(self):
        unknown = rec(5, "com.vendor.Unlisted.desktop")
        result = group_windows_by_desktop_id(
            [rec(2, "firefox.desktop"), unknown], TRUSTED)
        self.assertEqual(result.groups, (
            WindowGroup("firefox.desktop", "Browser", (2,)),
        ))
        self.assertEqual(result.unmapped, (unknown,))
        self.assertEqual(result.duplicates, ())

    def test_all_unmapped_produces_no_groups(self):
        unknown = rec(9, "org.missing.App.desktop")
        result = group_windows_by_desktop_id([unknown, rec(10, "another.desktop")],
                                             TRUSTED)
        self.assertEqual(result.groups, ())
        self.assertEqual(result.unmapped,
                         (unknown, rec(10, "another.desktop")))

    def test_empty_trusted_map_maps_nothing(self):
        windows = [rec(1, "firefox.desktop")]
        result = group_windows_by_desktop_id(windows, {})
        self.assertEqual(result.groups, ())
        self.assertEqual(result.unmapped, tuple(windows))

    def test_read_only_trusted_map_is_accepted(self):
        result = group_windows_by_desktop_id(
            [rec(1, "firefox.desktop")], MappingProxyType(TRUSTED))
        self.assertEqual(result.groups, (
            WindowGroup("firefox.desktop", "Browser", (1,)),
        ))


class DuplicateWindowTests(unittest.TestCase):
    def test_repeated_window_id_folded_once_and_reported(self):
        result = group_windows_by_desktop_id(
            [rec(42, "firefox.desktop"),
             rec(42, "firefox.desktop"),
             rec(43, "firefox.desktop")],
            TRUSTED)
        self.assertEqual(result.groups, (
            WindowGroup("firefox.desktop", "Browser", (42, 43)),
        ))
        self.assertEqual(result.duplicates, (42,))
        self.assertEqual(result.unmapped, ())

    def test_duplicate_first_occurrence_wins_even_across_desktop_ids(self):
        result = group_windows_by_desktop_id(
            [rec(8, "firefox.desktop"),
             rec(8, "org.gnome.Terminal.desktop")],
            TRUSTED)
        self.assertEqual(result.groups, (
            WindowGroup("firefox.desktop", "Browser", (8,)),
        ))
        self.assertEqual(result.duplicates, (8,))

    def test_duplicate_of_unmapped_window_still_reported(self):
        unknown = rec(4, "org.missing.App.desktop")
        result = group_windows_by_desktop_id([unknown, unknown], TRUSTED)
        self.assertEqual(result.groups, ())
        self.assertEqual(result.unmapped, (unknown,))
        self.assertEqual(result.duplicates, (4,))

    def test_frozen_result_cannot_be_mutated(self):
        result = group_windows_by_desktop_id(
            [rec(1, "firefox.desktop"), rec(1, "firefox.desktop")], TRUSTED)
        with self.assertRaises(TypeError):
            result.groups[0].window_ids[0] = 99  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            result.duplicates += (1,)  # type: ignore[operator]


class TrustBoundaryTests(unittest.TestCase):
    def test_invalid_trusted_map_rejected(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id([], ["not", "a", "map"])

    def test_invalid_trusted_map_entry_rejected(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id([], {"firefox.desktop": ""})

    def test_string_windows_container_rejected(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id("firefox.desktop", TRUSTED)

    def test_non_record_entry_rejected(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id([(1, "firefox.desktop")], TRUSTED)

    def test_unhashable_window_id_rejected(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id([rec([], "firefox.desktop")], TRUSTED)

    def test_invalid_desktop_id_rejected(self):
        for bad in ("", None, 7):
            with self.subTest(bad=bad):
                with self.assertRaises(WindowGroupingError):
                    group_windows_by_desktop_id([rec(1, bad)], TRUSTED)

    def test_window_count_bound_enforced(self):
        windows = [rec(i, "firefox.desktop") for i in range(4)]
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(windows, TRUSTED, max_windows=3)

    def test_group_count_bound_enforced(self):
        windows = [rec(1, "firefox.desktop"), rec(2, "org.gnome.Terminal.desktop")]
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(windows, TRUSTED, max_groups=1)

    def test_input_is_not_mutated(self):
        windows = [rec(1, "firefox.desktop"), rec(1, "firefox.desktop")]
        snapshot = tuple(windows)
        group_windows_by_desktop_id(windows, TRUSTED)
        self.assertEqual(tuple(windows), snapshot)


if __name__ == "__main__":
    unittest.main()
