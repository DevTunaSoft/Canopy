"""Offline unit tests for bounded pre-flight screenshot limits.

Synthetic PNG bytes only. No real Qt build, Linux Mint guest or compiled
binary is exercised here. The existing PNG validator is reused in one test
to show composition rather than duplicated parsing.
"""
from functools import partial
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from canopy_features.performance import screenshot_limits as limits_mod
from tools import check_screenshot

SIGNATURE = b"\x89PNG\r\n\x1a\n"
ScreenshotLimitError = limits_mod.ScreenshotLimitError
ScreenshotLimits = limits_mod.ScreenshotLimits


def chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def make_png(width, height, *, idat=None):
    """Build a small valid 8-bit RGB PNG (non-interlaced)."""
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    if idat is None:
        row = b"\x00" + bytes((x + y) & 0xff
                              for y in range(height) for x in range(width * 3))
        idat = zlib.compress(row)
    return SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


class ScreenshotLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def write(self, name, data):
        path = self.dir / name
        path.write_bytes(data)
        return path

    def test_valid_screenshot_passes_and_returns_info(self):
        data = make_png(1200, 750)
        path = self.write("valid.png", data)
        info = limits_mod.check_limits(path)
        self.assertEqual((info.width, info.height), (1200, 750))
        self.assertEqual(info.byte_size, len(data))

    def test_oversized_file_rejected_before_read(self):
        # max_bytes far below a valid PNG; rejection happens on stat alone.
        path = self.write("big.png", make_png(40, 40))
        small = ScreenshotLimits(max_bytes=100)
        with self.assertRaisesRegex(ScreenshotLimitError, "exceeds 100 byte limit"):
            limits_mod.check_limits(path, small)

    def test_oversized_width_rejected(self):
        path = self.write("wide.png", make_png(5000, 100))
        with self.assertRaisesRegex(ScreenshotLimitError, "width 5000 exceeds"):
            limits_mod.check_limits(path)

    def test_oversized_height_rejected(self):
        path = self.write("tall.png", make_png(100, 3000))
        with self.assertRaisesRegex(ScreenshotLimitError, "height 3000 exceeds"):
            limits_mod.check_limits(path)

    def test_custom_limits_boundary(self):
        path = self.write("medium.png", make_png(200, 100))
        with self.assertRaises(ScreenshotLimitError):
            limits_mod.check_limits(path, ScreenshotLimits(max_width=100))
        info = limits_mod.check_limits(path, ScreenshotLimits(max_width=200, max_height=100))
        self.assertEqual((info.width, info.height), (200, 100))

    def test_truncated_png_rejected(self):
        # Too small for even a signature plus one chunk header.
        tiny = self.write("tiny.png", SIGNATURE[:8])
        with self.assertRaisesRegex(ScreenshotLimitError, "truncated PNG: file too small"):
            limits_mod.check_limits(tiny)

        # Signature and IHDR header present, but payload is cut short.
        short_payload = self.write("short_payload.png", SIGNATURE + struct.pack(">I4s", 13, b"IHDR") + b"\x00" * 5)
        with self.assertRaisesRegex(ScreenshotLimitError, "truncated PNG: incomplete image header"):
            limits_mod.check_limits(short_payload)

        # Full IHDR payload present, CRC missing.
        header = struct.pack(">IIBBBBB", 1200, 750, 8, 2, 0, 0, 0)
        no_crc = self.write("no_crc.png", SIGNATURE + struct.pack(">I4s", 13, b"IHDR") + header)
        with self.assertRaisesRegex(ScreenshotLimitError, "truncated PNG: incomplete header CRC"):
            limits_mod.check_limits(no_crc)

    def test_invalid_signature_rejected(self):
        path = self.write("fake.png", b"not a png file at all")
        with self.assertRaisesRegex(ScreenshotLimitError, "invalid PNG signature"):
            limits_mod.check_limits(path)

    def test_missing_symlink_and_non_regular_rejected(self):
        with self.assertRaises(ScreenshotLimitError):
            limits_mod.check_limits(self.dir / "missing.png")
        with self.assertRaises(ScreenshotLimitError):
            limits_mod.check_limits(self.dir)  # directory, not a regular file

        target = self.write("target.png", make_png(10, 10))
        link = self.dir / "link.png"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not permitted on this host")
        with self.assertRaisesRegex(ScreenshotLimitError, "symlink"):
            limits_mod.check_limits(link)

    def test_bounded_preflight_does_not_decode_image_data(self):
        # Valid IHDR, garbage IDAT. Pre-flight still returns info: decoding is
        # the inspector's job, not this gate's.
        path = self.write("garbage_idat.png", make_png(60, 40, idat=b"\x00\xff\x01\x02"))
        info = limits_mod.check_limits(path)
        self.assertEqual((info.width, info.height), (60, 40))

    def test_guard_composes_with_existing_validator(self):
        path = self.write("compose.png", make_png(80, 40))
        verifier = partial(check_screenshot.verify_png, width=80, height=40)
        result, info = limits_mod.guard(path, verifier)
        self.assertIsNone(result)  # verify_png returns None on success
        self.assertEqual((info.width, info.height), (80, 40))

    def test_guard_skips_inspector_on_oversized_input(self):
        calls = []

        def inspector(_path):
            calls.append(_path)
            raise AssertionError("inspector must not run for rejected input")

        path = self.write("reject.png", make_png(5000, 100))
        with self.assertRaises(ScreenshotLimitError):
            limits_mod.guard(path, inspector)
        self.assertEqual(calls, [])

    def test_invalid_limits_rejected(self):
        path = self.write("ok.png", make_png(10, 10))
        with self.assertRaises(TypeError):
            limits_mod.check_limits(path, (100, 100, 100))
        with self.assertRaises(ValueError):
            limits_mod.check_limits(path, ScreenshotLimits(max_width=0))


if __name__ == "__main__":
    unittest.main()
