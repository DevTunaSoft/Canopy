"""Regression: category ordering and lookup must fail closed with CategoryError.

Before the PE-120 fix, ``order_categories(None)`` leaked a raw ``TypeError``,
a non-``Category`` entry leaked ``AttributeError`` from the sort key, and
``CategoryCatalog.get([])`` leaked ``TypeError`` from the mapping lookup.
All three are caller-supplied inputs and must produce the module's domain
error with no raw built-in exception text. Pure Python/offline: no Qt, GIO,
process, timer, VM or Mint claim.
"""
import traceback
import unittest

from canopy_features.launcher.app_categories import (
    Category,
    CategoryCatalog,
    CategoryError,
    STANDARD_CATEGORIES,
    order_categories,
)

# Raw built-in wording that must never reach a caller of the domain API.
_RAW_TOKENS = (
    "unhashable",
    "not iterable",
    "has no attribute",
    "TypeError",
    "AttributeError",
)


def _assert_clean_domain_error(test, caught):
    """No built-in exception is chained or visible in the reported error."""
    error = caught.exception
    test.assertIsNone(error.__cause__)
    # A raise outside an except block has no context to suppress; a raise
    # that translates a built-in must suppress it so no raw text is shown.
    if isinstance(error.__context__, (TypeError, AttributeError)):
        test.assertTrue(error.__suppress_context__)
    rendered = "".join(traceback.format_exception(
        type(error), error, error.__traceback__))
    for token in _RAW_TOKENS:
        test.assertNotIn(token, str(error))
        test.assertNotIn(token, rendered)


class OrderCategoriesInputTests(unittest.TestCase):
    def test_non_iterable_inputs_raise_domain_error_without_raw_text(self):
        for value in (None, 123, object()):
            with self.subTest(value=repr(value)):
                with self.assertRaises(CategoryError) as caught:
                    order_categories(value)
                _assert_clean_domain_error(self, caught)

    def test_non_category_entries_raise_domain_error_without_raw_text(self):
        good = Category("Utility", "Accessories", 130)
        for values in (
            ["Utility"],
            [object()],
            [good, "Network"],
            [good, None],
            [good, 123],
            [good, object()],
        ):
            with self.subTest(values=repr(values)):
                with self.assertRaises(CategoryError) as caught:
                    order_categories(values)
                _assert_clean_domain_error(self, caught)

    def test_scalar_text_is_not_exploded_into_characters(self):
        with self.assertRaises(CategoryError) as caught:
            order_categories("Utility")
        _assert_clean_domain_error(self, caught)

    def test_valid_rank_then_id_order_preserved_across_iterables(self):
        early = Category("Early", "E", 1)
        zed = Category("Zed", "Z", 10)
        alpha = Category("Alpha", "A", 10)
        expected = ("Early", "Alpha", "Zed")
        for values in (
            [zed, alpha, early],
            (zed, alpha, early),
            iter((zed, alpha, early)),
            {"z": zed, "a": alpha, "e": early}.values(),
        ):
            with self.subTest(kind=type(values).__name__):
                ordered = order_categories(values)
                self.assertIsInstance(ordered, tuple)
                self.assertEqual(tuple(c.id for c in ordered), expected)

    def test_equal_rank_ties_break_on_id_and_input_is_not_mutated(self):
        zed = Category("Zed", "Z", 10)
        alpha = Category("Alpha", "A", 10)
        values = [zed, alpha]
        self.assertEqual(tuple(c.id for c in order_categories(values)),
                         ("Alpha", "Zed"))
        self.assertEqual(values, [zed, alpha])


class CatalogLookupInputTests(unittest.TestCase):
    def setUp(self):
        self.catalog = CategoryCatalog()

    def test_unhashable_keys_raise_domain_error_without_raw_text(self):
        for key in ([], ["Utility"], {}, {"id": "Utility"}, set()):
            with self.subTest(key=repr(key)):
                with self.assertRaises(CategoryError) as caught:
                    self.catalog.get(key)
                _assert_clean_domain_error(self, caught)

    def test_known_and_hashable_miss_behavior_unchanged(self):
        known = self.catalog.get("Utility")
        self.assertIsInstance(known, Category)
        self.assertEqual(known.id, "Utility")
        self.assertIsNone(self.catalog.get("X-Missing"))
        # Hashable non-id keys were misses before the fix and stay misses.
        self.assertIsNone(self.catalog.get(123))
        self.assertIsNone(self.catalog.get(None))

    def test_rejected_lookup_leaves_catalog_unchanged(self):
        before = tuple(c.id for c in self.catalog.categories)
        with self.assertRaises(CategoryError):
            self.catalog.get([])
        self.assertEqual(tuple(c.id for c in self.catalog.categories), before)

    def test_catalog_ordering_and_resolution_still_work(self):
        self.assertEqual(tuple(c.id for c in self.catalog.categories),
                         tuple(c.id for c in STANDARD_CATEGORIES))
        resolution = self.catalog.resolve(
            ["Utility", "Network", "AudioVideo", "Utility", "Screensaver"])
        self.assertEqual(tuple(c.id for c in resolution.known),
                         ("AudioVideo", "Network", "Utility"))
        self.assertEqual(resolution.reserved, ("Screensaver",))


if __name__ == "__main__":
    unittest.main()
