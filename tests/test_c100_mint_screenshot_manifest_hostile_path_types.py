"""Wrong-type path arguments must fail closed with the manifest domain error.

A hostile-but-bounded caller value (finite scalar/container or a PathLike whose
``__fspath__`` returns a non-string) must never leak a raw ``TypeError`` out of
the manifest boundary, and must never produce a capture-safe claim.  Synthetic
PNG bytes are files on disk; a green unit test is not proof of a real capture.
"""
import os
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from canopy_features.mint import screenshot_capture_manifest as scm


def _chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))


def _png(width=8, height=8):
    """Build a valid nonuniform RGBA PNG accepted by mint_classic_qt_smoke."""
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend((32 + x % 2 + y % 2, 40, 52, 255))
        rows.append(bytes(row))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(b"".join(rows)))
            + _chunk(b"IEND", b""))


class _BadFspath:
    """Bounded hostile path-like: __fspath__ returns the wrong type."""

    def __fspath__(self):
        return 123


class _BytesFspath:
    """Bounded hostile path-like: __fspath__ returns bytes, not str."""

    def __fspath__(self):
        return b"/not/a/string/path"


class HostilePathTypeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture = self.root / "capture.png"
        self.capture.write_bytes(_png())

    def assertDomainError(self, fn, pattern):
        with self.assertRaisesRegex(scm.ManifestError, pattern):
            fn()
        try:
            fn()
        except scm.ManifestError as exc:
            self.assertIs(type(exc), scm.ManifestError)
        except Exception as exc:  # pragma: no cover - RED diagnostics
            self.fail("raw %s escaped the manifest boundary" % type(exc).__name__)

    def test_capture_path_wrong_types_fail_closed(self):
        for value in (7, None, b"/abs/capture.png", [str(self.capture)],
                      {"path": str(self.capture)}, _BadFspath(), _BytesFspath()):
            with self.subTest(value=type(value).__name__):
                self.assertDomainError(
                    lambda v=value: scm.build_manifest([v]),
                    "capture path",
                )

    def test_capture_container_wrong_types_fail_closed(self):
        for value in (None, 7, str(self.capture), {"a": str(self.capture)}):
            with self.subTest(value=type(value).__name__):
                self.assertDomainError(
                    lambda v=value: scm.build_manifest(v),
                    "captures must be",
                )

    def test_binary_path_wrong_types_fail_closed(self):
        for value in (7, [str(self.capture)], _BadFspath(), _BytesFspath()):
            with self.subTest(value=type(value).__name__):
                self.assertDomainError(
                    lambda v=value: scm.build_manifest([self.capture], binary=v),
                    "binary path",
                )

    def test_write_manifest_target_wrong_types_fail_closed(self):
        payload = scm.build_manifest([self.capture])
        for value in (7, None, [str(self.root / "out.json")], _BadFspath(),
                      _BytesFspath()):
            with self.subTest(value=type(value).__name__):
                self.assertDomainError(
                    lambda v=value: scm.write_manifest(v, payload),
                    "manifest target path",
                )
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["capture.png"])

    def test_valid_path_objects_still_build_and_write(self):
        result = scm.build_manifest([Path(self.capture)], binary=Path(self.capture))
        self.assertEqual(result["capture_count"], 1)
        self.assertRegex(result["binary_sha256"], r"^[0-9a-f]{64}$")
        target = scm.write_manifest(Path(self.root / "out.json"), result)
        self.assertEqual(target, self.root / "out.json")
        self.assertEqual(target.read_bytes(), scm.serialize(result))
        self.assertIsInstance(os.fspath(target), str)


if __name__ == "__main__":
    unittest.main()
