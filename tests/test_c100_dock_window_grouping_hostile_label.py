"""Regression tests for hostile-but-bounded dock grouping labels.

Run: python -m unittest tests.test_c100_dock_window_grouping_hostile_label -v
No Qt runtime, window manager, D-Bus or Linux Mint host is involved.
"""
import unittest

from canopy_features.dock.window_grouping import (
    MAX_ID_BYTES,
    WindowGroup,
    WindowGroupingError,
    WindowRecord,
    group_windows_by_desktop_id,
)

DESKTOP_ID = "firefox.desktop"
TRUSTED = {DESKTOP_ID: "Browser", "org.gnome.Terminal.desktop": "Terminal"}


def group_with_label(label):
    return group_windows_by_desktop_id(
        [WindowRecord(1, DESKTOP_ID)], {DESKTOP_ID: label})


def assert_label_rejected(testcase, label):
    with testcase.assertRaises(WindowGroupingError):
        group_with_label(label)


class HostileLabelTests(unittest.TestCase):
    """A bounded label is not automatically a displayable trusted label."""

    def test_c0_control_label_rejected(self):
        assert_label_rejected(self, "Browser\x1b[31m")

    def test_embedded_nul_label_rejected(self):
        assert_label_rejected(self, "Browser\x00")

    def test_format_character_label_rejected(self):
        assert_label_rejected(self, "Browser\u200b")

    def test_line_separator_label_rejected(self):
        assert_label_rejected(self, "Browser\u2028")

    def test_paragraph_separator_label_rejected(self):
        assert_label_rejected(self, "Browser\u2029")

    def test_private_use_label_rejected(self):
        assert_label_rejected(self, "Browser\ue000")

    def test_noncharacter_label_rejected(self):
        assert_label_rejected(self, "Browser\ufdd0")

    def test_surrogate_label_rejected(self):
        assert_label_rejected(self, "Browser\ud800")

    def test_hostile_label_never_yields_a_group(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(
                [WindowRecord(1, DESKTOP_ID), WindowRecord(2, "org.gnome.Terminal.desktop")],
                {DESKTOP_ID: "Browser\x1b", "org.gnome.Terminal.desktop": "Terminal"})

    def test_control_desktop_id_in_allowlist_rejected(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(
                [], {DESKTOP_ID + "\x1b": "Browser"})

    def test_control_desktop_id_in_window_record_rejected(self):
        with self.assertRaises(WindowGroupingError):
            group_windows_by_desktop_id(
                [WindowRecord(1, DESKTOP_ID + "\x1b")], TRUSTED)


class LegitimateLabelTests(unittest.TestCase):
    """The guard must not reject ordinary or bounded international labels."""

    def test_plain_labels_still_group(self):
        result = group_with_label("Browser")
        self.assertEqual(result.groups,
                         (WindowGroup(DESKTOP_ID, "Browser", (1,)),))
        self.assertEqual(result.unmapped, ())
        self.assertEqual(result.duplicates, ())

    def test_spaced_and_non_ascii_labels_still_group(self):
        for label in ("File Manager", "Caf\u00e9", "\u7f51\u9875", "Terminal \u2192 1"):
            with self.subTest(label=label):
                result = group_with_label(label)
                self.assertEqual(result.groups[0].dock_label, label)

    def test_maximum_byte_length_label_still_grouped(self):
        label = "A" * MAX_ID_BYTES
        self.assertEqual(group_with_label(label).groups[0].dock_label, label)

    def test_overlong_label_still_rejected(self):
        assert_label_rejected(self, "A" * (MAX_ID_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
