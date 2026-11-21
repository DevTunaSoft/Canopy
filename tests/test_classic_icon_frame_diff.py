"""Stdlib negative controls for the six-scene real-Qt pixel-boundary gate."""
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.check_classic_icon_frame_diff import (
    CENTERS, ComparisonError, compare_pair
)


def png_chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload +
            struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def make_rgba_png(width, height, changes=()):
    stride = width * 4
    pixels = bytearray(bytes((25, 35, 45, 255)) * (width * height))
    for x, y in changes:
        offset = 4 * (y * width + x)
        pixels[offset] = 155
    scanlines = b"".join(
        b"\x00" + pixels[y * stride:(y + 1) * stride]
        for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" +
            png_chunk(b"IHDR", ihdr) +
            png_chunk(b"IDAT", zlib.compress(scanlines)) +
            png_chunk(b"IEND", b""))


class IconFrameDifferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.before = Path(self.temp.name) / "before.png"
        self.after = Path(self.temp.name) / "after.png"
        self.size = "760x500"
        self.before.write_bytes(make_rgba_png(760, 500))

    def simulate(self, changes, scene="desktop"):
        self.after.write_bytes(make_rgba_png(760, 500, changes))
        return compare_pair(self.before, self.after, "760x500", scene)

    def test_all_eight_launcher_icon_edits_pass_without_outside_changes(self):
        report = self.simulate(CENTERS[self.size]["launcher"], "launcher")
        self.assertEqual(report["outside_icon_pixels"], 0)
        self.assertEqual(report["changed_pixels"], 8)
        self.assertEqual(len(report["per_icon_changed_pixels"]), 8)

    def test_closed_desktop_identical_even_when_launcher_review_enabled(self):
        report = self.simulate([], "desktop")
        self.assertEqual(report["changed_pixels"], 0)
        self.assertEqual(report["before_sha256"], report["after_sha256"])

    def test_no_dock_pixel_change_permitted(self):
        with self.assertRaisesRegex(ComparisonError, "frozen dock/desktop pixel changed"):
            self.simulate(CENTERS[self.size]["desktop"], "desktop")

    def test_single_changed_icon_is_not_misreported_as_all_pass(self):
        with self.assertRaisesRegex(ComparisonError, "every icon"):
            self.simulate(CENTERS[self.size]["launcher"][:1], "launcher")

    def test_external_non_icon_pixel_rejected(self):
        altered = CENTERS[self.size]["launcher"] + [(8, 100)]
        with self.assertRaisesRegex(ComparisonError, "outside exactly one"):
            self.simulate(altered, "launcher")

    def test_eight_icon_changes_cannot_pass_with_wrong_scene(self):
        with self.assertRaisesRegex(ComparisonError, "frozen dock/desktop pixel changed"):
            self.simulate(CENTERS[self.size]["launcher"], "desktop")

    def test_invalid_screenshot_dimensions_rejected(self):
        self.after.write_bytes(make_rgba_png(720, 480))
        with self.assertRaisesRegex(ComparisonError, "wrong screenshot dimensions"):
            compare_pair(self.before, self.after, self.size, "desktop")

    def test_crc_tamper_or_truncated_png_rejected(self):
        self.after.write_bytes(make_rgba_png(760, 500, CENTERS[self.size]["desktop"]))
        damaged = bytearray(self.after.read_bytes())
        damaged[25] ^= 0x20
        self.after.write_bytes(damaged)
        with self.assertRaisesRegex(ComparisonError, "invalid RGBA"):
            compare_pair(self.before, self.after, self.size, "desktop")
        self.after.write_bytes(make_rgba_png(760, 500)[:-10])
        with self.assertRaisesRegex(ComparisonError, "invalid RGBA"):
            compare_pair(self.before, self.after, self.size, "desktop")

    def test_symlinked_artifact_rejected_without_following(self):
        original = Path(self.temp.name) / "real-after.png"
        original.write_bytes(make_rgba_png(760, 500))
        self.after.symlink_to(original)
        with self.assertRaisesRegex(ComparisonError, "unsafe"):
            compare_pair(self.before, self.after, self.size, "desktop")

    def test_same_image_never_counts_as_framing_improvement(self):
        self.after.write_bytes(self.before.read_bytes())
        with self.assertRaisesRegex(ComparisonError, "every icon"):
            compare_pair(self.before, self.after, self.size, "launcher")


if __name__ == "__main__":
    unittest.main()
