"""Unit tests for self-test PNG evidence verification."""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools.check_screenshot import PNG_SIGNATURE, verify_png


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload)) + kind + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    )


def image(width=760, height=500):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"\\x00" + b"\\x20\\x40\\x60" * width
    return (
        PNG_SIGNATURE + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw * height))
        + chunk(b"IEND", b"")
    )


class ScreenshotTests(unittest.TestCase):
    def test_valid_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "screenshot.png"
            path.write_bytes(image())
            verify_png(path, 760, 500)

    def test_wrong_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "screenshot.png"
            path.write_bytes(image())
            with self.assertRaisesRegex(ValueError, "Expected"):
                verify_png(path, 1200, 750)

    def test_bad_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "screenshot.png"
            corrupted = bytearray(image())
            corrupted[20] ^= 0x01
            path.write_bytes(corrupted)
            with self.assertRaises(ValueError):
                verify_png(path, 760, 500)

    def test_truncated_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "screenshot.png"
            path.write_bytes(image()[:-9])
            with self.assertRaises(ValueError):
                verify_png(path, 760, 500)


if __name__ == "__main__":
    unittest.main()
