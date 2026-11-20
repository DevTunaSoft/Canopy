"""Run the real icon-ingestion utility on synthetic PNGs; no external dependencies."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.prepare_classic_icons import stage_assets, validate_png

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "prototype/classic/assets/icons/classic-approved-selections.json"


def make_png(width=256, height=256, color_type=6):
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    count = 4 if color_type == 6 else 3
    scanline = b"\\x00" + bytes([90] * count * width)
    pixels = zlib.compress(scanline * height)
    return b"\\x89PNG\\r\\n\\x1a\\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


class IconIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.output = self.base / "output"
        self.source.mkdir()
        self.items = json.loads(MANIFEST.read_text())["icons"]
        for item in self.items:
            (self.source / f'{item["app"]}-option-{item["option"]}.png').write_bytes(make_png())

    def test_stage_exact_approved_assets_and_qrc(self):
        staged = stage_assets(self.source, self.output)
        self.assertEqual(len(staged), 8)
        self.assertEqual(sorted(p.name for p in self.output.glob("*.png")),
                         sorted(f'{item["app"]}.png' for item in self.items))
        qrc = (self.output / "classic-icons.qrc").read_text()
        self.assertIn('prefix="/canopy/classic/icons"', qrc)
        self.assertIn('alias="browser.png"', qrc)
        self.assertEqual(json.loads((self.output / "staged-icons.json").read_text())["scope"],
                         "review_only_not_release_approved")

    def test_reject_missing_icon_without_creating_output(self):
        (self.source / "browser-option-3.png").unlink()
        with self.assertRaisesRegex(ValueError, "Missing reviewed source"):
            stage_assets(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_reject_wrong_option_filename(self):
        (self.source / "browser-option-3.png").rename(self.source / "browser-option-2.png")
        with self.assertRaisesRegex(ValueError, "Missing reviewed source"):
            stage_assets(self.source, self.output)

    def test_reject_rgb_nontransparent_png(self):
        path = self.source / "browser-option-3.png"
        path.write_bytes(make_png(color_type=2))
        with self.assertRaisesRegex(ValueError, "RGBA"):
            stage_assets(self.source, self.output)

    def test_reject_modified_crc_and_small_icon(self):
        path = self.source / "browser-option-3.png"
        corrupted = bytearray(path.read_bytes())
        corrupted[20] ^= 0x02
        path.write_bytes(corrupted)
        with self.assertRaisesRegex(ValueError, "CRC mismatch"):
            validate_png(path)
        path.write_bytes(make_png(128, 128))
        with self.assertRaisesRegex(ValueError, "dimensions"):
            validate_png(path)

    def test_reject_output_overwrite(self):
        self.output.mkdir()
        (self.output / "existing.txt").write_text("don't overwrite")
        with self.assertRaisesRegex(ValueError, "empty"):
            stage_assets(self.source, self.output)


if __name__ == "__main__":
    unittest.main()
