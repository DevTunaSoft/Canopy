"""Offline unit tests for the /proc PSS parser.

No real /proc dependency: proc roots are temporary directories. No polling,
background services, privileged operations, or network access.
"""
from pathlib import Path
import tempfile
import unittest

from canopy_features.performance import pss_samples as pss

# Realistic smaps_rollup shape, including Pss-prefixed totals that must be
# ignored when looking for the single Pss total.
ROLLUP = (
    "Rss:              1652 kB\n"
    "Pss:               900 kB\n"
    "Pss_Dirty:         100 kB\n"
    "Pss_Anon:          700 kB\n"
    "Pss_File:          200 kB\n"
    "Pss_Shmem:           0 kB\n"
    "Shared_Clean:      800 kB\n"
)


class ParsePssKibTests(unittest.TestCase):
    def test_parses_total_and_ignores_pss_prefixed_decoys(self):
        self.assertEqual(pss.parse_pss_kib(ROLLUP), 900)

    def test_accepts_value_without_unit(self):
        self.assertEqual(pss.parse_pss_kib("Pss: 42\n"), 42)

    def test_missing_total_is_not_estimated(self):
        for text in ("Rss: 100 kB\nPss_Dirty: 20 kB\n", "", "Rss: 100 kB\n"):
            with self.subTest(text=text):
                with self.assertRaises(pss.MissingPssError):
                    pss.parse_pss_kib(text)

    def test_malformed_totals_are_rejected_not_guessed(self):
        bad = (
            "Pss: abc kB\n",        # non-numeric
            "Pss: -1 kB\n",         # negative
            "Pss:\n",               # empty
            "Pss: 1.5 kB\n",        # fractional
            "Pss: 12 MB\n",         # wrong unit
            "Pss: 12 kB extra\n",   # extra tokens
            "Pss: +12 kB\n",        # sign
            "Pss: \u0661\u0662 kB\n",  # non-ASCII decimal digits
        )
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(pss.MalformedPssError):
                    pss.parse_pss_kib(text)

    def test_conflicting_duplicate_totals_rejected(self):
        with self.assertRaises(pss.MalformedPssError):
            pss.parse_pss_kib("Pss: 10 kB\nPss: 20 kB\n")

    def test_identical_duplicate_totals_accepted(self):
        self.assertEqual(pss.parse_pss_kib("Pss: 10 kB\nPss: 10 kB\n"), 10)

    def test_non_text_rejected(self):
        for value in (None, b"Pss: 1 kB\n", 123):
            with self.subTest(value=value):
                with self.assertRaises(pss.MalformedPssError):
                    pss.parse_pss_kib(value)


class ReadPssKibTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proc = Path(self.tmp.name)
        self.pid_dir = self.proc / "4242"
        self.pid_dir.mkdir()
        self.file = self.pid_dir / "smaps_rollup"
        self.file.write_text(ROLLUP, encoding="utf-8")

    def test_reads_from_supplied_proc_root(self):
        self.assertEqual(pss.read_pss_kib(4242, proc_root=self.proc), 900)

    def test_disappeared_process_is_explicit(self):
        self.file.unlink()
        self.pid_dir.rmdir()
        with self.assertRaises(pss.ProcessDisappearedError):
            pss.read_pss_kib(4242, proc_root=self.proc)

    def test_missing_rollup_file_is_disappearance(self):
        self.file.unlink()
        with self.assertRaises(pss.ProcessDisappearedError):
            pss.read_pss_kib(4242, proc_root=self.proc)

    def test_malformed_rollup_propagates_malformed_error(self):
        self.file.write_text("Pss: nope kB\n", encoding="utf-8")
        with self.assertRaises(pss.MalformedPssError):
            pss.read_pss_kib(4242, proc_root=self.proc)

    def test_missing_total_in_rollup_propagates_missing_error(self):
        self.file.write_text("Rss: 10 kB\n", encoding="utf-8")
        with self.assertRaises(pss.MissingPssError):
            pss.read_pss_kib(4242, proc_root=self.proc)

    def test_non_numeric_pid_is_caller_error(self):
        with self.assertRaises(ValueError):
            pss.read_pss_kib("not-a-pid", proc_root=self.proc)


class RealProcSmokeTests(unittest.TestCase):
    def test_real_proc_self_if_available(self):
        # Linux hosts expose this; on Windows the test skips. Either way no
        # value is fabricated: parsing a real rollup must yield an int.
        path = Path("/proc/self/smaps_rollup")
        if not path.is_file():
            self.skipTest("/proc/self/smaps_rollup unavailable on this host")
        value = pss.parse_pss_kib(path.read_text(encoding="utf-8"))
        self.assertIsInstance(value, int)
        self.assertGreaterEqual(value, 0)


if __name__ == "__main__":
    unittest.main()
