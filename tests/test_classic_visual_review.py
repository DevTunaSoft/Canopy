"""Synthetic screenshot fixtures test review-gallery integrity, not real Qt visuals."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.classic_visual_review import ReviewError, make_gallery


def png(width, height):
    def chunk(kind, blob):
        return (struct.pack(">I", len(blob)) + kind + blob
                + struct.pack(">I", zlib.crc32(kind + blob) & 0xffffffff))
    raw = (bytes([0]) + bytes([30, 50, 70, 255]) * width) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class VisualReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = self.root / "baseline"
        self.candidate = self.root / "candidate"
        self.output = self.root / "gallery"
        for directory, framed in ((self.baseline, False), (self.candidate, True)):
            directory.mkdir()
            rows = []
            for width, height in ((1920, 1080), (1200, 750), (760, 500)):
                name = f"qt-{width}x{height}.png"
                data = png(width, height)
                (directory / name).write_bytes(data)
                rows.append({"resolution": f"{width}x{height}", "status": "PASS",
                             "exit_code": 0, "screenshot": name,
                             "screenshot_sha256": hashlib.sha256(data).hexdigest()})
            report = {"schema_version": 1, "environment": "linuxmint", "qt_smoke": "PASS",
                      "framing_review": framed, "declared_source_sha": "a" * 40,
                      "verified_binary_sha256": "b" * 64, "tests": rows}
            (directory / "report.json").write_text(json.dumps(report))

    def change(self, directory, callback):
        path = directory / "report.json"
        report = json.loads(path.read_text())
        callback(report)
        path.write_text(json.dumps(report))

    def test_creates_private_byte_exact_gallery(self):
        manifest = make_gallery(self.baseline, self.candidate, self.output)
        self.assertTrue(manifest["images_copied_unchanged"])
        self.assertEqual(manifest["visual_owner_approval"], "NOT_RUN")
        self.assertFalse(manifest["actual_mint_session_independently_verified"])
        html = (self.output / "index.html").read_text()
        self.assertIn("NOT visually approved", html)
        self.assertIn("1920 × 1080", html)
        self.assertNotIn(str(self.root), html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        for side, original in (("before", self.baseline), ("after", self.candidate)):
            for name in ("qt-1920x1080.png", "qt-1200x750.png", "qt-760x500.png"):
                self.assertEqual((self.output / side / name).read_bytes(), (original / name).read_bytes())
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)

    def test_tampered_pixels_fail_before_creating_output(self):
        (self.candidate / "qt-760x500.png").write_bytes(b"tampered")
        with self.assertRaises(ReviewError):
            make_gallery(self.baseline, self.candidate, self.output)
        self.assertFalse(self.output.exists())

    def test_wrong_source_hash_rejected(self):
        self.change(self.candidate, lambda r: r.update(declared_source_sha="c" * 40))
        with self.assertRaisesRegex(ReviewError, "identical source"):
            make_gallery(self.baseline, self.candidate, self.output)

    def test_different_binary_rejected(self):
        self.change(self.candidate, lambda r: r.update(verified_binary_sha256="c" * 64))
        with self.assertRaisesRegex(ReviewError, "identical source"):
            make_gallery(self.baseline, self.candidate, self.output)

    def test_non_pass_capture_rejected(self):
        self.change(self.candidate, lambda r: r["tests"][0].update(status="FAIL"))
        with self.assertRaisesRegex(ReviewError, "incomplete"):
            make_gallery(self.baseline, self.candidate, self.output)

    def test_rejects_swapped_framing_flags(self):
        self.change(self.baseline, lambda r: r.update(framing_review=True))
        with self.assertRaisesRegex(ReviewError, "matching PASS"):
            make_gallery(self.baseline, self.candidate, self.output)

    def test_rejects_report_controlled_path(self):
        self.change(self.candidate, lambda r: r["tests"][0].update(screenshot="../../private.png"))
        with self.assertRaisesRegex(ReviewError, "incomplete"):
            make_gallery(self.baseline, self.candidate, self.output)

    def test_existing_output_preserved(self):
        self.output.mkdir()
        (self.output / "keep.txt").write_text("original")
        with self.assertRaisesRegex(ReviewError, "new absolute"):
            make_gallery(self.baseline, self.candidate, self.output)
        self.assertEqual((self.output / "keep.txt").read_text(), "original")

    def test_symlinked_screenshot_rejected(self):
        path = self.baseline / "qt-760x500.png"
        real = self.root / "real.png"
        path.rename(real)
        path.symlink_to(real)
        with self.assertRaisesRegex(ReviewError, "linked"):
            make_gallery(self.baseline, self.candidate, self.output)

    def test_corrupted_png_crc_rejected(self):
        path = self.baseline / "qt-760x500.png"
        content = bytearray(path.read_bytes())
        content[50] ^= 1
        path.write_bytes(content)
        with self.assertRaises(ReviewError):
            make_gallery(self.baseline, self.candidate, self.output)


if __name__ == "__main__":
    unittest.main()
