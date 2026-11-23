"""Static safety contracts for conservative, non-destructive dock fit review.

This is NOT visual approval. Actual build/capture/pixel isolation belongs to CI.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "prototype" / "classic"


class BalancedFitContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = (SRC / "main.cpp").read_text()
        cls.provider = (SRC / "RoundedDockIconProvider.cpp").read_text()
        cls.header = (SRC / "RoundedDockIconProvider.h").read_text()
        cls.dock = (SRC / "DockTile.qml").read_text()

    def test_separate_flag_never_becomes_default(self):
        self.assertIn('args.contains(QStringLiteral("--dock-balanced-fit-review"))',
                      self.cpp)
        self.assertIn("if (dockBalancedFitReviewMode && !approvedMode)", self.cpp)
        self.assertIn("DOCK_BALANCED_FIT_REVIEW_FAIL", self.cpp)
        self.assertIn("if (dockBalancedFitReviewMode && (dockInnerReviewMode || framingReviewMode))", self.cpp)
        self.assertIn('approvedRoot, terminalCandidatePath, dockInnerReviewMode,', self.cpp)
        self.assertIn("&roundedError, dockBalancedFitReviewMode", self.cpp)
        self.assertIn("bool balancedDockFitMode = false", self.header)
        self.assertNotIn("dockBalancedFitReviewMode = true", self.cpp)

    def test_preserves_original_full_vertical_content_no_magnification_crop(self):
        self.assertIn("constexpr qreal kFullSourceHeight = 333.0;", self.provider)
        self.assertIn('(original.height() - kFullSourceHeight) / 2.0', self.provider)
        self.assertIn('kFullSourceHeight, kFullSourceHeight', self.provider)
        self.assertIn("painter.drawImage(face, original, source)", self.provider)
        self.assertIn("source.right() > original.width()", self.provider)
        self.assertIn("source.bottom() > original.height()", self.provider)
        self.assertIn("balanced dock source sample out of bounds", self.provider)
        self.assertIn("original.width() != 345", self.provider)
        self.assertIn("original.height() != 333", self.provider)

    def test_every_profile_is_a_safe_333_square_crop(self):
        data = self.provider.split("kLauncherOpticalCenters = {")[1].split("};")[0]
        centers = re.findall(r'QStringLiteral\("([a-z]+)"\), QPointF\((\d+), (\d+)\)',
                             data)
        self.assertEqual(len(centers), 8)
        self.assertEqual({key for key, _, _ in centers},
                         {"browser","mail","files","calendar","photos",
                          "music","terminal","settings"})
        for _name, x, y in centers:
            source_left = int(x) - 333/2
            self.assertGreaterEqual(source_left, 0)
            self.assertLessEqual(source_left + 333, 345)
            self.assertGreaterEqual(int(y), 162)
            self.assertLessEqual(int(y), 171)

    def test_card_and_artwork_masters_remain_immutable(self):
        self.assertIn("outline.addRoundedRect(face, kRoundedRadius", self.provider)
        self.assertIn("painter.fillPath(outline", self.provider)
        self.assertNotIn("painter.translate(", self.provider)
        self.assertNotIn("QFile::remove(", self.provider)
        self.assertIn("anchors.centerIn: parent", self.dock)
        self.assertIn("width: 54", self.dock)
        self.assertIn("height: 54", self.dock)
        self.assertNotIn("anchors.verticalCenterOffset", self.dock)

    def test_default_and_terminal_optional_derivative_unmodified(self):
        self.assertIn("if (balancedDockFitMode && !terminalDerivative)", self.provider)
        self.assertIn("else if (framingReviewMode && !terminalDerivative)", self.provider)
        self.assertIn("Qt::KeepAspectRatio", self.provider)
        self.assertIn("painter.drawImage(placement, original)", self.provider)
        self.assertIn('DOCK_BALANCED_FIT_REVIEW_ACTIVE:', self.cpp)
        self.assertIn("SELF_TEST_PASS: dock balanced full-height original content fit", self.cpp)


if __name__ == "__main__":
    unittest.main()
