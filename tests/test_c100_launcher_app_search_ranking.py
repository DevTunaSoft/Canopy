"""Offline unit tests for deterministic launcher application-match ranking.

No Qt runtime, desktop database or Mint VM is required. These tests cover tier
ordering, deterministic ties, Unicode case-folding, fuzzy subsequences, empty
queries and large catalogs. They do not prove the ranking is wired into the
compiled Qt launcher.
"""
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from canopy_features.launcher.app_search_ranking import (
    ALL,
    EXACT,
    FUZZY,
    PREFIX,
    SUBSTRING,
    RankedMatch,
    rank_applications,
)


class AppSearchRankingTests(unittest.TestCase):
    def test_tier_order_exact_prefix_substring_fuzzy(self):
        apps = ["f_i_r_e", "aFire", "Firefox", "Fire"]
        result = rank_applications("fire", apps)
        self.assertEqual([m.name for m in result], ["Fire", "Firefox", "aFire", "f_i_r_e"])
        self.assertEqual(
            [m.tier for m in result], [EXACT, PREFIX, SUBSTRING, FUZZY])
        self.assertEqual([m.score for m in result], [4, 3, 2, 1])
        self.assertEqual([m.index for m in result], [3, 2, 1, 0])

    def test_query_is_case_insensitive_and_trimmed(self):
        apps = ["Firefox", "FIREFOX", "firefox"]
        expected = rank_applications("fire", apps)
        self.assertEqual(rank_applications("  FIRE  ", apps), expected)
        self.assertEqual(rank_applications("\tfire\n", apps), expected)
        self.assertTrue(all(m.tier == PREFIX for m in expected))

    def test_unicode_casefold_not_plain_lower(self):
        # casefold maps both to "strasse"; str.lower() would not.
        apps = ["Straße", "STRASSE", "strasse"]
        result = rank_applications("STRASSE", apps)
        self.assertEqual([m.name for m in result], apps)
        self.assertTrue(all(m.tier == EXACT for m in result))

    def test_fuzzy_subsequence_excludes_out_of_order_and_ranks_tighter(self):
        apps = ["a________b", "ba", "a___b", "a_b"]
        result = rank_applications("ab", apps)
        self.assertEqual([m.name for m in result], ["a_b", "a___b", "a________b"])
        self.assertTrue(all(m.tier == FUZZY for m in result))
        self.assertNotIn("ba", [m.name for m in result])

    def test_exact_ties_preserve_catalog_order_across_calls(self):
        apps = ["Fire", "fire", "FIRE", "Unrelated", "fire"]
        first = rank_applications("fire", apps)
        second = rank_applications("fire", apps)
        self.assertEqual(first, second)
        self.assertEqual([m.name for m in first], ["Fire", "fire", "FIRE", "fire"])
        self.assertTrue(all(m.tier == EXACT for m in first))

    def test_prefix_ties_are_deterministic(self):
        apps = ["Firebird", "Firefox", "Firefly"]
        first = rank_applications("fire", apps)
        second = rank_applications("FiRe", apps)
        self.assertEqual(first, second)
        # All prefix tier: shorter title first, then folded title, then index.
        self.assertEqual([m.name for m in first], ["Firefly", "Firefox", "Firebird"])

    def test_empty_query_returns_all_titles_in_catalog_order(self):
        apps = ["Settings", "Files", "Browser", "Files"]
        for query in ("", "   ", " \t\n "):
            with self.subTest(query=query):
                result = rank_applications(query, apps)
                self.assertEqual([m.name for m in result], apps)
                self.assertEqual([m.index for m in result], [0, 1, 2, 3])
                self.assertTrue(all(m.tier == ALL and m.score == 0 for m in result))

    def test_no_match_returns_empty_tuple(self):
        self.assertEqual(rank_applications("zzzzq", ["Firefox", "Mail"]), ())

    def test_large_catalog_is_deterministic_and_does_not_mutate_input(self):
        base = [f"App{i:04d}" for i in range(2000)]
        apps = base + ["Firefox", "Firebird", "afire", "f_i_r_e", "Fire"]
        snapshot = list(apps)

        result = rank_applications("fire", apps)
        self.assertEqual(apps, snapshot)
        self.assertEqual(result, rank_applications("fire", apps))
        self.assertEqual(
            [m.name for m in result], ["Fire", "Firefox", "Firebird", "afire", "f_i_r_e"])

        everything = rank_applications("", apps)
        self.assertEqual(len(everything), len(apps))
        self.assertEqual([m.name for m in everything], apps)
        self.assertEqual([m.index for m in everything], list(range(len(apps))))

    def test_ranked_match_is_immutable_and_fields_are_consistent(self):
        match = rank_applications("fire", ["xFirefox"])[0]
        self.assertIsInstance(match, RankedMatch)
        self.assertEqual(match.name, "xFirefox")
        self.assertEqual(match.tier, SUBSTRING)
        self.assertEqual(match.score, 2)
        self.assertEqual(match.index, 0)
        with self.assertRaises(FrozenInstanceError):
            match.name = "changed"

    def test_module_adds_no_background_or_privileged_behavior(self):
        source = (Path(__file__).resolve().parents[1]
                  / "canopy_features" / "launcher" / "app_search_ranking.py")
        text = source.read_text(encoding="utf-8")
        for forbidden in ("threading", "subprocess", "socket", "time.", "sleep",
                          "QTimer", "while True", "os.system", "popen"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
