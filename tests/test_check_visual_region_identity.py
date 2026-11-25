"""Tests for the byte-exact visual-region identity checker."""
from __future__ import annotations

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools.check_visual_region_identity import compare_regions, decode_png

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def write_png(path: Path, width: int, height: int, channels: int,
              values=None) -> None:
    """Write a small filter-0 PNG (RGB when channels=3, RGBA when channels=4)."""
    colour = {3: 2, 4: 6}[channels]
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            base = values(x, y) if values else (x * 17 + y * 31) % 256
            for c in range(channels):
                row.append((base + c * 29) % 256)
        rows.append(b"\x00" + bytes(row))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + kind + payload +
                struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, 0)
    path.write_bytes(SIGNATURE + chunk(b"IHDR", ihdr) +
                     chunk(b"IDAT", zlib.compress(b"".join(rows))) +
                     chunk(b"IEND", b""))


class VisualRegionIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "base.png"
        self.feature = self.root / "feature.png"
        write_png(self.base, 8, 6, 3)
        write_png(self.feature, 8, 6, 3)

    def test_identical_captures_pass_every_region(self):
        result = compare_regions(decode_png(self.base), decode_png(self.feature),
                                 [(0, 0, 8, 6), (0, 0, 8, 2), (0, 2, 8, 4)])
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["size"], [8, 6])
        self.assertTrue(all(r["identical"] and r["differing_pixels"] == 0
                            for r in result["regions"]))

    def test_single_pixel_delta_is_detected(self):
        # Mutate exactly one pixel's colour triple; every other pixel stays equal.
        write_png(self.feature, 8, 6, 3,
                  lambda x, y: ((x * 17 + y * 31) % 256) ^ (0xFF if (x, y) == (4, 1) else 0))
        result = compare_regions(decode_png(self.base), decode_png(self.feature),
                                 [(0, 0, 8, 6), (0, 0, 8, 1)])
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["regions"][0]["differing_pixels"], 1)
        self.assertTrue(result["regions"][1]["identical"])

    def test_alpha_delta_is_detected(self):
        rgba_base = self.root / "rgba-base.png"
        rgba_feature = self.root / "rgba-feature.png"
        write_png(rgba_base, 8, 6, 4)
        write_png(rgba_feature, 8, 6, 4,
                  lambda x, y: (x * 17 + y * 31) % 256 if (x, y) != (0, 0) else 99)
        result = compare_regions(decode_png(rgba_base), decode_png(rgba_feature),
                                 [(0, 0, 8, 6)])
        self.assertEqual(result["verdict"], "FAIL")
        self.assertEqual(result["regions"][0]["differing_pixels"], 1)
        self.assertEqual(result["channels"], 4)

    def test_out_of_bounds_region_blocked(self):
        image = decode_png(self.base)
        with self.assertRaises(ValueError):
            image.region_bytes(7, 5, 2, 1)

    def test_dimension_mismatch_blocked(self):
        write_png(self.feature, 7, 6, 3)
        with self.assertRaises(ValueError):
            compare_regions(decode_png(self.base), decode_png(self.feature),
                            [(0, 0, 7, 6)])

    def test_corrupt_crc_blocked(self):
        data = bytearray(self.base.read_bytes())
        data[-5] ^= 0xFF
        self.base.write_bytes(data)
        with self.assertRaises(ValueError):
            decode_png(self.base)


if __name__ == "__main__":
    unittest.main()
