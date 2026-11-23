"""Offline tests for the screenshot evidence manifest builder.

These tests use synthetic PNG bytes only to exercise validation logic. They
do NOT capture a screen, run compiled Qt, or validate a Linux Mint desktop.
"""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from canopy_features.mint import screenshot_capture_manifest as scm


def _chunk(kind, data):
    return (
        struct.pack(">I", len(data)) + kind + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    )


def _make_png(width=4, height=4):
    """Small, structurally valid, nonuniform RGBA PNG."""
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend((
                (x * 37 + y * 11 + 1) % 256,
                (y * 53 + x * 7 + 2) % 256,
                (x * 13 + y * 29 + 3) % 256,
                255,
            ))
        rows.append(bytes(row))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + _chunk(b"IEND", b"")
    )


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


class ScreenshotCaptureManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.png_data = _make_png()
        self.capture = self.root / "qt-4x4.png"
        self.capture.write_bytes(self.png_data)
        self.binary = self.root / "canopy-classic-spike"
        self.binary.write_bytes(b"compiled binary stand-in")
        self.source_sha = "a" * 40
        self.spec = {
            "name": "qt-4x4.png",
            "path": str(self.capture),
            "sha256": _sha256(self.png_data),
        }

    def build(self, **kwargs):
        return scm.build_manifest(
            captures=kwargs.get("captures", [self.spec]),
            binary=kwargs.get("binary", self.binary),
            source_sha=kwargs.get("source_sha", self.source_sha),
        )

    def test_manifest_uses_only_real_existing_capture(self):
        report = self.build()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["source_sha"], self.source_sha)
        self.assertEqual(report["binary_sha256"], _sha256(b"compiled binary stand-in"))
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["captures"], [{
            "name": "qt-4x4.png",
            "sha256": self.spec["sha256"],
            "width": 4,
            "height": 4,
            "bytes": len(self.png_data),
            "status": "PASS",
        }])

    def test_hash_mismatch_is_never_listed_as_a_capture(self):
        spec = dict(self.spec, sha256="0" * 64)
        report = self.build(captures=[spec])
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["captures"], [])
        self.assertEqual(
            report["failures"],
            [{"name": "qt-4x4.png", "reason": "HASH_MISMATCH"}],
        )

    def test_absent_binary_blocks_the_manifest(self):
        missing = self.root / "not-built"
        with self.assertRaisesRegex(scm.ManifestError, "ABSENT_BINARY"):
            self.build(binary=missing)

    def test_corrupt_png_is_rejected_even_with_matching_hash(self):
        corrupt = self.png_data[:-12]
        self.capture.write_bytes(corrupt)
        spec = dict(self.spec, sha256=_sha256(corrupt))
        report = self.build(captures=[spec])
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["captures"], [])
        self.assertEqual(
            report["failures"],
            [{"name": "qt-4x4.png", "reason": "INVALID_PNG"}],
        )

    def test_missing_capture_is_not_fabricated(self):
        absent = self.root / "never-captured.png"
        spec = dict(self.spec, name="never-captured.png", path=str(absent))
        report = self.build(captures=[spec])
        self.assertEqual(
            report["failures"],
            [{"name": "never-captured.png", "reason": "MISSING_CAPTURE"}],
        )
        self.assertFalse(absent.exists())

    def test_declared_dimensions_must_match_measured_png(self):
        spec = dict(self.spec, width=5)
        report = self.build(captures=[spec])
        self.assertEqual(
            report["failures"],
            [{"name": "qt-4x4.png", "reason": "DIMENSION_MISMATCH"}],
        )

    def test_symlinked_capture_is_not_trusted(self):
        linked = self.root / "linked.png"
        linked.symlink_to(self.capture)
        spec = dict(self.spec, name="linked.png", path=str(linked))
        report = self.build(captures=[spec])
        self.assertEqual(
            report["failures"],
            [{"name": "linked.png", "reason": "UNSAFE_CAPTURE"}],
        )

    def test_output_is_deterministic_and_path_free(self):
        first = scm.render_manifest(self.build())
        second = scm.render_manifest(self.build())
        self.assertEqual(first, second)
        self.assertNotIn(str(self.root), first)
        self.assertNotIn(str(self.binary), first)
        self.assertTrue(first.endswith("\n"))

    def test_duplicate_names_are_rejected(self):
        with self.assertRaisesRegex(scm.ManifestError, "DUPLICATE_NAME"):
            self.build(captures=[self.spec, dict(self.spec, path=str(self.capture))])

    def test_invalid_source_sha_is_rejected(self):
        with self.assertRaisesRegex(scm.ManifestError, "BAD_SOURCE_SHA"):
            self.build(source_sha="unverified")

    def test_capture_count_is_bounded(self):
        with self.assertRaisesRegex(scm.ManifestError, "TOO_MANY_CAPTURES"):
            self.build(captures=[self.spec] * (scm.MAX_CAPTURES + 1))

    def test_oversized_capture_is_rejected_before_reading(self):
        with patch.object(scm, "PNG_MAX_FILE_SIZE", 10):
            report = self.build()
        self.assertEqual(
            report["failures"],
            [{"name": "qt-4x4.png", "reason": "INVALID_PNG"}],
        )

    def test_malformed_spec_is_reported_not_crashed(self):
        report = self.build(captures=["not a mapping"])
        self.assertEqual(
            report["failures"],
            [{"name": "<invalid>", "reason": "BAD_SPEC"}],
        )
        self.assertEqual(report["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
