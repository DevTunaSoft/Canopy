"""Safety contracts for the opt-in final optical balancing experiment.

These checks do not infer aesthetic acceptance from green CI.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"


class DockOpticalBalanceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = (ROOT / "main.cpp").read_text(encoding="utf-8")
        cls.provider = (ROOT / "RoundedDockIconProvider.cpp").read_text(encoding="utf-8")
        cls.header = (ROOT / "RoundedDockIconProvider.h").read_text(encoding="utf-8")
        cls.tile = (ROOT / "DockTile.qml").read_text(encoding="utf-8")

    def test_default_off_and_exact_originals_mandatory(self):
        self.assertIn('args.contains(QStringLiteral("--dock-optical-balance-review"))', self.main)
        self.assertIn("if (explicitOpticalBalanceReview && !approvedMode)", self.main)
        self.assertIn("approvedMode && !dockOriginalFitMode &&", self.main)
        self.assertIn("if (dockOriginalFitMode && !approvedMode)", self.main)
        self.assertIn("if (dockOriginalFitMode && iconReviewFlags > 0)", self.main)
        self.assertIn('args.contains(QStringLiteral("--dock-original-fit"))', self.main)
        self.assertIn("DOCK_OPTICAL_BALANCE_FAIL", self.main)
        self.assertIn("verifyExactArtwork(requested, !landscapeMode, &error)", self.main)
        self.assertNotIn("dockOpticalBalanceReviewMode = true", self.main)

    def test_only_one_experiment_active_at_a_time(self):
        self.assertIn("if (iconReviewFlags > 1)", self.main)
        self.assertIn("if ((framingReviewMode && balancedDockFitMode) ||", self.provider)
        self.assertIn("opticalBalanceReviewMode && (framingReviewMode || balancedDockFitMode)", self.provider)
        self.assertIn("bool opticalBalanceReviewMode = false", self.header)

    def test_caches_exactly_eight_original_pngs_and_respects_alpha_mask(self):
        self.assertIn("entries.size() != 8", self.provider)
        self.assertIn("m_images.insert(id, rendered)", self.provider)
        self.assertIn("outline.addRoundedRect(face, kRoundedRadius", self.provider)
        self.assertIn("painter.setClipPath(outline)", self.provider)
        self.assertIn("painter.fillPath(outline", self.provider)
        self.assertIn("painter.drawImage(placement, original)", self.provider)
        self.assertIn("kOpticalFitPixels = 160", self.provider)
        self.assertIn("original.width() != 345", self.provider)
        self.assertIn("face.contains(placement)", self.provider)
        self.assertNotIn("QFile::remove(", self.provider)
        self.assertNotIn("painter.translate(", self.provider)

    def test_measured_offsets_are_bounded_and_cover_eight(self):
        entries = self.provider.split("kOpticalBalanceOffset = {")[1].split("};")[0]
        pairs = re.findall(r'QStringLiteral\("([a-z]+)"\), QPointF\((-?\d+), (-?\d+)\)', entries)
        self.assertEqual(len(pairs), 8)
        self.assertEqual({name for name, _, _ in pairs},
                         {"browser", "mail", "files", "calendar",
                          "photos", "music", "terminal", "settings"})
        self.assertTrue(all(abs(int(dx)) <= 5 and abs(int(dy)) <= 5
                            for _, dx, dy in pairs))

    def test_visual_card_qml_and_default_fallback_unchanged(self):
        self.assertIn("anchors.centerIn: parent", self.tile)
        self.assertIn("width: 62", self.tile)
        self.assertIn("height: 62", self.tile)
        self.assertNotIn("anchors.verticalCenterOffset", self.tile)
        self.assertIn("else if (balancedDockFitMode && !terminalDerivative)", self.provider)
        self.assertIn("else if (framingReviewMode && !terminalDerivative)", self.provider)
        self.assertIn("const bool terminalDerivative", self.provider)
        self.assertIn("Qt::KeepAspectRatio", self.provider)
        self.assertIn("SELF_TEST_PASS: dock optical balance inside unchanged geometry", self.main)

    def test_no_background_processing_or_gpu_effect(self):
        self.assertNotIn("ShaderEffect", self.provider)
        self.assertNotIn("QTimer", self.provider)
        self.assertNotIn("QThread", self.provider)
        self.assertNotIn("QProcess", self.provider)


if __name__ == "__main__":
    unittest.main()
