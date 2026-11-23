"""Oversized decimal values and non-UTF-8 rollups must fail closed as PssError."""
from pathlib import Path
import tempfile
import unittest

from canopy_features.performance import pss_samples as pss


class PssMalformedBoundaryTests(unittest.TestCase):
    def test_huge_decimal_pid_is_malformed_not_a_raw_valueerror(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(pss.MalformedPssError):
                pss.read_pss_kib("9" * 5000, proc_root=td)

    def test_huge_decimal_pss_total_is_malformed_not_a_raw_valueerror(self):
        with self.assertRaises(pss.MalformedPssError):
            pss.parse_pss_kib("Pss: " + "9" * 5000 + " kB")

    def test_non_utf8_rollup_is_malformed_not_a_raw_decode_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proc = root / "4242"
            proc.mkdir()
            (proc / "smaps_rollup").write_bytes(b"Pss: 123 kB\nBad: \xff\xfe\n")
            with self.assertRaises(pss.MalformedPssError):
                pss.read_pss_kib(4242, proc_root=root)

    def test_valid_padded_pid_and_total_are_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proc = root / "42"
            proc.mkdir()
            (proc / "smaps_rollup").write_text("Pss: 1024 kB\n", encoding="utf-8")
            self.assertEqual(pss.read_pss_kib("0042", proc_root=root), 1024)
        self.assertEqual(pss.parse_pss_kib("Pss: 42 kB\n"), 42)


if __name__ == "__main__":
    unittest.main()
