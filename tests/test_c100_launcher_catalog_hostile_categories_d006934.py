"""Residual audit: hostile category tokens must not be ingested as valid.

Run: python -m unittest tests.test_c100_launcher_catalog_hostile_categories_d006934 -v
No filesystem access, process launch, desktop database or Qt runtime is used.

Contract: compose_launcher_catalog claims ``no_invalid_entries_accepted`` for
every emitted snapshot. Category tokens are display text carried in the
host-ready rows, so a token containing a control/format/noncharacter scalar
must fail closed just like an unsafe Name title; accepting one would make
that negative claim false.
"""
import unittest

from canopy_features.launcher.desktop_entry_parser import DesktopEntry
from canopy_features.launcher.launcher_catalog_ingest import (
    CatalogIngestError,
    compose_launcher_catalog,
)

APP_ID = "org.example.Catalog.desktop"


def pair(*, categories):
    return (APP_ID, DesktopEntry(values={
        "Type": "Application",
        "Name": "Example",
        "Exec": "/usr/bin/example",
        "Categories": categories,
    }, localized={}))


class HostileCategoryTests(unittest.TestCase):
    def test_non_printable_category_token_is_refused(self):
        # Same unsafe Unicode categories the module already refuses in a
        # title and the Desktop Entry parser refuses on every raw line.
        for token in (
            "Ga\x85me",     # Cc (C1 NEL)
            "Ga\u202eme",   # Cf (right-to-left override)
            "Ga\u200bme",   # Cf (zero-width space)
            "Ga\ue000me",   # Co (private use)
            "Ga\u2028me",   # Zl (line separator)
            "Ga\u2029me",   # Zp (paragraph separator)
            "Ga\u0378me",   # Cn (unassigned)
        ):
            with self.subTest(token=token):
                with self.assertRaises(CatalogIngestError):
                    compose_launcher_catalog(
                        (pair(categories="Game;" + token + ";"),))

    def test_plain_and_legitimate_unicode_categories_still_ingest(self):
        snapshot = compose_launcher_catalog(
            (pair(categories="Game;Caf\u00e9;\u65e5\u672c\u8a9e;"),))
        self.assertEqual(snapshot.rows[0].categories,
                         ("Game", "Caf\u00e9", "\u65e5\u672c\u8a9e"))
        self.assertIn("no_invalid_entries_accepted", snapshot.claims)


if __name__ == "__main__":
    unittest.main()
