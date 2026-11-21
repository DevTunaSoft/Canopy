"""Contracts for strictly opt-in, non-destructive icon framing review.

These are source checks only. Actual Qt build/screenshot, SHA-pinned
private original-art replay, and owner visual review remain mandatory.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"


class SharedIconFramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = (ROOT / "main.cpp").read_text(encoding="utf-8")
        cls.provider = (ROOT / "RoundedDockIconProvider.cpp").read_text(encoding="utf-8")
        cls.header = (ROOT / "RoundedDockIconProvider.h").read_text(encoding="utf-8")
        cls.tile = (ROOT / "DockTile.qml").read_text(encoding="utf-8")
        cls.launcher = (ROOT / "LauncherOverlay.qml").read_text(encoding="utf-8")

    def test_explicit_opt_in_rejects_missing_originals(self):
        self.assertIn('args.contains(QStringLiteral("--icon-framing-review"))', self.cpp)
        self.assertIn("if (framingReviewMode && !approvedMode)", self.cpp)
        self.assertIn("ICON_FRAMING_REVIEW_FAIL", self.cpp)
        self.assertIn("verifyExactArtwork(requested, !landscapeMode, &error)", self.cpp)
        self.assertIn("framingReviewMode, &roundedError", self.cpp)
        self.assertNotIn("framingReviewMode = true", self.cpp)

    def test_reuses_existing_eight_gutter_measurements_without_deleting_any(self):
        start = self.provider.split("kApprovedSourceTopGutters = {")[1].split("};")[0]
        terms = dict((name, int(number)) for name, number in
                     re.findall(r'\{QStringLiteral\("([a-z]+)"\), (\d+)\}', start))
        self.assertEqual(terms, {
            "browser": 9, "mail": 6, "files": 2, "calendar": 0,
            "photos": 0, "music": 5, "terminal": 14, "settings": 14,
        })

    def test_fixed_outer_card_mask_unmodified_and_no_whole_card_shift(self):
        self.assertIn("outline.addRoundedRect(face, kRoundedRadius", self.provider)
        self.assertIn("painter.setClipPath(outline)", self.provider)
        self.assertIn("painter.fillPath(outline", self.provider)
        self.assertIn("const int side = original.height() - top", self.provider)
        self.assertIn("const int left = (original.width() - side) / 2", self.provider)
        self.assertIn("painter.drawImage(face, original, originalSample)", self.provider)
        self.assertNotIn("painter.translate(", self.provider)
        self.assertNotIn("QFile::remove(", self.provider)
        self.assertIn("anchors.centerIn: parent", self.tile)
        self.assertIn("width: 54", self.tile)
        self.assertIn("height: 54", self.tile)
        self.assertNotIn("anchors.verticalCenterOffset", self.tile)

    def test_default_renderer_unchanged_terminal_derivative_not_reframed(self):
        self.assertIn("if (framingReviewMode && !terminalDerivative)", self.provider)
        self.assertIn("Qt::KeepAspectRatio", self.provider)
        self.assertIn("painter.drawImage(placement, original)", self.provider)
        self.assertIn("const bool terminalDerivative =", self.provider)
        self.assertIn("bool framingReviewMode, QString *error", self.provider)
        self.assertIn("bool framingReviewMode, QString *error", self.header)

    def test_single_shared_provider_feeds_dock_and_launcher(self):
        self.assertIn('engine.addImageProvider(QStringLiteral("canopy-dock"), roundedIcons)', self.cpp)
        self.assertIn('"image://canopy-dock/" + iconName.toLowerCase()', self.tile)
        self.assertIn('"image://canopy-dock/" + appButton.modelData.title.toLowerCase()', self.launcher)
        self.assertIn('objectName: "canopyLauncherIcon"', self.launcher)
        self.assertIn("readonly property bool imageReady: status === Image.Ready", self.launcher)
        self.assertIn('QStringLiteral("canopyLauncherIcon")', self.cpp)
        self.assertIn("countReadyLauncherImages(applicationLauncher)", self.cpp)
        self.assertNotIn("ShaderEffect", self.launcher)
        self.assertNotIn("Timer {", self.launcher)

    def test_real_qt_mode_and_independent_image_readiness_gates_exist(self):
        self.assertIn("SELF_TEST_PASS: shared Qt dock+launcher frame review enabled", self.cpp)
        self.assertIn("SELF_TEST_FAIL: incomplete launcher image catalogue", self.cpp)
        self.assertIn("SELF_TEST_PASS: actual launcher image component count", self.cpp)
        self.assertIn("SELF_TEST_PASS: dock icons horizontally/vertically centred", self.cpp)
        self.assertIn("qAbs(iconMidX - buttonMidX) > 0.75", self.cpp)
        self.assertIn("qAbs(iconMidY - buttonMidY) > 0.75", self.cpp)


if __name__ == "__main__":
    unittest.main()
