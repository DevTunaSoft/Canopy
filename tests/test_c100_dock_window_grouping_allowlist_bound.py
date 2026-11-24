"""Regression tests for the bounded trusted allowlist in dock window grouping.

Run: python -m unittest tests.test_c100_dock_window_grouping_allowlist_bound -v
No Qt runtime, window manager, D-Bus or Linux Mint host is involved.
"""
import unittest

from canopy_features.dock import window_grouping as wg
from canopy_features.dock.window_grouping import (
    MAX_GROUPS,
    WindowGroup,
    WindowGroupingError,
    WindowRecord,
    group_windows_by_desktop_id,
)

TRUSTED = {
    "firefox.desktop": "Browser",
    "org.gnome.Terminal.desktop": "Terminal",
}


def trusted_map(count):
    """Build ``count`` distinct, valid desktop-id -> dock-label entries."""
    return {"app%d.desktop" % i: "App%d" % i for i in range(count)}


class AllowlistBoundTests(unittest.TestCase):
    """The host-supplied allowlist must be bounded like every other input."""

    def test_allowlist_bound_constant_declared(self):
        self.assertTrue(hasattr(wg, "MAX_TRUSTED_APPLICATIONS"))
        self.assertIs(type(wg.MAX_TRUSTED_APPLICATIONS), int)
        self.assertEqual(wg.MAX_TRUSTED_APPLICATIONS, MAX_GROUPS)

    def test_oversized_allowlist_rejected(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id([], trusted_map(MAX_GROUPS + 1))

    def test_oversized_allowlist_rejected_even_with_windows(self):
        windows = [WindowRecord(window_id=1, desktop_id="app0.desktop")]
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(windows, trusted_map(MAX_GROUPS + 1))

    def test_oversized_allowlist_rejected_with_no_windows(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id((), trusted_map(MAX_GROUPS * 2))


class ControlTests(unittest.TestCase):
    """Existing behavior must survive the new bound."""

    def test_small_allowlist_still_maps(self):
        result = group_windows_by_desktop_id(
            [WindowRecord(window_id=11, desktop_id="firefox.desktop")],
            {"firefox.desktop": "Browser"},
        )
        self.assertEqual(result.groups,
                         (WindowGroup("firefox.desktop", "Browser", (11,)),))

    def test_exact_boundary_allowlist_accepted(self):
        result = group_windows_by_desktop_id([], trusted_map(MAX_GROUPS))
        self.assertEqual(result.groups, ())

    def test_invalid_entry_still_rejected(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id([], {"firefox.desktop": ""})

    def test_window_and_group_bounds_still_enforced(self):
        wins = [WindowRecord(window_id=i, desktop_id="firefox.desktop")
                for i in range(3)]
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(wins, TRUSTED, max_windows=2)
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(
                [WindowRecord(1, "firefox.desktop"),
                 WindowRecord(2, "org.gnome.Terminal.desktop")],
                TRUSTED, max_groups=1)


if __name__ == "__main__":
    unittest.main()
