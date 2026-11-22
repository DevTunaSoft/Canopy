"""Offline unit tests for /proc PSS parsing; no real Mint or Qt claimed."""
from pathlib import Path
import tempfile
import unittest

from canopy_features.performance import pss_samples as pss

ROLLUP = """\
00400000-7f0000000000 ---p 00000000 00:00 0                             [rollup]
Rss:                81920 kB
Pss:                12345 kB
Pss_Dirty:              0 kB
Shared_Clean:        1024 kB
"""

ROLLUP_NO_PSS = """\
00400000-7f0000000000 ---p 00000000 00:00 0                             [rollup]
Rss:                81920 kB
Pss_Dirty:              0 kB
"""

SMAPS = """\
00400000-00452000 r-xp 00000000 08:02 173521      /usr/bin/example
Size:                 328 kB
Rss:                   228 kB
Pss:                   200 kB
7f0000000000-7f0000001000 rw-p 00000000 00:00 0
Size:                   4 kB
Rss:                     4 kB
Pss:                     3 kB
"""


class RollupParsingTests(unittest.TestCase):
    def test_measured_total(self):
        result = pss.parse_rollup_pss(ROLLUP)
        self.assertEqual(result.status, pss.OK)
        self.assertEqual(result.pss_kib, 12345)
        self.assertEqual(result.sample_count, 1)
        self.assertTrue(result.is_measured)

    def test_missing_total_is_not_estimated_from_rss(self):
        result = pss.parse_rollup_pss(ROLLUP_NO_PSS)
        self.assertEqual(result.status, pss.MISSING)
        self.assertIsNone(result.pss_kib)
        self.assertFalse(result.is_measured)
        self.assertIn("no Pss", result.reason)

    def test_malformed_totals_never_produce_a_value(self):
        bad_lines = (
            "Pss:",
            "Pss: kB",
            "Pss: -1 kB",
            "Pss: 12.5 kB",
            "Pss: 12",
            "Pss: 12kB",
            "Pss: 12 KB",
            "Pss: 12 MB",
            "Pss: 12 kB extra",
            "Pss: 99999999999999999999 kB",
        )
        for bad in bad_lines:
            with self.subTest(line=bad):
                result = pss.parse_rollup_pss("Rss: 1 kB\n" + bad + "\n")
                self.assertEqual(result.status, pss.MALFORMED)
                self.assertIsNone(result.pss_kib)
                self.assertFalse(result.is_measured)

    def test_duplicate_totals_are_ambiguous(self):
        text = "Pss: 100 kB\nPss: 200 kB\n"
        result = pss.parse_rollup_pss(text)
        self.assertEqual(result.status, pss.CONFLICT)
        self.assertIsNone(result.pss_kib)
        self.assertEqual(result.sample_count, 2)

    def test_non_text_and_oversized_evidence_rejected(self):
        for value in (None, 123, b"Pss: 1 kB\n"):
            with self.subTest(value=type(value).__name__):
                self.assertEqual(pss.parse_rollup_pss(value).status, pss.MALFORMED)
        huge = "Pss: 1 kB\n" + "x" * pss.MAX_SMAPS_BYTES
        self.assertEqual(pss.parse_rollup_pss(huge).status, pss.MALFORMED)


class SmapsParsingTests(unittest.TestCase):
    def test_sums_only_kernel_supplied_values(self):
        result = pss.parse_smaps_pss(SMAPS)
        self.assertEqual(result.status, pss.OK)
        self.assertEqual(result.pss_kib, 203)
        self.assertEqual(result.sample_count, 2)

    def test_one_bad_mapping_value_rejects_the_total(self):
        text = SMAPS.replace("Pss:                   200 kB", "Pss:                   bad kB")
        result = pss.parse_smaps_pss(text)
        self.assertEqual(result.status, pss.MALFORMED)
        self.assertIsNone(result.pss_kib)

    def test_no_mapping_values_is_not_zero(self):
        result = pss.parse_smaps_pss(SMAPS.replace("Pss:", "Xss:"))
        self.assertEqual(result.status, pss.MISSING)
        self.assertIsNone(result.pss_kib)


class SnapshotReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proc_root = Path(self.tmp.name) / "proc"
        self.proc_root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _put(self, pid, name, text):
        folder = self.proc_root / str(pid)
        folder.mkdir(exist_ok=True)
        path = folder / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_reads_synthetic_rollup(self):
        path = self._put(4242, "smaps_rollup", ROLLUP)
        result = pss.read_snapshot(4242, proc_root=str(self.proc_root))
        self.assertEqual(result.status, pss.OK)
        self.assertEqual(result.pss_kib, 12345)
        self.assertEqual(result.source, str(path))

    def test_reads_synthetic_full_smaps_when_requested(self):
        self._put(4242, "smaps_rollup", ROLLUP)
        self._put(4242, "smaps", SMAPS)
        result = pss.read_snapshot("4242", proc_root=str(self.proc_root), rollup=False)
        self.assertEqual(result.status, pss.OK)
        self.assertEqual(result.pss_kib, 203)

    def test_disappeared_process_never_yields_a_value(self):
        for pid in ("9999", 4242):
            with self.subTest(pid=pid):
                result = pss.read_snapshot(pid, proc_root=str(self.proc_root))
                self.assertEqual(result.status, pss.PROCESS_GONE)
                self.assertIsNone(result.pss_kib)
        folder = self.proc_root / "4242"
        folder.mkdir()
        result = pss.read_snapshot(4242, proc_root=str(self.proc_root))
        self.assertEqual(result.status, pss.PROCESS_GONE)
        self.assertIsNone(result.pss_kib)

    def test_missing_proc_root_is_process_gone(self):
        result = pss.read_snapshot(4242, proc_root=str(self.proc_root / "absent"))
        self.assertEqual(result.status, pss.PROCESS_GONE)
        self.assertIsNone(result.pss_kib)

    def test_oversized_and_non_utf8_files_rejected(self):
        self._put(1, "smaps_rollup", "x" * (pss.MAX_SMAPS_BYTES + 1))
        self.assertEqual(
            pss.read_snapshot(1, proc_root=str(self.proc_root)).status, pss.MALFORMED)
        self._put(2, "smaps_rollup", "Pss: 1 kB\n")
        (self.proc_root / "2" / "smaps_rollup").write_bytes(b"Pss: 1 kB\n\xff")
        self.assertEqual(
            pss.read_snapshot(2, proc_root=str(self.proc_root)).status, pss.MALFORMED)

    def test_unreadable_path_is_not_a_process_value(self):
        folder = self.proc_root / "3"
        (folder / "smaps_rollup").mkdir(parents=True)
        result = pss.read_snapshot(3, proc_root=str(self.proc_root))
        self.assertEqual(result.status, pss.UNREADABLE)
        self.assertIsNone(result.pss_kib)

    def test_invalid_pid_rejected(self):
        for pid in (0, -1, True, "abc", "01", 1.5):
            with self.subTest(pid=pid):
                with self.assertRaises(ValueError):
                    pss.read_snapshot(pid, proc_root=str(self.proc_root))


if __name__ == "__main__":
    unittest.main()
