"""Regression: Application.categories must not accept scalar text as tokens.

The catalog models the freedesktop ``Categories=`` field as an ordered
collection of category ids. A bare string is one id, not a sequence of ids;
coercing it with tuple() explodes it into single-character tokens and silently
turns a valid category into bogus unknown categories. Non-iterables currently
leak a raw TypeError instead of the module's domain error.
"""
import unittest

from canopy_features.launcher.app_categories import (
    Application,
    CategoryCatalog,
    CategoryError,
)


class ApplicationCategoryTypeTests(unittest.TestCase):
    def test_string_categories_rejected(self):
        with self.assertRaises(CategoryError):
            Application("a.desktop", "Alpha", "AudioVideo")

    def test_bytes_categories_rejected(self):
        with self.assertRaises(CategoryError):
            Application("b.desktop", "Beta", b"Game")

    def test_reserved_name_as_string_rejected(self):
        with self.assertRaises(CategoryError):
            Application("c.desktop", "Gamma", "Screensaver")

    def test_non_iterable_categories_raise_domain_error(self):
        with self.assertRaises(CategoryError):
            Application("d.desktop", "Delta", 123)

    def test_tuple_categories_still_accepted(self):
        app = Application("e.desktop", "Epsilon", ("AudioVideo", "Game"))
        self.assertEqual(app.categories, ("AudioVideo", "Game"))

    def test_list_categories_still_coerced(self):
        app = Application("f.desktop", "Zeta", ["Utility"])
        self.assertEqual(app.categories, ("Utility",))

    def test_valid_catalog_resolution_unchanged(self):
        app = Application("g.desktop", "Eta", ("Utility", "Network"))
        resolution = CategoryCatalog().resolve(app.categories)
        self.assertEqual(resolution.primary.id, "Network")
