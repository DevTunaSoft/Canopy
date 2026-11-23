"""Wrong-type caller inputs must fail closed in the Mint Qt evidence gate.

Pure-stub regression tests: a PASS here is NOT real Mint guest acceptance.
CI discovers only ``tests/``; run explicitly with
``python -m unittest tools.qa.mint_smoke_type_guard_tests -v``.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import mint_classic_qt_smoke as smoke  # noqa: E402


class MintSmokeTypeGuardTests(unittest.TestCase):
    @staticmethod
    def stub_os_boundary():
        """Bypass only POSIX exec-bit/Qt/PNG I/O; keep all argument validation real."""
        original_safe = smoke.safe_resource

        def stub_safe(path, kind, *, directory=False, executable=False):
            return original_safe(path, kind, directory=directory, executable=False)

        def stub_run_qt(command, timeout, expected):
            return 0, {marker: 1 for marker in expected}, len(expected), False

        def stub_png_size(path):
            label = Path(path).name[3:-4]
            return tuple(map(int, label.split("x")))

        return patch.multiple(
            smoke, safe_resource=stub_safe, _run_qt=stub_run_qt,
            png_size=stub_png_size, file_sha256=lambda path: "d" * 64,
        )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="canopy-mint-type-guard-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "fake-qt"
        self.binary.write_text("stub", encoding="utf-8")
        self.art = self.root / "approved-art"
        self.art.mkdir()
        self.wallpaper = self.root / "alpine.png"
        self.wallpaper.write_bytes(b"stub")
        self.ready = {"status": "READY_FOR_TESTS", "mint_identified": True}
        self.out = self.root / "evidence"

    def call(self, **overrides):
        args = {
            "binary": self.binary,
            "approved_art": self.art,
            "wallpaper": self.wallpaper,
            "output_dir": self.out,
            "source_sha": "a" * 40,
            "preflight": self.ready,
            "timeout_seconds": 10,
            "framing_review": False,
        }
        args.update(overrides)
        return smoke.run_mint_smoke(**args)

    def test_non_bool_framing_review_rejected_before_evidence(self):
        # A truthy string or int is silently coerced by bool() into a report
        # that claims framing was reviewed and demands an extra PASS marker.
        for index, value in enumerate(("false", "true", 1, 0, [], ["review"], {"review": True})):
            with self.subTest(value=repr(value)):
                self.out = self.root / ("framing-" + str(index))
                with self.stub_os_boundary():
                    with self.assertRaises(smoke.MintSmokeError):
                        self.call(framing_review=value)
                self.assertFalse(self.out.exists())

    def test_wrong_type_paths_raise_domain_error_not_raw_type_error(self):
        for field, value in (
            ("binary", b"bytes-path"),
            ("approved_art", object()),
            ("wallpaper", 5),
            ("output_dir", None),
            ("output_dir", 123),
            ("terminal", 123),
        ):
            with self.subTest(field=field, value=repr(value)):
                with self.assertRaises(smoke.MintSmokeError) as caught:
                    self.call(**{field: value})
                self.assertNotIsInstance(caught.exception, TypeError)
                self.assertFalse(self.out.exists())

    def test_bool_framing_review_still_returns_exact_marker_contract(self):
        with self.stub_os_boundary():
            for value, markers in ((False, 3), (True, 4)):
                with self.subTest(framing_review=value):
                    self.out = self.root / ("evidence-" + str(value))
                    report = self.call(framing_review=value)
                    self.assertEqual(report["qt_smoke"], "PASS")
                    self.assertIs(report["framing_review"], value)
                    self.assertEqual(
                        [row["markers_observed"] for row in report["tests"]],
                        [markers] * 3,
                    )

    def test_wrong_type_preflight_still_rejected(self):
        for preflight in ([], "READY_FOR_TESTS", 1,
                          {"status": "READY_FOR_TESTS", "mint_identified": 1}):
            with self.subTest(preflight=repr(preflight)):
                with self.assertRaises(smoke.MintSmokeError):
                    self.call(preflight=preflight)
                self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
