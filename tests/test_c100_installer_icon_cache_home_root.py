"""Regression: an ambiguous POSIX root home must fail closed, not crash.

``PurePosixPath('//')`` has a single part (the implementation-defined
double-slash root), so ``_home_path`` previously indexed ``parts[1]`` and
leaked ``IndexError`` out of the public ``describe_refresh`` entry point.
The documented boundary is ``IconCacheDescriptionError`` for an invalid,
unsafe or ambiguous home directory.
"""
from pathlib import PurePosixPath
import unittest

from canopy_features.installer import icon_cache_optin as ic


HOME = "/home/alice"
THEME = HOME + "/.local/share/icons/Hicolor"


def lookup(found):
    """Injectable PATH stand-in; never runs a tool."""
    return lambda name: found


class IconCacheHomeRootTests(unittest.TestCase):
    def test_double_slash_root_refused_via_public_api(self):
        """The ambiguous '//' root must raise the domain error, never IndexError."""
        with self.assertRaises(ic.IconCacheDescriptionError) as caught:
            ic.describe_refresh("//", (THEME,), tool_lookup=lookup(ic.CACHE_TOOL))
        self.assertIn("home", str(caught.exception).lower())

    def test_double_slash_root_as_path_refused_via_public_api(self):
        with self.assertRaises(ic.IconCacheDescriptionError):
            ic.describe_refresh(
                PurePosixPath("//"), (PurePosixPath(THEME),),
                tool_lookup=lookup(ic.CACHE_TOOL),
            )

    def test_home_path_boundary_rejects_single_part_roots(self):
        for bad in ("//", "///"):
            with self.subTest(bad=bad), self.assertRaises(ic.IconCacheDescriptionError):
                ic._home_path(bad)

    def test_valid_and_system_homes_unchanged(self):
        """Controls: a real user home is accepted and system/root homes refused."""
        result = ic.describe_refresh(
            HOME, (THEME,), tool_lookup=lookup(ic.CACHE_TOOL),
        )
        self.assertTrue(result.available)
        self.assertEqual(result.directories, (THEME,))
        for bad in ("/", "/usr/local/home"):
            with self.subTest(bad=bad), self.assertRaises(ic.IconCacheDescriptionError):
                ic.describe_refresh(bad, (THEME,), tool_lookup=lookup(ic.CACHE_TOOL))


if __name__ == "__main__":
    unittest.main()
