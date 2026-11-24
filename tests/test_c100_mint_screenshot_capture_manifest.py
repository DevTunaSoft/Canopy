"""Offline tests for reproducible screenshot capture evidence manifests.

Synthetic PNG fixtures are files on disk, not fabricated evidence. A green
unit test is NOT proof of a real Mint capture or a working Qt desktop.
"""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from canopy_features.mint import screenshot_capture_manifest as manifest


def _chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))


def _png(width=8, height=8):
    """Build a valid nonuniform RGBA PNG accepted by mint_classic_qt_smoke."""
    rows = []
    for y in range(height):
        row = bytearray([0])  # filter type 0
        for x in range(width):
            row.extend((32 + x % 2 + y % 2, 40, 52, 255))
        rows.append(bytes(row))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(b"".join(rows)))
            + _chunk(b"IEND", b""))


class ScreenshotCaptureManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.captures = []
        for name in ("qt-1920x1080.png", "qt-1200x750.png", "qt-760x500.png"):
            path = self.root / name
            path.write_bytes(_png())
            self.captures.append(path)

    def test_reproducible_across_input_order_and_writes(self):
        first = manifest.build_manifest(self.captures)
        second = manifest.build_manifest(list(reversed(self.captures)))
        self.assertEqual(first, second)
        self.assertEqual(manifest.serialize(first), manifest.serialize(second))
        self.assertEqual([e["path"] for e in first["entries"]],
                         ["qt-1200x750.png", "qt-1920x1080.png", "qt-760x500.png"])
        self.assertEqual(first["capture_count"], 3)
        self.assertIsNone(first["binary_sha256"])
        for entry in first["entries"]:
            self.assertEqual(set(entry),
                             {"path", "sha256", "size_bytes", "width", "height"})
            self.assertEqual((entry["width"], entry["height"]), (8, 8))
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
        payload = {k: v for k, v in first.items() if k != "manifest_sha256"}
        self.assertEqual(
            first["manifest_sha256"],
            hashlib.sha256(manifest.serialize(payload)).hexdigest(),
        )
        one = manifest.write_manifest(self.root / "one.json", first)
        two = manifest.write_manifest(self.root / "two.json", second)
        self.assertEqual(one.read_bytes(), two.read_bytes())

    def test_manifest_leaks_no_absolute_paths_or_timestamps(self):
        result = manifest.build_manifest(self.captures)
        raw = manifest.serialize(result).decode("ascii")
        self.assertNotIn(self.root.name, raw)
        self.assertNotIn("timestamp", raw)
        self.assertNotIn("captured_at", raw)

    def test_hash_mismatch_fails_closed(self):
        with self.assertRaisesRegex(manifest.ManifestError, "SHA-256 mismatch"):
            manifest.build_manifest(
                [self.captures[0]],
                expected_sha256={self.captures[0].name: "0" * 64},
            )

    def test_matching_expected_hash_is_accepted(self):
        digest = hashlib.sha256(self.captures[0].read_bytes()).hexdigest()
        result = manifest.build_manifest(
            [self.captures[0]],
            expected_sha256={self.captures[0].name: digest},
        )
        self.assertEqual(result["entries"][0]["sha256"], digest)

    def test_expected_hash_for_unknown_capture_fails(self):
        with self.assertRaisesRegex(manifest.ManifestError, "unknown capture"):
            manifest.build_manifest(
                [self.captures[0]],
                expected_sha256={"not-a-capture.png": "a" * 64},
            )

    def test_absent_binary_fails_closed(self):
        with self.assertRaisesRegex(manifest.ManifestError, "binary missing"):
            manifest.build_manifest(
                [self.captures[0]], binary=self.root / "no-such-binary",
            )

    def test_present_binary_records_its_sha256(self):
        binary = self.root / "classic-qt"
        binary.write_bytes(b"compiled binary bytes")
        result = manifest.build_manifest([self.captures[0]], binary=binary)
        self.assertEqual(
            result["binary_sha256"],
            hashlib.sha256(binary.read_bytes()).hexdigest(),
        )

    def test_corrupt_png_is_rejected(self):
        damaged = self.root / "damaged.png"
        bits = bytearray(_png())
        bits[-1] ^= 1  # break IEND CRC
        damaged.write_bytes(bits)
        with self.assertRaisesRegex(manifest.ManifestError, "corrupt or unreadable PNG"):
            manifest.build_manifest([damaged])

    def test_missing_capture_is_rejected(self):
        with self.assertRaisesRegex(manifest.ManifestError, "capture missing or unsafe"):
            manifest.build_manifest([self.root / "gone.png"])

    def test_non_png_file_is_rejected(self):
        text = self.root / "report.json"
        text.write_text('{"qt_smoke": "PASS"}', encoding="utf-8")
        with self.assertRaisesRegex(manifest.ManifestError, "corrupt or unreadable PNG"):
            manifest.build_manifest([text])

    def test_duplicate_capture_names_are_rejected(self):
        folder = self.root / "second"
        folder.mkdir()
        duplicate = folder / self.captures[0].name
        duplicate.write_bytes(_png())
        with self.assertRaisesRegex(manifest.ManifestError, "duplicate"):
            manifest.build_manifest([self.captures[0], duplicate])

    def test_symlinked_capture_is_rejected(self):
        link = self.root / "linked.png"
        try:
            link.symlink_to(self.captures[0])
        except OSError as exc:
            self.skipTest("symlinks unavailable on this host: " + str(exc))
        with self.assertRaisesRegex(manifest.ManifestError, "capture missing or unsafe"):
            manifest.build_manifest([link])

    def test_empty_capture_set_is_rejected(self):
        with self.assertRaisesRegex(manifest.ManifestError, "capture count"):
            manifest.build_manifest([])

    def test_write_manifest_never_overwrites(self):
        target = manifest.write_manifest(self.root / "fixed.json",
                                         manifest.build_manifest([self.captures[0]]))
        original = target.read_bytes()
        with self.assertRaises(FileExistsError):
            manifest.write_manifest(target, manifest.build_manifest(self.captures))
        self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
