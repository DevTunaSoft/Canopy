"""Offline unit tests for freedesktop category modelling and ordering.

These tests exercise pure Python only. They do not compile Qt, launch GIO,
or run on Linux Mint; real Mint/Qt acceptance remains NOT RUN here.
"""
import unittest

from canopy_features.launcher.app_categories import (
    Application, Category, CategoryCatalog, CategoryError, CategoryResolution,
    MAX_CATEGORY_TOKENS, NO_CATEGORY_RANK, RESERVED_CATEGORY_IDS,
    STANDARD_CATEGORIES, order_applications, order_categories, parse_categories,
)


class CategoryModelTests(unittest.TestCase):
    def test_standard_categories_are_canonical_and_unique(self):
        ids = [category.id for category in STANDARD_CATEGORIES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "AudioVideo")
        self.assertEqual(ids[-1], "Utility")
        ranks = [category.rank for category in STANDARD_CATEGORIES]
        self.assertEqual(ranks, sorted(ranks))
        self.assertTrue(all(type(category.rank) is int for category in STANDARD_CATEGORIES))

    def test_category_is_frozen_and_validates_fields(self):
        cat = Category("Utility", "Accessories", 130)
        with self.assertRaises(Exception):
            cat.rank = 5
        for bad in (
            lambda: Category("has space", "Name", 1),
            lambda: Category("ok", "", 1),
            lambda: Category("ok", "Name", True),
            lambda: Category("", "Name", 1),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(CategoryError):
                    bad()

    def test_order_categories_uses_rank_then_id_for_ties(self):
        a = Category("Zed", "Z", 10)
        b = Category("Alpha", "A", 10)
        c = Category("Early", "E", 1)
        self.assertEqual([x.id for x in order_categories([a, b, c])],
                         ["Early", "Alpha", "Zed"])


class ParsingTests(unittest.TestCase):
    def test_parse_drops_empty_segments_and_keeps_first_seen_order(self):
        self.assertEqual(parse_categories("Utility;;Network;Utility;"),
                         ("Utility", "Network", "Utility"))

    def test_parse_none_and_empty(self):
        self.assertEqual(parse_categories(None), ())
        self.assertEqual(parse_categories(""), ())
        self.assertEqual(parse_categories("   ;  ; "), ())

    def test_parse_rejects_malformed_and_oversized_input(self):
        for value in ("Bad Id", "Bad_Id", 123, ";".join(["Utility"] * (MAX_CATEGORY_TOKENS + 1))):
            with self.subTest(value=repr(value)[:40]):
                with self.assertRaises(CategoryError):
                    parse_categories(value)


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = CategoryCatalog()

    def test_known_categories_resolve_deduplicated_and_ordered(self):
        resolution = self.catalog.resolve(["Utility", "Network", "Utility", "AudioVideo"])
        self.assertEqual([c.id for c in resolution.known],
                         ["AudioVideo", "Network", "Utility"])
        self.assertEqual(resolution.primary.id, "AudioVideo")
        self.assertEqual(resolution.unknown, ())
        self.assertEqual(resolution.reserved, ())

    def test_unknown_categories_are_reported_not_invented(self):
        resolution = self.catalog.resolve(["X-VendorTool", "Utility", "X-Other"])
        self.assertEqual([c.id for c in resolution.known], ["Utility"])
        self.assertEqual(resolution.unknown, ("X-VendorTool", "X-Other"))
        self.assertIsNone(self.catalog.resolve(["X-VendorTool"]).primary)

    def test_duplicate_unknown_id_is_reported_once(self):
        resolution = self.catalog.resolve(["X-One", "X-One", "X-One"])
        self.assertEqual(resolution.unknown, ("X-One",))
        self.assertEqual(resolution.known, ())

    def test_reserved_categories_are_ignored(self):
        self.assertEqual(RESERVED_CATEGORY_IDS, frozenset({"Screensaver", "TrayIcon", "Applets"}))
        resolution = self.catalog.resolve(["Screensaver", "Utility", "TrayIcon"])
        self.assertEqual(resolution.reserved, ("Screensaver", "TrayIcon"))
        self.assertEqual([c.id for c in resolution.known], ["Utility"])

    def test_resolution_is_immutable(self):
        resolution = self.catalog.resolve(["Utility", "X-Unknown"])
        with self.assertRaises(Exception):
            resolution.known = ()
        with self.assertRaises(TypeError):
            resolution.unknown[0] = "changed"

    def test_resolve_rejects_malformed_and_oversized_ids(self):
        for ids in ("Utility", ["Bad Id"], [123],
                    ["Utility"] * (MAX_CATEGORY_TOKENS + 1)):
            with self.subTest(ids=repr(ids)[:40]):
                with self.assertRaises(CategoryError):
                    self.catalog.resolve(ids)


class CatalogConstructionTests(unittest.TestCase):
    def test_duplicate_category_ids_are_rejected(self):
        with self.assertRaisesRegex(CategoryError, "duplicate category id"):
            CategoryCatalog(extra=[Category("Utility", "Dup", 999)])

    def test_duplicate_in_replacement_set_is_rejected(self):
        cats = [Category("One", "One", 1), Category("One", "Again", 2)]
        with self.assertRaisesRegex(CategoryError, "duplicate"):
            CategoryCatalog(categories=cats)

    def test_custom_category_resolves_and_by_id_is_read_only(self):
        catalog = CategoryCatalog(extra=[Category("X-Text", "Text Tools", 5)])
        self.assertEqual(catalog.get("X-Text").display_name, "Text Tools")
        self.assertEqual(catalog.resolve(["X-Text"]).known[0].id, "X-Text")
        with self.assertRaises(TypeError):
            catalog._by_id["Hack"] = Category("Hack", "H", 0)

    def test_non_category_entry_rejected(self):
        with self.assertRaises(CategoryError):
            CategoryCatalog(categories=["Utility"])


class ApplicationOrderingTests(unittest.TestCase):
    def test_apps_order_by_primary_category_then_title(self):
        catalog = CategoryCatalog()
        apps = (
            Application("z.desktop", "Zed", ("Utility",)),
            Application("a.desktop", "Alpha", ("AudioVideo",)),
            Application("b.desktop", "Beta", ("AudioVideo",)),
            Application("m.desktop", "Music", ("AudioVideo", "Utility")),
        )
        titles = [app.title for app in order_applications(apps, catalog)]
        self.assertEqual(titles, ["Alpha", "Beta", "Music", "Zed"])

    def test_unknown_only_and_no_category_sort_last_deterministically(self):
        catalog = CategoryCatalog()
        apps = (
            Application("u.desktop", "Unknown", ("X-Vendor",)),
            Application("n.desktop", "None", ()),
            Application("k.desktop", "Known", ("Utility",)),
        )
        ordered = order_applications(apps, catalog)
        self.assertEqual([a.title for a in ordered], ["Known", "None", "Unknown"])
        self.assertGreater(NO_CATEGORY_RANK, STANDARD_CATEGORIES[-1].rank)

    def test_duplicate_application_id_collapsed_to_first(self):
        catalog = CategoryCatalog()
        apps = (
            Application("dup.desktop", "First", ("Utility",)),
            Application("dup.desktop", "Second", ("AudioVideo",)),
        )
        ordered = order_applications(apps, catalog)
        self.assertEqual([a.title for a in ordered], ["First"])

    def test_application_is_frozen_and_validates_tokens(self):
        app = Application("a.desktop", "App", ["Utility"])
        self.assertEqual(app.categories, ("Utility",))
        with self.assertRaises(Exception):
            app.title = "changed"
        with self.assertRaises(CategoryError):
            Application("a.desktop", "App", ["Bad Id"])
        with self.assertRaises(CategoryError):
            Application("", "App", ())

    def test_order_requires_catalog(self):
        with self.assertRaises(CategoryError):
            order_applications([], object())


class PurityTests(unittest.TestCase):
    def test_module_has_no_os_qt_network_or_polling_imports(self):
        from pathlib import Path
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/launcher/app_categories.py").read_text(encoding="utf-8")
        for forbidden in ("QTimer", "PyQt", "PySide", "QML", "subprocess",
                          "import socket", "time.sleep", "Thread(", "open("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)

    def test_resolution_type_is_the_declared_result(self):
        catalog = CategoryCatalog()
        self.assertIsInstance(catalog.resolve(["Utility"]), CategoryResolution)


if __name__ == "__main__":
    unittest.main()
