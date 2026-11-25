"""Offline tests for Hidden/NoDisplay/OnlyShowIn/NotShowIn visibility.

These are pure-Python tests of the decision component. They do not launch
apps, query GIO, compile Qt or run on Linux Mint.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canopy_features.launcher import desktop_entry_visibility as vis


def fields(*lines):
    return vis.parse_desktop_entry("[Desktop Entry]\n" + "\n".join(lines) + "\n")


class DesktopEntryVisibilityTests(unittest.TestCase):
    def test_parse_keeps_desktop_entry_keys_and_ignores_other_groups(self):
        text = (
            "# a comment\n"
            "[Desktop Entry]\n"
            "Name=Browser\n"
            "Name[fr]=Navigateur\n"
            "NoDisplay=true\n"
            "\n"
            "[Desktop Action new-window]\n"
            "Hidden=true\n"
        )
        self.assertEqual(vis.parse_desktop_entry(text), {
            "Name": "Browser",
            "Name[fr]": "Navigateur",
            "NoDisplay": "true",
        })

    def test_visible_by_default_known_and_unknown_desktop(self):
        entry = fields("Name=Browser")
        self.assertTrue(vis.should_show(entry, "X-Cinnamon"))
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(vis.should_show(entry))
        self.assertTrue(vis.should_show(entry, ""))

    def test_hidden_true_hides_even_when_only_show_in_matches(self):
        entry = fields("Hidden=true", "OnlyShowIn=X-Cinnamon;")
        self.assertFalse(vis.should_show(entry, "X-Cinnamon"))

    def test_nodisplay_true_hides_and_wins_over_only_show_in(self):
        entry = fields("NoDisplay=true", "OnlyShowIn=GNOME;")
        self.assertFalse(vis.should_show(entry, "GNOME"))

    def test_hidden_wins_over_every_conflicting_flag(self):
        entry = fields(
            "Hidden=true", "NoDisplay=false",
            "OnlyShowIn=GNOME;", "NotShowIn=KDE;",
        )
        self.assertFalse(vis.should_show(entry, "GNOME"))

    def test_hidden_false_nodisplay_false_visible(self):
        entry = fields("Hidden=false", "NoDisplay=false")
        self.assertTrue(vis.should_show(entry, "GNOME"))

    def test_boolean_values_are_case_insensitive(self):
        for token in ("true", "True", "TRUE", "1", "yes", "on"):
            with self.subTest(token=token):
                self.assertFalse(vis.should_show(fields("Hidden=" + token), "GNOME"))
                self.assertFalse(vis.should_show(fields("NoDisplay=" + token), "GNOME"))

    def test_malformed_or_missing_boolean_defaults_false(self):
        entry = fields("Hidden=maybe", "NoDisplay=")
        self.assertTrue(vis.should_show(entry, "GNOME"))
        self.assertTrue(vis.should_show(fields("Name=Browser"), "GNOME"))

    def test_only_show_in_match_shows_and_mismatch_hides(self):
        entry = fields("OnlyShowIn=GNOME;X-Cinnamon;")
        self.assertTrue(vis.should_show(entry, "X-Cinnamon"))
        self.assertFalse(vis.should_show(entry, "KDE"))

    def test_only_show_in_present_hides_unknown_desktop(self):
        entry = fields("OnlyShowIn=GNOME;")
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(vis.should_show(entry))
        self.assertFalse(vis.should_show(entry, ""))
        self.assertFalse(vis.should_show(entry, "UNKNOWN-DESKTOP"))

    def test_empty_only_show_in_hides_everywhere(self):
        entry = fields("OnlyShowIn=")
        self.assertFalse(vis.should_show(entry, "GNOME"))
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(vis.should_show(entry))

    def test_not_show_in_match_hides_mismatch_shows(self):
        entry = fields("NotShowIn=X-Cinnamon;")
        self.assertFalse(vis.should_show(entry, "X-Cinnamon"))
        self.assertTrue(vis.should_show(entry, "GNOME"))

    def test_empty_not_show_in_does_not_restrict(self):
        entry = fields("NotShowIn=")
        self.assertTrue(vis.should_show(entry, "GNOME"))
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(vis.should_show(entry))

    def test_only_show_in_takes_precedence_over_not_show_in(self):
        entry = fields("OnlyShowIn=GNOME;", "NotShowIn=GNOME;")
        self.assertTrue(vis.should_show(entry, "GNOME"))

    def test_desktop_order_first_match_decides(self):
        entry = fields("OnlyShowIn=X-Cinnamon;", "NotShowIn=GNOME;")
        self.assertFalse(vis.should_show(entry, "GNOME:X-Cinnamon"))
        self.assertTrue(vis.should_show(entry, "X-Cinnamon:GNOME"))

    def test_desktop_names_are_case_sensitive(self):
        entry = fields("OnlyShowIn=GNOME;")
        self.assertTrue(vis.should_show(entry, "GNOME"))
        self.assertFalse(vis.should_show(entry, "gnome"))

    def test_current_desktop_read_from_environment(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME:X-Cinnamon"}):
            self.assertTrue(vis.should_show(fields("OnlyShowIn=X-Cinnamon;")))
            self.assertFalse(vis.should_show(fields("NotShowIn=GNOME;")))

    def test_current_desktops_accepts_iterable(self):
        entry = fields("OnlyShowIn=GNOME;")
        self.assertTrue(vis.should_show(entry, ["KDE", "GNOME"]))
        self.assertFalse(vis.should_show(entry, ["KDE", "XFCE"]))

    def test_should_show_file_reads_desktop_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.desktop"
            path.write_text(
                "[Desktop Entry]\nName=Browser\nOnlyShowIn=X-Cinnamon;\n",
                encoding="utf-8",
            )
            self.assertTrue(vis.should_show_file(path, "X-Cinnamon"))
            self.assertFalse(vis.should_show_file(path, "GNOME"))

    def test_should_show_file_tolerates_invalid_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.desktop"
            path.write_bytes(b"[Desktop Entry]\nName=\xff\nNoDisplay=true\n")
            self.assertFalse(vis.should_show_file(path, "GNOME"))


if __name__ == "__main__":
    unittest.main()
