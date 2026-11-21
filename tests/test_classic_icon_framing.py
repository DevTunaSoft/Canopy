"""Prevent repeat of PR #108: move *source-sheet content*, never dock cards.

These are static contract guards. Actual Qt6 compilation/scene screenshots
and human visual acceptance are required separately.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"


class SourceSheetFramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = (ROOT / "RoundedDockIconProvider.cpp").read_text()
        cls.hdr = (ROOT / "RoundedDockIconProvider.h").read_text()
        cls.main = (ROOT / "main.cpp").read_text()
        cls.tile = (ROOT / "DockTile.qml").read_text()

    def test_review_explicitly_opt_in_and_requires_originals(self):
        self.assertIn('args.contains(QStringLiteral("--icon-framing-review"))',
                      self.main)
        self.assertIn("if (frameReviewMode && !approvedMode)", self.main)
        self.assertIn("ICON_FRAMING_REVIEW_FAIL", self.main)
        self.assertIn("verifyExactArtwork(requested, !landscapeMode, &error)",
                      self.main)
        self.assertNotIn("frameReviewMode = true", self.main)

    def test_all_eight_pinned_crop_measurements(self):
        pattern = re.compile(
            r'\{QStringLiteral\("([a-z]+)"\), (\d+)\}', re.MULTILINE
        )
        values = dict((name, int(n)) for name, n
                      in pattern.findall(self.provider.split("kSourceSheetTopGutters = {")[1]
                                          .split("};")[0]))
        self.assertEqual(values, {
            "browser": 9, "mail": 6, "files": 2, "calendar": 0,
            "photos": 0, "music": 5, "terminal": 14, "settings": 14,
        })
        self.assertTrue(all(0 <= v <= 14 for v in values.values()))

    def test_square_content_reframed_inside_same_centered_card(self):
        src = self.provider
        self.assertIn("const int side = original.height() - top", src)
        self.assertIn("const int left = (original.width() - side) / 2", src)
        self.assertIn("const QRectF sourceRect(left, top, side, side)", src)
        self.assertIn("painter.drawImage(face, original, sourceRect)", src)
        self.assertIn("outline.addRoundedRect(face, kRoundedRadius", src)
        self.assertIn("painter.setClipPath(outline)", src)
        self.assertIn("painter.fillPath(outline", src)
        self.assertNotIn("translate(", src)
        self.assertNotIn("QImage::save", src)
        self.assertNotIn("QFile::remove", src)

    def test_default_preserves_original_full_fit_and_terminal_v3(self):
        self.assertIn("if (framingReviewMode && !usesTerminalDerivative)", self.provider)
        self.assertIn("!terminalCandidatePath.isEmpty() && sourcePath == terminalCandidatePath", self.provider)
        self.assertIn("const QSize fitted = original.size().scaled(", self.provider)
        self.assertIn("Qt::KeepAspectRatio", self.provider)
        self.assertIn("painter.drawImage(placement, original)", self.provider)
        self.assertIn("frameReviewMode, &roundedError", self.main)

    def test_centered_image_frame_and_active_dot_never_shifted(self):
        self.assertIn("anchors.centerIn: parent", self.tile)
        self.assertIn("width: 54", self.tile)
        self.assertIn("height: 54", self.tile)
        self.assertIn("source: tile.iconUrl", self.tile)
        self.assertIn("anchors.bottomMargin: 2", self.tile)
        self.assertNotIn("anchors.horizontalCenterOffset", self.tile)
        self.assertNotIn("anchors.verticalCenterOffset", self.tile)

    def test_real_qt_screenshot_geometry_gate_still_exists(self):
        self.assertIn('SELF_TEST_FAIL: dock icon optical alignment', self.main)
        self.assertIn('qAbs(iconMidX - buttonMidX) > 0.75', self.main)
        self.assertIn('qAbs(iconMidY - buttonMidY) > 0.75', self.main)
        self.assertIn("SELF_TEST_PASS: opt-in icon source framing verified", self.main)
        self.assertIn("owner approval pending", self.main)

    def test_source_verification_and_failure_paths(self):
        self.assertIn("QImageReader reader(sourcePath)", self.provider)
        self.assertIn("if (side < 256 || original.width() < side", self.provider)
        self.assertIn("m_images.clear()", self.provider)
        self.assertIn("approved image framing dimensions invalid", self.provider)


if __name__ == "__main__":
    unittest.main()
