"""Regression tests for the bounded favorites snapshot in launcher intent summary.

Run: python -m unittest tests.test_c100_launcher_intent_summary_favorites_bound -v
No Qt runtime, process launch or desktop database is involved.
"""
import unittest

from canopy_features.launcher.launcher_intent_summary import (
    MAX_FAVORITES,
    MAX_FAVORITES_RAW,
    STATUS_READY,
    LauncherIntentError,
    _normalize_favorites,
    summarize_launcher_intent,
)

CATALOG_IDS = frozenset((
    "org.example.One.desktop",
    "org.example.Two.desktop",
    "org.example.Three.desktop",
))
CATALOG = tuple((app_id, app_id.split(".")[-2]) for app_id in sorted(CATALOG_IDS))


class CountingIds:
    """Iterator that records how many favorite ids the composer consumed."""

    def __init__(self, count, *, known=False):
        self.count = count
        self.known = known
        self.consumed = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.consumed >= self.count:
            raise StopIteration
        self.consumed += 1
        if self.known:
            return "org.example.One.desktop"
        return "unknown.app.%d" % self.consumed


class FavoritesBoundTests(unittest.TestCase):
    """Every caller-supplied favorite id counts toward the input bound."""

    def test_unknown_favorites_iterable_is_bounded(self):
        source = CountingIds(MAX_FAVORITES * 100)
        with self.assertRaises(LauncherIntentError):
            _normalize_favorites(source, CATALOG_IDS)
        self.assertLessEqual(source.consumed, MAX_FAVORITES_RAW + 1)

    def test_unknown_favorites_list_rejected(self):
        ids = ["unknown.app.%d" % i for i in range(MAX_FAVORITES_RAW + 1)]
        with self.assertRaises(LauncherIntentError):
            _normalize_favorites(ids, CATALOG_IDS)

    def test_duplicate_known_favorites_are_bounded(self):
        source = CountingIds(MAX_FAVORITES * 10, known=True)
        with self.assertRaises(LauncherIntentError):
            _normalize_favorites(source, CATALOG_IDS)
        self.assertLessEqual(source.consumed, MAX_FAVORITES_RAW + 1)

    def test_summary_rejects_oversized_unknown_favorites(self):
        source = CountingIds(MAX_FAVORITES * 100)
        with self.assertRaises(LauncherIntentError):
            summarize_launcher_intent("One", CATALOG, favorites=source)
        self.assertLessEqual(source.consumed, MAX_FAVORITES_RAW + 1)


class ControlTests(unittest.TestCase):
    """Existing behavior must survive the new bound."""

    def test_known_favorites_kept_in_order(self):
        favorites = ("org.example.Two.desktop", "org.example.One.desktop")
        self.assertEqual(
            _normalize_favorites(favorites, CATALOG_IDS), favorites)

    def test_exact_bound_of_unknown_ids_accepted(self):
        ids = ["unknown.app.%d" % i for i in range(MAX_FAVORITES)]
        self.assertEqual(_normalize_favorites(ids, CATALOG_IDS), ())

    def test_small_known_catalog_accepted(self):
        ids = sorted(CATALOG_IDS)
        self.assertEqual(len(ids), 3)
        self.assertEqual(_normalize_favorites(ids, CATALOG_IDS), tuple(ids))

    def test_over_bound_known_ids_rejected(self):
        ids = tuple("known.app.%02d.desktop" % i
                    for i in range(MAX_FAVORITES + 1))
        with self.assertRaises(LauncherIntentError):
            _normalize_favorites(ids, frozenset(ids))

    def test_non_string_favorite_rejected(self):
        with self.assertRaises(LauncherIntentError):
            _normalize_favorites(("org.example.One.desktop", 7), CATALOG_IDS)

    def test_summary_end_to_end_unchanged(self):
        summary = summarize_launcher_intent(
            "One", CATALOG,
            favorites=("org.example.Two.desktop", "org.example.One.desktop"))
        self.assertEqual(summary.status, STATUS_READY)
        self.assertEqual(summary.favorites,
                         ("org.example.Two.desktop", "org.example.One.desktop"))


if __name__ == "__main__":
    unittest.main()
