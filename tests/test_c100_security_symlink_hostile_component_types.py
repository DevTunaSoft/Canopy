"""Regression tests for hostile-but-bounded path component inputs.

The symlink defense documents UnsafePathError as its domain error for unsafe
paths. These tests pin the contract for wrong-typed and hostile os.PathLike
inputs across every public entry point, including the deferred body of the
``verified_directory`` context manager.
"""
import os
import tempfile
from pathlib import Path
import unittest

from canopy_features.security import symlink_component_defense as defense


class HostilePathLike:
    """Minimal PathLike whose fspath fails with a hostile ValueError."""

    def __fspath__(self):
        raise ValueError("hostile fspath implementation")


class FspathFailure:
    """PathLike whose fspath fails with an arbitrary hostile exception."""

    def __init__(self, error):
        self.error = error

    def __fspath__(self):
        raise self.error


class WrongPathTypeContractTests(unittest.TestCase):
    BAD_PATHS = (None, 123, 1.5, [], {}, bytearray(b"/tmp"), HostilePathLike())

    def test_find_symlink_component_wrong_types_use_domain_error(self):
        for bad in self.BAD_PATHS:
            with self.subTest(path_type=type(bad).__name__):
                with self.assertRaises(defense.UnsafePathError):
                    defense.find_symlink_component(bad)

    def test_reject_symlink_components_wrong_types_use_domain_error(self):
        for bad in self.BAD_PATHS:
            with self.subTest(path_type=type(bad).__name__):
                with self.assertRaises(defense.UnsafePathError):
                    defense.reject_symlink_components(bad)

    def test_verified_directory_wrong_types_use_domain_error(self):
        for bad in self.BAD_PATHS:
            with self.subTest(path_type=type(bad).__name__):
                with self.assertRaises(defense.UnsafePathError):
                    with defense.verified_directory(bad):
                        pass

    def test_hostile_fspath_failures_use_domain_error_everywhere(self):
        for error in (OSError("hostile fspath I/O failure"),
                      RuntimeError("hostile fspath runtime failure")):
            bad = FspathFailure(error)
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(defense.UnsafePathError):
                    defense.find_symlink_component(bad)
                with self.assertRaises(defense.UnsafePathError):
                    defense.reject_symlink_components(bad)
                with self.assertRaises(defense.UnsafePathError):
                    with defense.verified_directory(bad):
                        pass

    def test_valid_path_still_accepted_after_type_guard(self):
        with tempfile.TemporaryDirectory() as td:
            clean = Path(td) / "child" / "leaf"
            clean.mkdir(parents=True)
            self.assertIsNone(defense.find_symlink_component(clean))
            self.assertEqual(str(defense.reject_symlink_components(clean)),
                             os.path.abspath(str(clean)))
            with defense.verified_directory(clean) as (_, path):
                self.assertEqual(str(path), os.path.abspath(str(clean)))


if __name__ == "__main__":
    unittest.main()
