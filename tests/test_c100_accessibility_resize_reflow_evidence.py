"""Offline unit tests for QML reduced-width layout-contract evidence.

These tests read the real Classic QML source and mutate it in memory to prove
the checker detects overflow, lost clipping and broken compact reflow. No Qt
binary, Mint guest or GUI screenshot is involved; environment flags assert
that explicitly.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from canopy_features.accessibility import resize_reflow_evidence as evidence
from tools.mint_classic_qt_smoke import SIZES


def make_png(path: Path, width: int, height: int) -> None:
    """Write a small solid-colour RGBA PNG accepted by the shared validator."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

    raw_row = b"\x00" + b"\x80\x90\xa0\xff" * width
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw_row * height))
        + chunk(b"IEND", b"")
    )


class ResizeReflowEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.sources = evidence.load_sources()

    def check(self, *, sources=None, **kwargs):
        return evidence.check_layout_contract(
            sources=self.sources if sources is None else sources, **kwargs
        )

    def test_reduced_size_reuses_existing_smoke_sizes(self):
        self.assertEqual(evidence.REDUCED_SIZE, (760, 500))
        self.assertIn(evidence.REDUCED_SIZE, SIZES)
        report = self.check()
        self.assertTrue(report["reduced_size_from_smoke_sizes"])
        self.assertEqual(report["size"], "760x500")

    def test_real_source_passes_at_760x500(self):
        report = self.check()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["failed"], [])
        self.assertTrue(all(report["contracts"].values()))
        geometry = report["geometry"]
        self.assertEqual(geometry["minimum_width"], 720)
        self.assertEqual(geometry["minimum_height"], 480)
        self.assertEqual(geometry["compact_threshold"], 900)
        preview = geometry["preview"]
        self.assertEqual((preview["width"], preview["height"]), (688.0, 302.0))
        self.assertLessEqual(preview["right"], report["width"])
        self.assertLessEqual(preview["bottom"], report["height"])
        self.assertLessEqual(geometry["dock_width"], report["width"])

    def test_environment_flags_do_not_claim_real_qt_or_mint(self):
        report = self.check()
        env = report["environment"]
        self.assertEqual(env["mode"], "offline-source-contract")
        self.assertFalse(env["compiled_qt_ran"])
        self.assertFalse(env["linux_mint_ran"])
        self.assertTrue(env["host_os"])
        self.assertIn("No Qt binary", env["limitations"])

    def test_overflow_is_detected_at_760x500(self):
        sources = dict(self.sources)
        sources["main"] = self.sources["main"].replace(
            "width: Math.min(root.width - 72, Math.max(780, root.width * 0.56))",
            "width: root.width + 120",
            1,
        )
        self.assertNotEqual(sources["main"], self.sources["main"])
        report = self.check(sources=sources)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["contracts"]["preview_within_viewport"])
        self.assertIn("preview_within_viewport", report["failed"])
        self.assertGreater(report["geometry"]["preview"]["right"], report["width"])

    def test_clipped_content_contract_fails_when_clip_removed(self):
        sources = dict(self.sources)
        sources["preview"] = self.sources["preview"].replace("clip: true", "clip: false")
        report = self.check(sources=sources)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["contracts"]["preview_clips_content"])
        self.assertFalse(report["contracts"]["scrollers_clip_content"])
        self.assertIn("preview_clips_content", report["failed"])
        self.assertIn("scrollers_clip_content", report["failed"])

    def test_window_below_minimum_is_flagged(self):
        report = self.check(size=(700, 470))
        self.assertFalse(report["contracts"]["above_minimum"])
        self.assertIn("above_minimum", report["failed"])
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["reduced_size_from_smoke_sizes"])

    def test_compact_reflow_contract_fails_when_threshold_drops(self):
        sources = dict(self.sources)
        sources["main"] = self.sources["main"].replace(
            "width < 900", "width < 600", 1
        )
        report = self.check(sources=sources)
        self.assertFalse(report["contracts"]["compact_layout_engages"])
        self.assertEqual(report["status"], "FAIL")

    def test_expression_evaluator_rejects_code_and_supports_qml_math(self):
        self.assertEqual(
            evidence.evaluate("Math.max(24, Math.min(680, root.width - 72))",
                              {"root.width": 760}),
            680,
        )
        with self.assertRaises(ValueError):
            evidence.evaluate("__import__('os')", {})
        with self.assertRaises(ValueError):
            evidence.evaluate("root.width + destructive_call()", {"root.width": 760})

    def test_screenshot_validation_is_reused_without_duplication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qt-760x500.png"
            make_png(path, 760, 500)
            result = evidence.screenshot_evidence(path, (760, 500))
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(result["sha256"], expected)
            self.assertEqual(result["size"], [760, 500])
            self.assertEqual(result["name"], "qt-760x500.png")
            path.write_bytes(b"not a png")
            with self.assertRaises(ValueError):
                evidence.screenshot_evidence(path, (760, 500))

    def test_cli_prints_report_and_returns_zero_on_real_source(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = evidence.main([])
        report = json.loads(stream.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["size"], "760x500")


if __name__ == "__main__":
    unittest.main()
