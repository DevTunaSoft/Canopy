import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
from scripts.validate_visual import png_dimensions, validate


def chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)


def create_png(path, width=2, height=3):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    pixels = (b"\x00" + b"\x00\x00\x00" * width) * height
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
                     chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


class VisualValidationTests(unittest.TestCase):
    def test_dimensions_and_broken_crc(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sample.png"
            create_png(path)
            self.assertEqual(png_dimensions(path), (2, 3))
            content = bytearray(path.read_bytes())
            content[24] ^= 2
            path.write_bytes(content)
            with self.assertRaises(ValueError):
                png_dimensions(path)

    def test_capture_report(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ("top-bar", "dock"):
                create_png(root / (name + ".png"))
            rows = [{"role": name, "filename": name + ".png", "width": 2, "height": 3}
                    for name in ("top-bar", "dock")]
            (root / "captures.json").write_text(json.dumps(
                {"schema_version": 1, "mode": "isolated-xvfb", "status": "PASS",
                 "captures": rows}))
            self.assertEqual(validate(root)["status"], "PASS")
            rows[0]["width"] = 99
            (root / "captures.json").write_text(json.dumps(
                {"schema_version": 1, "mode": "isolated-xvfb", "status": "PASS",
                 "captures": rows}))
            with self.assertRaises(ValueError):
                validate(root)

    def test_reject_partial_or_bad_png(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "test.png"
            path.write_bytes(b"wrong")
            with self.assertRaises(ValueError):
                png_dimensions(path)
            create_png(path)
            path.write_bytes(path.read_bytes()[:-12])
            with self.assertRaises(ValueError):
                png_dimensions(path)


if __name__ == "__main__":
    unittest.main()
