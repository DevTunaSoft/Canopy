"""Regression tests: case-insensitive containment must not fold compatibility
letters into distinct NTFS names (path-jail fail-open).

Python's ``str.lower()`` maps U+1E9E (capital sharp S) to 'ß', U+212A
(Kelvin sign) to 'k' and U+212B (Angstrom sign) to 'å'. Windows/NTFS (and
``os.path.normcase``) treat each pair as *distinct* filenames. The jail's
case-insensitive comparison must therefore keep them distinct too, otherwise
a directory outside the jail root is reported as contained and
:func:`resolve_within` returns an escaping path.

Pure/offline tests run on any host with an explicit ``case_sensitive=False``;
the filesystem test uses temporary directories only (no symlinks, no
privileged operations).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_features.security import path_jail_checks as jail  # noqa: E402


class CompatibilityLetterFoldTests(unittest.TestCase):
    """NTFS-distinct compatibility letters must never compare equal."""

    # (compatibility char, plain char with matching str.lower()).
    PAIRS = (
        ("\u1e9e", "\u00df"),  # ẞ vs ß  (capital vs small sharp S)
        ("\u212a", "k"),       # K vs k  (Kelvin sign)
        ("\u212b", "\u00e5"),  # Å vs å  (Angstrom sign)
    )

    def test_os_normcase_confirms_pairs_are_distinct_on_windows(self):
        # On the Windows host NTFS itself distinguishes these names; this
        # asserts our premise rather than the module's behavior.
        if os.name != "nt":
            self.skipTest("NTFS normcase premise is Windows-specific")
        for special, plain in self.PAIRS:
            with self.subTest(special=special, plain=plain):
                self.assertNotEqual(os.path.normcase(special), os.path.normcase(plain))

    def test_compatibility_letter_is_not_contained_in_plain_root(self):
        for special, plain in self.PAIRS:
            with self.subTest(special=special, plain=plain):
                self.assertFalse(jail.is_contained(
                    Path("/jail") / special / "secret.txt",
                    Path("/jail") / plain,
                    case_sensitive=False,
                ))
                self.assertFalse(jail.is_contained(
                    Path("/jail") / plain / "secret.txt",
                    Path("/jail") / special,
                    case_sensitive=False,
                ))

    def test_compatibility_letter_in_middle_component_is_not_contained(self):
        self.assertFalse(jail.is_contained(
            Path("/jail/\u1e9e/sub/users/secret.txt"),
            Path("/jail/\u00df/sub"),
            case_sensitive=False,
        ))

    def test_pure_casefold_expansion_still_not_contained(self):
        # Guard the neighbouring contract: full-casefold expansion ß->ss
        # must stay rejected (already fixed by the length check).
        self.assertFalse(jail.is_contained(
            Path("/jail/\u00df/x"), Path("/jail/ss"), case_sensitive=False))

    def test_legitimate_unicode_case_match_still_contained(self):
        # Guard against over-correcting: simple one-to-one case pairs that
        # NTFS *does* equate must still match.
        self.assertTrue(jail.is_contained(
            Path("/home/CAFÉ/ΔΟΚΙΜΉ/a.txt"),
            Path("/home/café/δοκιμή"),
            case_sensitive=False,
        ))
        self.assertTrue(jail.is_contained(
            Path("/HOME/ALICE/x"), Path("/home/alice"), case_sensitive=False))


class ResolveWithinCompatibilityLetterTests(unittest.TestCase):
    """Filesystem-backed proof that the fold bug widens the jail."""

    def test_distinct_compatibility_directory_cannot_be_used_as_escape(self):
        special, plain = "\u1e9e", "\u00df"
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            jail_root = base / plain
            outside = base / special
            jail_root.mkdir()
            outside.mkdir()
            (outside / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
            with self.assertRaises(jail.PathJailError):
                jail.resolve_within(
                    jail_root, str(outside / "secret.txt"), case_sensitive=False)


if __name__ == "__main__":
    unittest.main()
