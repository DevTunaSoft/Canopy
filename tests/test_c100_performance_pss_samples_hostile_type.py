"""Wrong-type values at the PSS parser boundary must fail closed.

Hostile-but-bounded inputs may reach the public entry points of
``pss_samples``. They must surface as the module's own MalformedPssError,
never as a raw built-in exception and never as a valid-looking PSS sample.
"""
import tempfile
import unittest
from pathlib import Path

from canopy_features.performance import pss_samples as pss


class _HostileText(str):
    """Bounded str subclass whose splitter yields wrong-type lines."""

    def splitlines(self, keepends=False):
        return ["Pss: 10 kB", None]


class _HostileTextFalseSafe(str):
    """Bounded str subclass that could manufacture a false safe sample."""

    def splitlines(self, keepends=False):
        return ["Pss: 10 kB", []]


class _BytesPathLike:
    def __fspath__(self):
        return b"/proc"


class HostileTypeBoundaryTests(unittest.TestCase):
    def test_hostile_text_line_type_is_not_a_raw_exception(self):
        with self.assertRaises(pss.MalformedPssError):
            pss.parse_pss_kib(_HostileText("Pss: 10 kB\n"))

    def test_hostile_text_line_type_cannot_fabricate_safe_sample(self):
        with self.assertRaises(pss.MalformedPssError):
            pss.parse_pss_kib(_HostileTextFalseSafe("Pss: 10 kB\n"))

    def test_wrong_type_proc_root_fails_closed(self):
        for bad in (None, [], {}, 1.5, object(), b"/proc"):
            with self.subTest(value=type(bad).__name__):
                with self.assertRaises(pss.MalformedPssError):
                    pss.read_pss_kib(42, proc_root=bad)

    def test_pathlike_proc_root_returning_bytes_fails_closed(self):
        with self.assertRaises(pss.MalformedPssError):
            pss.read_pss_kib(42, proc_root=_BytesPathLike())

    def test_ordinary_text_and_path_proc_root_still_work(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proc = root / "42"
            proc.mkdir()
            (proc / "smaps_rollup").write_text("Pss: 900 kB\n", encoding="utf-8")
            self.assertEqual(
                pss.read_pss_kib(42, proc_root=str(root)), 900)
            self.assertEqual(pss.read_pss_kib(42, proc_root=root), 900)
        self.assertEqual(pss.parse_pss_kib("Pss: 42 kB\n"), 42)


if __name__ == "__main__":
    unittest.main()
