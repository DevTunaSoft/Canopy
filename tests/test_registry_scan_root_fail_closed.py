"""Fail-closed regression tests for hostile Shell Pack catalog root values.

The registry's public scan boundary must translate hostile-but-bounded root
values into the module's domain error. A raw ``TypeError`` from ``Path()`` is
not a fail-closed registry result: callers cannot distinguish it from a
programming error and the CLI's ``PackValidationError`` gate is bypassed.
"""

import tempfile
import unittest
from pathlib import Path

from canopy_core.registry import scan_shell_packs
from tools.check_shell_pack import PackValidationError


class RegistryScanRootTypeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "packs"
        self.root.mkdir()

    def test_hostile_root_types_raise_domain_error_not_raw_typeerror(self):
        for hostile in (None, 7, 1.5, b"packs", ["packs"], {"path": "packs"}):
            with self.subTest(hostile=hostile):
                with self.assertRaises(PackValidationError):
                    scan_shell_packs(hostile)

    def test_real_directory_root_still_scans(self):
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertEqual(report.problems, ())
        self.assertEqual(report.checked_directories, 0)


if __name__ == "__main__":
    unittest.main()
