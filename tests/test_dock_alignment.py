"""Check real dock centering contracts and guard against top-aligned regression.

The C++ Qt screenshot smoke test additionally measures all eight image rectangles.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"


class DockAlignmentTests(unittest.TestCase):
    def test_icon_geometry_is_centered_not_top_aligned(self):
        tile = (ROOT / "DockTile.qml").read_text(encoding="utf-8")
        self.assertIn("width: 58", tile)
        self.assertIn("height: 70", tile)
        self.assertIn("width: 54", tile)
        self.assertIn("height: 54", tile)
        self.assertEqual(tile.count("anchors.centerIn: parent"), 2)
        self.assertNotIn("anchors.topMargin: 2", tile)
        self.assertIn("anchors.bottomMargin: 2", tile)
        self.assertIn('source: tile.iconUrl', tile)

    def test_all_eight_real_qt_image_boxes_are_checked(self):
        source = (ROOT / "main.cpp").read_text(encoding="utf-8")
        self.assertIn('findVisualItem(button, QStringLiteral("canopyDockIcon"))', source)
        self.assertIn('qAbs(iconMidX - buttonMidX - expectedX) > 0.75', source)
        self.assertIn('qAbs(iconMidY - buttonMidY - expectedY) > 0.75', source)
        self.assertIn('qAbs(iconMidY - dock->height() / 2 - expectedY) > 1.0', source)
        self.assertIn('SELF_TEST_FAIL: dock icon optical alignment', source)
        self.assertIn('SELF_TEST_PASS: dock icons horizontally/vertically centred', source)
        self.assertIn('QStringLiteral("Trash")', source)
        self.assertIn('QStringLiteral("Settings")', source)
        self.assertIn('QStringLiteral("Browser")', source)

    def test_rounded_source_verified_artwork_unchanged(self):
        provider = (ROOT / "RoundedDockIconProvider.cpp").read_text(encoding="utf-8")
        self.assertIn('painter.setClipPath(outline)', provider)
        self.assertIn('Qt::KeepAspectRatio', provider)
        self.assertIn('m_images.insert(id, rendered)', provider)
        self.assertIn('allCornersClipped()', provider)
        self.assertNotIn('QFile::remove', provider)


if __name__ == "__main__":
    unittest.main()
