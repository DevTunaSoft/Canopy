"""Regression tests for hostile-but-bounded string-like labels in ranking.

PROVABLE defect on integration tip 2051dfd:

  * ``rank_applications("fire", ["Firefox", BrokenCasefold("xFirefox")])``
    accepts a ``str`` subclass in ``_iter_titles`` and then calls its
    overridden ``casefold()``, leaking a raw ``AttributeError`` instead of
    the module's ``TypeError``.
  * ``rank_applications("", [BrokenCasefold("Firefox")])`` takes the blank
    query path, never calls ``casefold()`` and emits a ``RankedMatch`` for the
    malformed label: a false ranking-valid claim from the same bad input.
  * A hostile query subclass is silently stripped into a plain ``str`` and
    accepted as well.

All inputs are finite and bounded: one short label, one call. No Qt, desktop
database, process launch, polling, filesystem walk or visual claim is involved.
"""
import unittest
from typing import cast

from canopy_features.launcher.app_search_ranking import (
    ALL,
    PREFIX,
    RankedMatch,
    rank_applications,
)


class BrokenCasefold(str):
    """Bounded hostile label: string-like, but not a real string contract."""

    def casefold(self) -> str:
        # Deliberately violates str.casefold's return contract at runtime.
        return cast(str, None)


class HostileLabelTests(unittest.TestCase):
    def test_broken_casefold_title_nonblank_query_fails_closed(self):
        with self.assertRaises(TypeError):
            rank_applications("fire", ["Firefox", BrokenCasefold("xFirefox")])

    def test_broken_casefold_title_blank_query_fails_closed(self):
        for query in ("", "  \t "):
            with self.subTest(query=query):
                with self.assertRaises(TypeError):
                    rank_applications(query, [BrokenCasefold("Firefox")])

    def test_hostile_query_fails_closed(self):
        with self.assertRaises(TypeError):
            rank_applications(BrokenCasefold("fire"), ["Firefox"])

    def test_broken_casefold_title_is_rejected_even_when_unmatched(self):
        with self.assertRaises(TypeError):
            rank_applications("zzzzq", [BrokenCasefold("Mail")])

    # ---- Controls: valid plain strings must keep the existing contract ----
    def test_plain_strings_still_rank(self):
        result = rank_applications("fire", ["Mail", "Firefox", "Fire"])
        self.assertEqual([m.name for m in result], ["Fire", "Firefox"])
        self.assertEqual([m.tier for m in result], ["exact", "prefix"])
        self.assertTrue(all(type(m) is RankedMatch for m in result))

    def test_plain_strings_blank_query_still_return_all(self):
        apps = ["Settings", "Files", "Browser"]
        result = rank_applications("  ", apps)
        self.assertEqual([m.name for m in result], apps)
        self.assertEqual([m.tier for m in result], [ALL, ALL, ALL])
        self.assertEqual([m.index for m in result], [0, 1, 2])

    def test_prefix_tier_control(self):
        result = rank_applications("fire", ["Firefox"])
        self.assertEqual(result[0].tier, PREFIX)


if __name__ == "__main__":
    unittest.main()
