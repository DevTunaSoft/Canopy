"""Regression tests for wrong-type catalog titles in launcher ranking.

PROVABLE defect on integration tip 38bc65ba:
  * rank_applications("fire", ["Firefox", 123]) calls ``name.casefold()`` on
    the non-str title and leaks a raw ``AttributeError`` instead of a clean
    ``TypeError``.
  * rank_applications("", [123]) (blank query) silently accepts the non-str
    title into a RankedMatch, so the two code paths disagree about the type
    contract and a malformed catalog can reach a downstream host.

The fix validates titles as str in BOTH paths and rejects a bare str/bytes
catalog (which would otherwise be enumerated into single-character titles).
No Qt, desktop database, process launch, polling or GUI is involved.
"""
import unittest

from canopy_features.launcher.app_search_ranking import (
    ALL,
    EXACT,
    PREFIX,
    RankedMatch,
    rank_applications,
)

# Finite, bounded wrong-type values; no unbounded iterables in RED tests.
BAD_TITLES = (None, 123, 3.5, b"Firefox", bytearray(b"Firefox"),
              ["Firefox"], ("Firefox",), {"title": "Firefox"}, object())


class RankingTitleTypeTests(unittest.TestCase):
    def test_non_str_title_nonblank_query_raises_type_error(self):
        for bad in BAD_TITLES:
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(TypeError):
                    rank_applications("fire", ["Firefox", bad])

    def test_non_str_title_blank_query_raises_type_error(self):
        for bad in BAD_TITLES:
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(TypeError):
                    rank_applications("", [bad])

    def test_non_str_title_only_entry_raises_type_error(self):
        for query in ("fire", ""):
            with self.subTest(query=query):
                with self.assertRaises(TypeError):
                    rank_applications(query, [None])

    def test_bare_string_catalog_is_rejected(self):
        # A bare string is an iterable of single characters, not a catalog of
        # titles; enumerating it produces nonsensical one-character matches.
        for bad in ("Firefox", b"Firefox", bytearray(b"Firefox")):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(TypeError):
                    rank_applications("f", bad)
                with self.subTest(query="blank"):
                    with self.assertRaises(TypeError):
                        rank_applications("", bad)

    def test_non_iterable_catalog_raises_type_error(self):
        for bad in (123, None, 3.5):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(TypeError):
                    rank_applications("fire", bad)

    # ---- Controls: must pass on the pristine base as well as after the fix ----
    def test_str_titles_nonblank_still_rank(self):
        result = rank_applications("fire", ["Firefox", "Fire", "Mail"])
        self.assertEqual([m.name for m in result], ["Fire", "Firefox"])
        self.assertEqual([m.tier for m in result], [EXACT, PREFIX])
        self.assertTrue(all(type(m) is RankedMatch for m in result))

    def test_str_titles_blank_query_still_returns_all(self):
        apps = ["Settings", "Files", "Browser"]
        result = rank_applications("   ", apps)
        self.assertEqual([m.name for m in result], apps)
        self.assertEqual([m.tier for m in result], [ALL, ALL, ALL])
        self.assertEqual([m.index for m in result], [0, 1, 2])

    def test_empty_catalog_is_fine(self):
        self.assertEqual(rank_applications("fire", []), ())
        self.assertEqual(rank_applications("", []), ())

    def test_query_wrong_type_still_type_error(self):
        for bad in (None, 123, b"fire", ["fire"]):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(TypeError):
                    rank_applications(bad, ["Firefox"])

    def test_generator_catalog_of_str_titles_is_supported(self):
        apps = (name for name in ("Firefox", "Fire", "Mail"))
        result = rank_applications("fire", apps)
        self.assertEqual([m.name for m in result], ["Fire", "Firefox"])


if __name__ == "__main__":
    unittest.main()
