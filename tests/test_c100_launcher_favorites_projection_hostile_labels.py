"""Regression tests: hostile-but-bounded catalog labels cannot pass projection.

The projection promises a READY display row only for a source that is safe to
hand to a trusted host. A bounded title can still carry control, bidi,
zero-width, private-use, unassigned or line-separator scalars; accepting one
would emit a plausible-looking READY/favorite claim with an unreadable or
reordered label. These tests are offline unit tests only: no Qt, desktop
session, process launch, network or visual claim is made.
"""
import unicodedata
import unittest

from canopy_features.launcher import launcher_favorites_projection as projection
from canopy_features.launcher.launcher_favorites_projection import (
    ProjectionError,
    STATUS_READY,
    project_results,
)

HOSTILE_TITLES = (
    "Fire\x00fox",       # Cc: embedded NUL
    "Fire\x1b[31mfox",   # Cc: escape sequence
    "Fire\u202efox",     # Cf: right-to-left override
    "Fire\u200dfox",     # Cf: zero-width joiner
    "Fire\ufefffox",     # Cf: byte-order mark in mid-string
    "Fire\u2028fox",     # Zl: line separator
    "Fire\u2029fox",     # Zp: paragraph separator
    "Fire\ue000fox",     # Co: private-use scalar
    "Fire\u0378fox",     # Cn: unassigned scalar
)

SAFE_TITLE = "Caf\u00e9 Fire \u00a0Fox"


class HostileLabelTests(unittest.TestCase):
    def test_hostile_titles_rejected_on_blank_query(self):
        for title in HOSTILE_TITLES:
            with self.subTest(title=unicodedata.category(title[4])):
                catalog = (("org.example.Hostile", title),
                           ("org.example.Other", "Other"))
                with self.assertRaises(ProjectionError):
                    project_results("", catalog,
                                    favorites=["org.example.Hostile"])

    def test_hostile_favorite_title_never_emits_ready_row(self):
        # A favorite label with a bidi override can look like a different app
        # when rendered, so a READY row with favorite=True must never appear.
        title = "Fire\u202efox"
        catalog = (("org.example.Hostile", title),
                   ("org.example.Other", "Other"))
        with self.assertRaises(ProjectionError):
            project_results("fire", catalog,
                            favorites=["org.example.Hostile"])

    def test_hostile_titles_rejected_on_ranked_query(self):
        for title in HOSTILE_TITLES:
            with self.subTest(title=unicodedata.category(title[4])):
                catalog = (("org.example.Hostile", title),
                           ("org.example.Other", "Other"))
                with self.assertRaises(ProjectionError):
                    project_results("fire", catalog)

    def test_hostile_title_not_copied_into_to_dict(self):
        title = "Firefox\u200d"
        catalog = (("org.example.Hostile", title),)
        with self.assertRaises(ProjectionError):
            project_results("", catalog).to_dict()

    def test_printable_unicode_title_still_projects(self):
        catalog = (("org.example.Safe", SAFE_TITLE),
                   ("org.example.Other", "Other"))
        view = project_results("", catalog,
                               favorites=["org.example.Safe"])
        self.assertEqual(view.status, STATUS_READY)
        self.assertEqual(view.rows[0].title, SAFE_TITLE)
        self.assertTrue(view.rows[0].favorite)
        self.assertEqual(view.favorite_count, 1)


if __name__ == "__main__":
    unittest.main()
