"""Canopy Classic visual identity regression guards (source, not aesthetic approval).

Real Qt screenshots + exact original PNG archive are still required for sign-off.
"""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
NS = "{http://www.w3.org/2000/svg}"


class RoundedDockAndColorTuxTests(unittest.TestCase):
    def test_approved_icons_are_not_mutated_or_replaced(self):
        dock = (CLASSIC / "DockTile.qml").read_text()
        cpp = (CLASSIC / "main.cpp").read_text()
        provider = (CLASSIC / "RoundedDockIconProvider.cpp").read_text()
        self.assertIn('image://canopy-dock/', dock)
        self.assertIn('source: tile.iconUrl', dock)
        self.assertIn('sourceSize: Qt.size(192, 192)', dock)
        self.assertIn('engine.addImageProvider(QStringLiteral("canopy-dock"), roundedIcons)', cpp)
        strict_gate = re.search(
            r"verifyExactArtwork\(\s*requested,\s*!landscapeMode,\s*&error,\s*&verifiedArtBytes\s*\)",
            cpp,
        )
        self.assertIsNotNone(strict_gate, "strict artwork gate lost verified bytes")
        self.assertLess(strict_gate.start(), cpp.index('new RoundedDockIconProvider('))
        self.assertIn('QImageReader reader(sourcePath)', provider)
        self.assertNotIn('QFile::remove', provider)
        self.assertNotIn('QImage::save', provider)
        self.assertNotIn('QProcess', provider)

    def test_rounded_alpha_clip_and_zoom_out_are_implemented_once(self):
        src = (CLASSIC / "RoundedDockIconProvider.cpp").read_text()
        self.assertIn('constexpr int kCanvasPixels = 192;', src)
        self.assertIn('constexpr int kInsetPixels = 12;', src)
        self.assertIn('outline.addRoundedRect(face, kRoundedRadius, kRoundedRadius)', src)
        self.assertIn('painter.setClipPath(outline)', src)
        self.assertIn('Qt::KeepAspectRatio', src)
        self.assertIn('painter.drawImage(placement, original)', src)
        self.assertIn('m_images.insert(id, rendered)', src)
        self.assertIn('image.pixelColor(kInsetPixels + 1, kInsetPixels + 1).alpha() != 0', src)
        self.assertIn('allCornersClipped()', src)
        self.assertNotIn('ShaderEffect', src)
        self.assertNotIn('QTimer', src)

    def test_launcher_uses_full_color_tux_without_discarding_reference_shape(self):
        svg = (CLASSIC / "assets/brand/penguin-launcher.svg").read_text()
        root = ET.fromstring(svg)
        paths = list(root.iter(NS + "path"))
        self.assertGreaterEqual(len(paths), 5)
        self.assertEqual(paths[0].get("fill-rule"), "evenodd")
        self.assertEqual(len(re.findall(r"\bM\s", paths[0].get("d", ""))), 4)
        self.assertIn("#182236", svg)
        self.assertIn("#f7f9fd", svg)
        self.assertIn("#ffca35", svg)
        self.assertIn("#f4b523", svg)
        self.assertIn('source: "qrc:/Canopy/Classic/assets/brand/penguin-launcher.svg"',
                      (CLASSIC / "Main.qml").read_text())

    def test_qt_build_includes_provider_and_unchanged_artwork_lock(self):
        cmake = (CLASSIC / "CMakeLists.txt").read_text()
        self.assertIn("RoundedDockIconProvider.cpp", cmake)
        self.assertIn("RoundedDockIconProvider.h", cmake)
        self.assertIn("assets/approved/manifest.json", cmake)
        self.assertIn("assets/brand/penguin-launcher.svg", cmake)


if __name__ == "__main__":
    unittest.main()
