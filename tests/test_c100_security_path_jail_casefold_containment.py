"""Regression tests: Windows/NTFS case-insensitive containment must not use
full Unicode case folding.

``str.casefold()`` expands characters such as ``ß`` -> ``ss`` and the
ligature ``ﬀ`` -> ``ff``. NTFS and Qt compare path components with one-to-one
(simple) folding, so a casefold-based containment check treats two distinct
directories as the same jail root -- a fail-open that can admit a path outside
the allowed root. These tests are pure/offline and run on any host with an
explicit ``case_sensitive=False``.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_features.security import path_jail_checks as jail  # noqa: E402


class NonExpandingFoldTests(unittest.TestCase):
    """Full-casefold expansions must never collapse distinct NTFS names."""

    # (candidate component, distinct root component) pairs that str.casefold()
    # wrongly equates but Windows/NTFS keeps distinct.
    EXPANSION_PAIRS = (
        ("ß", "ss"),        # U+00DF sharp s
        ("ﬀ", "ff"),        # U+FB00 latin small ligature ff
        ("ﬁ", "fi"),        # U+FB01 latin small ligature fi
        ("ſ", "s"),         # U+017F latin small letter long s
    )

    def test_casefold_expansion_is_not_contained(self):
        for special, expansion in self.EXPANSION_PAIRS:
            with self.subTest(special=special, expansion=expansion):
                self.assertFalse(jail.is_contained(
                    Path("/home") / special / "secret.txt",
                    Path("/home") / expansion,
                    case_sensitive=False,
                ))
                self.assertFalse(jail.is_contained(
                    Path("/home") / expansion / "secret.txt",
                    Path("/home") / special,
                    case_sensitive=False,
                ))

    def test_casefold_expansion_matches_ntfs_normcase_contract(self):
        # Tie the expectation to the actual filesystem's notion of
        # case-insensitive identity: if the host says the names differ, the
        # jail must never claim containment.
        for special, expansion in self.EXPANSION_PAIRS:
            if os.path.normcase(special) == os.path.normcase(expansion):
                continue
            with self.subTest(special=special, expansion=expansion):
                self.assertFalse(jail.is_contained(
                    Path("/jail") / special / "x", Path("/jail") / expansion,
                    case_sensitive=False,
                ))

    def test_expansion_in_ancestor_component_is_not_contained(self):
        # A lookalike in a middle component must not fold into the root path.
        self.assertFalse(jail.is_contained(
            Path("/home/ß/users/shared/file.txt"),
            Path("/home/ss/users"),
            case_sensitive=False,
        ))


class BenignCaseMatchTests(unittest.TestCase):
    """Legitimate case-insensitive matches must still be accepted."""

    def test_ascii_case_match_still_contained(self):
        self.assertTrue(jail.is_contained(
            Path("/HOME/ALICE/Docs/a.txt"), Path("/home/alice"),
            case_sensitive=False,
        ))

    def test_unicode_case_match_still_contained(self):
        # Simple one-to-one lowercase: É -> é, Greek Sigma -> sigma.
        self.assertTrue(jail.is_contained(
            Path("/home/CAFÉ/ΔΟΚΙΜΉ/α.txt"),
            Path("/home/café/δοκιμή"),
            case_sensitive=False,
        ))

    def test_root_itself_and_descendant_with_case_variation(self):
        root = Path("/home/Alice")
        self.assertTrue(jail.is_contained(root, Path("/home/alice"),
                                          case_sensitive=False))
        self.assertTrue(jail.is_contained(root / "Doc" / "A.TXT",
                                          Path("/home/alice"),
                                          case_sensitive=False))

    def test_case_sensitive_branch_still_literal(self):
        self.assertFalse(jail.is_contained(
            Path("/home/ALICE/x"), Path("/home/alice"), case_sensitive=True))


if __name__ == "__main__":
    unittest.main()
