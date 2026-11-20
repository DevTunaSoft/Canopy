"""Contract and fixture checks for the independent Classic landscape path."""
import struct
import tempfile
import unittest
from pathlib import Path

from tools.create_wallpaper_fixture import write_fixture

ROOT = Path(__file__).resolve().parents[1]


class LandscapeWallpaperTests(unittest.TestCase):
    def test_fixture_header_and_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fixture.png"
            write_fixture(target)
            content = target.read_bytes()
            self.assertEqual(content[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", content[16:24]), (2048, 1152))
            self.assertLess(len(content), 24_000_000)

    def test_fixture_rejects_unbounded_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_fixture(Path(tmp) / "unsafe.png", 100000, 100000)

    def test_landscape_decoupled_from_locked_icons(self):
        source = (ROOT / "prototype/classic/main.cpp").read_text()
        qml = (ROOT / "prototype/classic/Wallpaper.qml").read_text()
        self.assertIn("--landscape-wallpaper", source)
        self.assertIn("verifyLandscapeWallpaper(", source)
        self.assertIn("QImageReader reader(canonical)", source)
        self.assertIn("!file.isFile() || file.isSymLink()", source)
        self.assertIn("qint64(size.width()) * size.height() > 32'000'000", source)
        self.assertIn("verifyExactArtwork(requested, !landscapeMode, &error)", source)
        self.assertIn("canopyApprovedIconBase", source)
        self.assertIn("CANOPY_LANDSCAPE_WALLPAPER_VERIFIED", source)
        self.assertIn("canopyLandscapeWallpaperUrl.length > 0", qml)
        self.assertIn("Image.PreserveAspectCrop", qml)
        self.assertIn("cache: true", qml)
        self.assertNotIn("ShaderEffect", qml)
        self.assertNotIn("Timer {", qml)


if __name__ == "__main__":
    unittest.main()
