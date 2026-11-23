"""Regression tests: fuzzy match span must be the *minimal* subsequence span.

``_subsequence_span`` documents itself as returning the smallest span that
contains the query as an ordered subsequence. The original greedy leftmost
scan returned a non-minimal span whenever query characters repeat, which
silently mis-ranked fuzzy launcher matches. These tests pin the documented
contract, including an exhaustive brute-force parity check.

Pure, offline and stateless; no Qt, desktop database or process launch.
"""
import itertools
import unittest

from canopy_features.launcher.app_search_ranking import (
    FUZZY,
    _subsequence_span,
    rank_applications,
)


def _brute_min_span(query, folded):
    """Independent oracle: minimum end-start+1 over all ordered index picks."""
    if not query:
        return 0
    best = None
    for indices in itertools.combinations(range(len(folded)), len(query)):
        if all(folded[index] == query[offset]
               for offset, index in enumerate(indices)):
            span = indices[-1] - indices[0] + 1
            best = span if best is None else min(best, span)
    return best


class FuzzyMinimalSpanTests(unittest.TestCase):
    def test_minimal_span_with_repeated_query_chars(self):
        # Greedy leftmost picks (0,2) in "aab" -> 3, but (1,2) -> 2.
        self.assertEqual(_subsequence_span("ab", "aab"), 2)
        # Greedy picks (0,7) in "aaaaaaXb" -> 8, but (5,7) -> 3.
        self.assertEqual(_subsequence_span("ab", "aaaaaaXb"), 3)
        # Single-occurrence case must be unchanged.
        self.assertEqual(_subsequence_span("ab", "aXYb"), 4)

    def test_tighter_fuzzy_match_ranks_first_with_repeated_chars(self):
        apps = ["aXYb", "aaaaaaXb"]  # catalog order: looser span first
        result = rank_applications("ab", apps)
        self.assertTrue(all(match.tier == FUZZY for match in result))
        # Minimal spans are 4 and 3, so "aaaaaaXb" must rank first.
        self.assertEqual([match.name for match in result], ["aaaaaaXb", "aXYb"])

    def test_exhaustive_parity_with_brute_force(self):
        alphabet = "ab"
        queries = ["".join(p) for length in (1, 2, 3)
                   for p in itertools.product(alphabet, repeat=length)]
        folded_values = ["".join(p) for length in range(1, 8)
                         for p in itertools.product(alphabet, repeat=length)]
        for query in queries:
            for folded in folded_values:
                with self.subTest(query=query, folded=folded):
                    self.assertEqual(
                        _subsequence_span(query, folded),
                        _brute_min_span(query, folded),
                    )

    def test_no_subsequence_is_none_and_empty_query_is_zero(self):
        self.assertIsNone(_subsequence_span("ab", "ba"))
        self.assertIsNone(_subsequence_span("abc", "acb"))
        self.assertEqual(_subsequence_span("", "anything"), 0)


if __name__ == "__main__":
    unittest.main()
