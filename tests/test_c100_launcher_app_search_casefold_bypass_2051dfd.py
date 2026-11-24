"""Regression tests for NFKC-before-casefold (caseless key) bypass.

At tip 2051dfd ``_normalize`` casefolds before NFKC. Compatibility code points
that only acquire a case mapping *after* compatibility decomposition keep their
uppercase form in the "caseless" key (e.g. U+1D2C -> 'A', not 'a'), so an
ordinary lowercase query fails to find an equivalent application name. The key
is also not idempotent: normalizing it again changes it.

These tests are pure Python, bounded (single code points / short strings) and
replayable offline: python -m unittest
tests.test_c100_launcher_app_search_casefold_bypass_2051dfd -v
"""
import unittest

from canopy_features.launcher.app_search_casefold import (
    EXACT,
    matches,
    normalize_for_search,
    normalize_name,
    rank_matches,
)

# Each probe NFKC-decomposes to a *cased* ASCII sequence whose casefold is the
# lowercase form. casefold() on the original code point alone is identity.
COMPATIBILITY_CASED = (
    ("\u1d2c", "a"),       # MODIFIER LETTER CAPITAL A   -> A -> a
    ("\u2102", "c"),       # DOUBLE-STRUCK CAPITAL C     -> C -> c
    ("\u2115", "n"),       # DOUBLE-STRUCK CAPITAL N     -> N -> n
    ("\u210b", "h"),       # SCRIPT CAPITAL H            -> H -> h
    ("\u2116", "no"),      # NUMERO SIGN                 -> No -> no
)


class CompatibleCasefoldTests(unittest.TestCase):
    def test_normalized_key_is_truly_caseless_for_compatibility_capitals(self):
        for probe, expected in COMPATIBILITY_CASED:
            with self.subTest(probe=ascii(probe)):
                self.assertEqual(normalize_name(probe), expected)
                self.assertEqual(normalize_for_search(probe), expected)

    def test_lowercase_query_matches_compatibility_capital_name(self):
        for probe, expected in COMPATIBILITY_CASED:
            with self.subTest(probe=ascii(probe)):
                self.assertTrue(matches(expected, probe))
                ranked = rank_matches(expected, [probe])
                self.assertEqual([(m.name, m.score) for m in ranked],
                                 [(probe, EXACT)])

    def test_search_key_is_idempotent(self):
        for probe, expected in COMPATIBILITY_CASED:
            with self.subTest(probe=ascii(probe)):
                key = normalize_for_search(probe)
                self.assertEqual(normalize_for_search(key), key)

    def test_existing_casefold_collisions_remain_intact(self):
        # Controls: behaviour that must not change when the fold order changes.
        self.assertEqual(normalize_name("Stra\u00dfe"), "strasse")
        self.assertEqual(normalize_for_search("STRASSE"), "strasse")
        self.assertEqual(normalize_for_search("\u0130"), "i\u0307")
        self.assertEqual(normalize_for_search("\uff21\uff21\uff21"), "aaa")
        self.assertEqual(normalize_name("  \u00c4PFEL "), "\u00e4pfel")
        self.assertEqual(normalize_for_search("\u00df"), "ss")


if __name__ == "__main__":
    unittest.main()
