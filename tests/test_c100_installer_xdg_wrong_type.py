"""Regression tests: wrong-type caller input to XDG path validators fails closed.

Both public boundaries document :class:`UnsafeXdgPath` as their error type.
An unhashable ``kind`` (base_dir) or a non-path ``target`` (validate) must not
leak a built-in ``TypeError`` past that boundary.
"""
import os
from pathlib import Path
import tempfile
import unittest

from canopy_features.installer import xdg_user_paths as xp


class XdgWrongTypeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.empty_env = {}

    def test_base_dir_unhashable_kind_uses_domain_error(self):
        # Base leaks TypeError: cannot use 'list'/'dict' as a dict key.
        for kind in (["data"], {"data": 1}, ["config"], {}):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(xp.UnsafeXdgPath, "unknown XDG base kind"):
                    xp.base_dir(kind, home=self.home, env=self.empty_env)

    def test_base_dir_hashable_non_string_kind_uses_domain_error(self):
        for kind in (None, 5, 3.5, ("data",)):
            with self.subTest(kind=kind):
                with self.assertRaises(xp.UnsafeXdgPath):
                    xp.base_dir(kind, home=self.home, env=self.empty_env)

    def test_validate_non_path_target_uses_domain_error(self):
        # Base leaks TypeError from pathlib.Path(...) for each of these.
        for target in (5, True, False, ["/x"], {"a": 1}, 3.5):
            with self.subTest(target=target):
                with self.assertRaisesRegex(xp.UnsafeXdgPath, "target must be a path"):
                    xp.validate(target, home=self.home)

    def test_validate_none_and_bytes_still_use_domain_error(self):
        # Controls: these were already handled before the fix.
        for target in (None, b"/x"):
            with self.subTest(target=target):
                with self.assertRaisesRegex(xp.UnsafeXdgPath, "target must be a path"):
                    xp.validate(target, home=self.home)

    def test_valid_string_and_path_targets_still_accepted(self):
        candidate = self.home / ".config" / "canopy"
        self.assertEqual(xp.validate(str(candidate), home=self.home), candidate)
        self.assertEqual(xp.validate(candidate, home=self.home), candidate)

    def test_valid_base_kinds_still_accepted(self):
        for kind, expected in {
            "data": self.home / ".local" / "share",
            "config": self.home / ".config",
            "cache": self.home / ".cache",
            "state": self.home / ".local" / "state",
        }.items():
            with self.subTest(kind=kind):
                self.assertEqual(
                    xp.base_dir(kind, home=self.home, env=self.empty_env), expected
                )


if __name__ == "__main__":
    unittest.main()
