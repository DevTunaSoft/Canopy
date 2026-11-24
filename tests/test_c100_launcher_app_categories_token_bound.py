"""Regression tests for the bounded Application.categories token iterable.

Run: python -m unittest tests.test_c100_launcher_app_categories_token_bound -v
No Qt runtime, desktop database or process launch is involved.
"""
import unittest

from canopy_features.launcher.app_categories import (
    MAX_CATEGORY_TOKENS,
    Application,
    CategoryError,
)


def tokens(count):
    """Yield ``count`` distinct, well-formed category id tokens."""
    for i in range(count):
        yield "A%d" % i


class CountingTokens:
    """Iterator that records how many tokens the constructor consumed."""

    def __init__(self, count):
        self._source = tokens(count)
        self.consumed = 0

    def __iter__(self):
        return self

    def __next__(self):
        value = next(self._source)
        self.consumed += 1
        return value


class CategoryTokenBoundTests(unittest.TestCase):
    """Constructing an Application must not materialize unbounded tokens."""

    def test_oversized_generator_rejected(self):
        with self.assertRaises(CategoryError):
            Application("app.over.gen", "Over Gen",
                        tokens(MAX_CATEGORY_TOKENS + 1))

    def test_oversized_list_rejected(self):
        with self.assertRaises(CategoryError):
            Application("app.over.list", "Over List",
                        list(tokens(MAX_CATEGORY_TOKENS + 1)))

    def test_oversized_iterator_consumption_is_bounded(self):
        source = CountingTokens(MAX_CATEGORY_TOKENS * 4)
        with self.assertRaises(CategoryError):
            Application("app.over.count", "Over Count", source)
        self.assertLessEqual(source.consumed, MAX_CATEGORY_TOKENS + 1)


class ControlTests(unittest.TestCase):
    """Existing behavior must survive the new bound."""

    def test_small_tuple_accepted(self):
        app = Application("app.ok", "OK", ("AudioVideo", "Game"))
        self.assertEqual(app.categories, ("AudioVideo", "Game"))

    def test_small_generator_materialized(self):
        app = Application("app.gen", "Gen", (x for x in ("AudioVideo", "Game")))
        self.assertEqual(app.categories, ("AudioVideo", "Game"))

    def test_exact_bound_tuple_accepted(self):
        expected = tuple(tokens(MAX_CATEGORY_TOKENS))
        app = Application("app.bound.tuple", "Bound Tuple", expected)
        self.assertEqual(app.categories, expected)

    def test_exact_bound_generator_accepted(self):
        expected = tuple(tokens(MAX_CATEGORY_TOKENS))
        app = Application("app.bound.gen", "Bound Gen",
                          tokens(MAX_CATEGORY_TOKENS))
        self.assertEqual(app.categories, expected)

    def test_bare_string_still_rejected(self):
        with self.assertRaises(CategoryError):
            Application("app.str", "Bare", "AudioVideo")

    def test_non_iterable_still_rejected(self):
        with self.assertRaises(CategoryError):
            Application("app.int", "NonIter", 7)


if __name__ == "__main__":
    unittest.main()
