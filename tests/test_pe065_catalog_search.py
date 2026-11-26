"""PE-065 tests for category-aware search over the existing catalog snapshot.

The search reads only rows already produced by ``compose_launcher_catalog``;
it creates no catalog entries, reads no files, launches nothing and polls
nothing. Ranking comes from the existing ``app_search_ranking`` module, and
category ids come from the existing ``app_categories`` parser.
"""
import unittest
from dataclasses import FrozenInstanceError

from canopy_features.launcher.app_categories import CategoryError
from canopy_features.launcher.launcher_catalog_ingest import (
    FIXED_CLAIMS,
    CatalogRow,
    LauncherCatalogSnapshot,
)

try:
    from canopy_features.launcher.catalog_search import (
        MAX_RESULTS,
        CatalogSearchError,
        CatalogSearchResult,
        search_catalog,
    )
except ImportError:  # RED on the unmodified base: the refinement is absent.
    MAX_RESULTS = 64
    CatalogSearchError = CategoryError
    CatalogSearchResult = None
    search_catalog = None


ROWS = (
    CatalogRow("org.example.Firefox.desktop", "Firefox", ("Network",)),
    CatalogRow("org.example.Files.desktop", "Files", ("Utility",)),
    CatalogRow("org.example.FileManager.desktop", "File Manager",
               ("Utility", "System")),
    CatalogRow("org.example.Music.desktop", "Music Player",
               ("AudioVideo", "Audio")),
    CatalogRow("org.example.Conference.desktop", "Conference",
               ("Network", "AudioVideo")),
)
SNAPSHOT = LauncherCatalogSnapshot(
    rows=ROWS, raw_count=len(ROWS), claims=FIXED_CLAIMS)


class CategoryAwareSearchTests(unittest.TestCase):
    def test_category_filter_keeps_only_rows_with_that_existing_token(self):
        results = search_catalog("fire", SNAPSHOT, category="Network")
        self.assertEqual([result.app_id for result in results],
                         ["org.example.Firefox.desktop"])
        self.assertEqual(results[0].title, "Firefox")
        self.assertEqual(results[0].categories, ("Network",))

    def test_blank_query_in_category_keeps_catalog_order(self):
        results = search_catalog("   ", SNAPSHOT, category="Network")
        self.assertEqual([result.app_id for result in results],
                         ["org.example.Firefox.desktop",
                          "org.example.Conference.desktop"])
        self.assertTrue(all(result.tier == "all" for result in results))

    def test_two_categories_on_one_row_both_match_the_filter(self):
        self.assertEqual(
            [result.app_id for result in
             search_catalog("music", SNAPSHOT, category="Audio")],
            ["org.example.Music.desktop"])
        self.assertEqual(
            [result.app_id for result in
             search_catalog("music", SNAPSHOT, category="AudioVideo")],
            ["org.example.Music.desktop"])

    def test_unknown_well_formed_category_returns_no_rows(self):
        self.assertEqual(search_catalog("fire", SNAPSHOT,
                                        category="X-Vendor"), ())

    def test_malformed_category_fails_closed(self):
        for category in ("Bad Id", "Network;Utility", 7, True):
            with self.subTest(category=category):
                with self.assertRaises(CatalogSearchError):
                    search_catalog("fire", SNAPSHOT, category=category)

    def test_query_ranking_is_preserved_within_the_filtered_rows(self):
        results = search_catalog("file", SNAPSHOT, category="Utility")
        self.assertEqual([result.title for result in results],
                         ["Files", "File Manager"])
        self.assertEqual([result.tier for result in results],
                         ["prefix", "prefix"])
        exact = search_catalog("files", SNAPSHOT, category="Utility")
        self.assertEqual(exact[0].title, "Files")
        self.assertEqual(exact[0].tier, "exact")

    def test_duplicate_titles_keep_distinct_app_ids_in_catalog_order(self):
        snapshot = LauncherCatalogSnapshot(rows=(
            CatalogRow("org.example.One.desktop", "Twin", ("Utility",)),
            CatalogRow("org.example.Two.desktop", "Twin", ("Network",)),
        ), claims=FIXED_CLAIMS)
        results = search_catalog("twin", snapshot)
        self.assertEqual([result.app_id for result in results],
                         ["org.example.One.desktop",
                          "org.example.Two.desktop"])
        self.assertEqual([result.index for result in results], [0, 1])

    def test_limit_bounds_the_returned_rows(self):
        results = search_catalog("", SNAPSHOT, limit=2)
        self.assertEqual(len(results), 2)
        for bad in (0, True, MAX_RESULTS + 1, 1.5, "2"):
            with self.subTest(limit=bad):
                with self.assertRaises(CatalogSearchError):
                    search_catalog("", SNAPSHOT, limit=bad)

    def test_result_record_is_immutable(self):
        result = search_catalog("files", SNAPSHOT)[0]
        self.assertIsInstance(result, CatalogSearchResult)
        with self.assertRaises(FrozenInstanceError):
            result.app_id = "changed"

    def test_input_validation_fails_closed(self):
        for query, snapshot in ((None, SNAPSHOT), ("files", None),
                                ("files", "not a snapshot"), (7, SNAPSHOT)):
            with self.subTest(query=query, snapshot=snapshot):
                with self.assertRaises(CatalogSearchError):
                    search_catalog(query, snapshot)

    def test_module_adds_no_io_or_background_behavior(self):
        from pathlib import Path
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/launcher/catalog_search.py").read_text(
                    encoding="utf-8")
        for forbidden in ("QTimer", "PyQt", "PySide", "subprocess",
                          "import os", "import socket", "time.sleep",
                          "Thread(", "open("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
