"""Process-id inputs to the PSS reader must fail closed at the boundary."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from canopy_features.performance.pss_samples import (
    MalformedPssError, MissingPssError, ProcessDisappearedError, read_pss_kib)


class PssPidBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        proc = self.root / "42"
        proc.mkdir()
        (proc / "smaps_rollup").write_text("Pss:  1024 kB\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_non_iterable_or_wrong_type_pids_rejected(self):
        for bad in (None, [], {}, 1.5, object()):
            with self.subTest(value=type(bad).__name__), self.assertRaises(MalformedPssError):
                read_pss_kib(bad, proc_root=self.root)

    def test_bool_is_not_a_pid(self):
        with self.assertRaises(MalformedPssError):
            read_pss_kib(True, proc_root=self.root)

    def test_non_decimal_and_nonpositive_pids_rejected(self):
        for bad in ("abc", "", "-1", "0", "1 2"):
            with self.subTest(value=bad), self.assertRaises(MalformedPssError):
                read_pss_kib(bad, proc_root=self.root)

    def test_valid_int_and_padded_decimal_string_match(self):
        self.assertEqual(read_pss_kib(42, proc_root=self.root), 1024)
        self.assertEqual(read_pss_kib("0042", proc_root=self.root), 1024)

    def test_vanished_pid_keeps_its_domain_error(self):
        with self.assertRaises(ProcessDisappearedError):
            read_pss_kib(777, proc_root=self.root)

    def test_missing_pss_still_reports_missing(self):
        proc = self.root / "43"
        proc.mkdir()
        (proc / "smaps_rollup").write_text("Rss: 10 kB\n", encoding="utf-8")
        with self.assertRaises(MissingPssError):
            read_pss_kib(43, proc_root=self.root)


if __name__ == "__main__":
    unittest.main()
