"""Tests for pure bounded launcher catalog ingestion.

Run: python -m unittest tests.test_c100_launcher_catalog_ingest -v
No file read, process launch, desktop database or Qt runtime is involved.
"""
import unittest
from dataclasses import FrozenInstanceError

from canopy_features.launcher import launcher_catalog_ingest as ingest_mod
from canopy_features.launcher.desktop_entry_parser import DesktopEntry
from canopy_features.launcher.launcher_catalog_ingest import (
    FIXED_CLAIMS,
    MAX_ENTRIES,
    CatalogIngestError,
    compose_launcher_catalog,
)


def entry(name="Example", *, kind="Application", hidden="false",
          no_display="false", categories="Game;Utility;"):
    return DesktopEntry(
        values={
            "Type": kind,
            "Name": name,
            "Exec": "/usr/bin/example",
            "Icon": "example",
            "Hidden": hidden,
            "NoDisplay": no_display,
            "Categories": categories,
        },
        localized={},
    )


def pair(app_id="org.example.Example.desktop", **kwargs):
    return (app_id, entry(**kwargs))


class IngestTests(unittest.TestCase):
    def test_fixed_negative_claims(self):
        self.assertIsInstance(FIXED_CLAIMS, tuple)
        self.assertTrue(FIXED_CLAIMS)
        self.assertTrue(all(type(c) is str for c in FIXED_CLAIMS))
        for claim in ("no_filesystem_io", "no_process_launch",
                      "no_duplicate_ids_emitted", "no_hidden_entries_emitted",
                      "no_invalid_entries_accepted", "no_visual_change"):
            with self.subTest(claim=claim):
                self.assertIn(claim, FIXED_CLAIMS)

    def test_happy_path_preserves_order_and_claims(self):
        snapshot = compose_launcher_catalog((
            pair("org.example.One.desktop", name="One"),
            pair("org.example.Two.desktop", name="Two"),
        ))
        self.assertEqual(snapshot.to_pairs(), (
            ("org.example.One.desktop", "One"),
            ("org.example.Two.desktop", "Two"),
        ))
        self.assertEqual(snapshot.claims, FIXED_CLAIMS)
        self.assertEqual(snapshot.raw_count, 2)
        self.assertEqual(snapshot.duplicate_id_count, 0)

    def test_duplicate_ids_first_occurrence_wins(self):
        snapshot = compose_launcher_catalog((
            pair("org.example.One.desktop", name="First"),
            pair("org.example.One.desktop", name="Second"),
            pair("org.example.Two.desktop", name="Two"),
        ))
        self.assertEqual(snapshot.to_pairs(), (
            ("org.example.One.desktop", "First"),
            ("org.example.Two.desktop", "Two"),
        ))
        self.assertEqual(snapshot.duplicate_id_count, 1)

    def test_hidden_and_no_display_are_skipped_non_destructively(self):
        snapshot = compose_launcher_catalog((
            pair("org.example.Hidden.desktop", name="Hidden", hidden="true"),
            pair("org.example.NoDisplay.desktop", name="NoDisplay",
                 no_display="true"),
            pair("org.example.Visible.desktop", name="Visible"),
        ))
        self.assertEqual(snapshot.to_pairs(),
                         (("org.example.Visible.desktop", "Visible"),))
        self.assertEqual(snapshot.hidden_count, 2)
        self.assertEqual(snapshot.raw_count, 3)

    def test_categories_are_bounded_strings(self):
        snapshot = compose_launcher_catalog((
            pair("org.example.One.desktop", categories="Game;Utility;"),
        ))
        self.assertEqual(snapshot.rows[0].categories, ("Game", "Utility"))

    def test_generator_input_is_supported(self):
        source = (pair("org.example.N%d.desktop" % i, name="N%d" % i)
                  for i in range(4))
        snapshot = compose_launcher_catalog(source)
        self.assertEqual(len(snapshot.rows), 4)

    def test_deterministic_for_same_input(self):
        entries = (pair("org.example.One.desktop", name="One"),
                   pair("org.example.Two.desktop", name="Two"))
        self.assertEqual(compose_launcher_catalog(entries),
                         compose_launcher_catalog(entries))

    def test_empty_input_yields_empty_snapshot(self):
        snapshot = compose_launcher_catalog(())
        self.assertEqual(snapshot.rows, ())
        self.assertEqual(snapshot.claims, FIXED_CLAIMS)

    def test_to_dict_shape(self):
        payload = compose_launcher_catalog((pair(),)).to_dict()
        self.assertEqual(set(payload), {
            "row_count", "raw_count", "hidden_count", "duplicate_id_count",
            "duplicate_title_count", "claims"})

    def test_record_is_frozen(self):
        snapshot = compose_launcher_catalog((pair(),))
        with self.assertRaises(FrozenInstanceError):
            snapshot.raw_count = 99
        with self.assertRaises(FrozenInstanceError):
            snapshot.rows[0].title = "changed"

    def test_module_has_no_io_or_process_import(self):
        with open(ingest_mod.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for token in ("subprocess", "Popen", "os.system", "open(", "Path("):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


class FailClosedTests(unittest.TestCase):
    def test_invalid_app_id_rejected(self):
        for bad in ("not-an-id", "org.example.One", 7, "org.example.X.desktop;rm"):
            with self.subTest(bad=bad):
                with self.assertRaises(CatalogIngestError):
                    compose_launcher_catalog(((bad, entry()),))

    def test_wrong_record_types_rejected(self):
        for bad in ((7, entry()), ("org.example.X.desktop", {}),
                    ("org.example.X.desktop", 7)):
            with self.subTest(bad=bad):
                with self.assertRaises(CatalogIngestError):
                    compose_launcher_catalog((bad,))

    def test_non_application_type_rejected(self):
        with self.assertRaises(CatalogIngestError):
            compose_launcher_catalog(
                (pair("org.example.X.desktop", kind="Link"),))

    def test_missing_or_oversized_title_rejected(self):
        for name in ("", "A" * 257):
            with self.subTest(name=name):
                with self.assertRaises(CatalogIngestError):
                    compose_launcher_catalog(
                        (pair("org.example.X.desktop", name=name),))

    def test_oversized_input_rejected(self):
        entries = tuple(pair("org.example.N%d.desktop" % i, name="N%d" % i)
                        for i in range(MAX_ENTRIES + 1))
        with self.assertRaises(CatalogIngestError):
            compose_launcher_catalog(entries)

    def test_bare_string_container_rejected(self):
        with self.assertRaises(CatalogIngestError):
            compose_launcher_catalog("org.example.X.desktop")


if __name__ == "__main__":
    unittest.main()
