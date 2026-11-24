"""Regression tests for allocation-free validation on blank search queries.

Run: python -m unittest tests.test_c100_launcher_casefold_blank_fastpath -v
"""
import unittest
from unittest.mock import patch

from canopy_features.launcher import app_search_casefold as casefold
from canopy_features.launcher.app_search_casefold import (
    ANY,
    EXACT,
    AppSearchError,
    Match,
    normalize_name,
    rank_matches,
)

ASCII_NAMES = tuple("Application Number %04d" % i for i in range(512))


class BlankFastPathTests(unittest.TestCase):
    def test_blank_ascii_query_skips_unicode_normalization(self):
        with patch.object(casefold.unicodedata, "normalize",
                          wraps=casefold.unicodedata.normalize) as spy:
            result = rank_matches("", ASCII_NAMES, limit=8)
        self.assertEqual(spy.call_count, 1)  # query key only, not 512 names
        self.assertEqual(len(result), 8)

    def test_blank_query_constructs_only_limited_matches(self):
        with patch.object(casefold, "Match", wraps=casefold.Match) as spy:
            result = rank_matches("", ASCII_NAMES, limit=8)
        self.assertEqual(spy.call_count, 8)
        self.assertEqual(len(result), 8)

    def test_non_ascii_blank_query_still_normalizes(self):
        with patch.object(casefold.unicodedata, "normalize",
                          wraps=casefold.unicodedata.normalize) as spy:
            rank_matches("", ("Äpfel", "Café"), limit=8)
        self.assertGreater(spy.call_count, 0)

    def test_blank_query_preserves_scores_and_indices(self):
        names = ("Zeta", "Alpha", "Beta")
        result = rank_matches("", names)
        self.assertEqual(result, (
            Match("Zeta", ANY, 0), Match("Alpha", ANY, 1), Match("Beta", ANY, 2)))

    def test_blank_query_controls_unchanged(self):
        result = rank_matches("alpha", ("Alpha", "Alphabet", "Beta"))
        self.assertEqual([m.score for m in result], [EXACT, casefold.PREFIX])
        self.assertEqual([m.name for m in result], ["Alpha", "Alphabet"])

    def test_blank_query_still_rejects_non_string_names(self):
        for bad in (7, None, b"App", ("App",)):
            with self.subTest(bad=bad):
                with self.assertRaises(AppSearchError):
                    rank_matches("", ("App", bad))

    def test_blank_query_still_rejects_oversized_names(self):
        long_name = "A" * (casefold.MAX_NAME_CHARS + 1)
        with self.assertRaises(AppSearchError):
            rank_matches("", (long_name,))

    def test_blank_query_still_rejects_invalid_unicode(self):
        with self.assertRaises(AppSearchError):
            rank_matches("", ("bad\ud800name",))

    def test_public_normalize_name_is_unchanged(self):
        self.assertEqual(normalize_name("  ÄPFEL "), "äpfel")

    def test_invalid_limit_still_rejected(self):
        for limit in (True, 0, 65, "8"):
            with self.subTest(limit=limit):
                with self.assertRaises(AppSearchError):
                    rank_matches("", ASCII_NAMES, limit=limit)


if __name__ == "__main__":
    unittest.main()
