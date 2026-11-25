"""Regression tests for the exact approved Classic wallpaper gate."""
from __future__ import annotations

import hashlib
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools.check_wallpaper import (
    APPROVED_ASSET,
    APPROVED_SHA256,
    DUPLICATE_ASSET,
    MAIN_QML,
    MASTER_NAME,
    WALLPAPER_QML,
    check,
    png_dimensions,
    sha256_file,
)

REPO = Path(__file__).resolve().parents[1]
SIGNATURE = b"\x89PNG\r\n\x1a\n"


def fake_png(width=1920, height=1080):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
    return SIGNATURE + struct.pack(">I", 13) + chunk + struct.pack(">I", 0)


def write_fixture(root: Path, raw: bytes):
    for relative in (APPROVED_ASSET, DUPLICATE_ASSET, MAIN_QML, WALLPAPER_QML):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative in (APPROVED_ASSET, DUPLICATE_ASSET):
            path.write_bytes(raw)
        elif relative == MAIN_QML:
            path.write_text(
                "Wallpaper { anchors.fill: parent }\n"
                f"{MASTER_NAME}\napprovedMasterWallpaperUrl\n"
                "Qt.binding\ncanopyLandscapeWallpaperUrl.length > 0\n"
                'child.objectName === "canopyWallpaperImage"\n',
                encoding="utf-8")
        else:
            path.write_text("Image {}\nImage.PreserveAspectCrop\n", encoding="utf-8")


class ApprovedWallpaperGateTests(unittest.TestCase):
    def test_repository_master_is_byte_exact_in_both_owned_paths(self):
        for relative in (APPROVED_ASSET, DUPLICATE_ASSET):
            path = REPO / relative
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(sha256_file(path), APPROVED_SHA256, relative.as_posix())
            self.assertEqual(len(path.read_bytes()), 3_107_170)
            self.assertEqual(png_dimensions(path.read_bytes()), (1920, 1080))
        self.assertEqual((REPO / APPROVED_ASSET).read_bytes(),
                         (REPO / DUPLICATE_ASSET).read_bytes())

    def test_repository_gate_passes(self):
        result = check(REPO)
        self.assertEqual(result["status"], "PASS", result["problems"])

    def test_green_fixture_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = fake_png()
            write_fixture(root, raw)
            result = check(root, hashlib.sha256(raw).hexdigest(), len(raw))
            self.assertEqual(result["status"], "PASS", result["problems"])

    def test_tampered_master_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = fake_png()
            write_fixture(root, raw)
            (root / APPROVED_ASSET).write_bytes(raw + b"substitute")
            result = check(root, hashlib.sha256(raw).hexdigest(), len(raw) + len(b"substitute"))
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("SHA-256 mismatch" in p for p in result["problems"]))

    def test_blue_wave_default_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = fake_png()
            write_fixture(root, raw)
            main = root / MAIN_QML
            main.write_text(main.read_text(encoding="utf-8") + 'source: "blue-current.svg"\n',
                            encoding="utf-8")
            result = check(root, hashlib.sha256(raw).hexdigest(), len(raw))
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("blue-current.svg" in p for p in result["problems"]))

    def test_wrong_dimensions_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = fake_png(1200, 750)
            write_fixture(root, raw)
            result = check(root, hashlib.sha256(raw).hexdigest(), len(raw))
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("wrong dimensions" in p for p in result["problems"]))

    def test_generated_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = fake_png()
            write_fixture(root, raw)
            (root / APPROVED_ASSET.parent / "generated-lookalike.png").write_bytes(raw)
            result = check(root, hashlib.sha256(raw).hexdigest(), len(raw))
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("unexpected wallpaper candidate" in p
                                for p in result["problems"]))


if __name__ == "__main__":
    unittest.main()
