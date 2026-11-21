"""Optical alignment candidate QA — separate from final owner visual approval.

The values are deliberately bounded UI offsets. No source-approved PNGs
or embedded source digests may be changed by this preview.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"


class OpticalDockReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qml = (CLASSIC / "DockTile.qml").read_text(encoding="utf-8")
        cls.main = (CLASSIC / "main.cpp").read_text(encoding="utf-8")
        cls.provider = (CLASSIC / "RoundedDockIconProvider.cpp").read_text(encoding="utf-8")

    def test_only_approved_mode_can_enable_preview_offsets(self):
        self.assertIn('args.contains(QStringLiteral("--optical-review"))', self.main)
        self.assertIn("if (opticalReviewMode && !approvedMode)", self.main)
        self.assertIn("OPTICAL_REVIEW_FAIL", self.main)
        self.assertIn("canopyOpticalReviewMode", self.main)

    def test_default_is_unmodified_and_centered(self):
        self.assertIn("canopyApprovedMode && canopyOpticalReviewMode", self.qml)
        self.assertIn("? (opticalOffsets[iconName] || [0, 0])[0] : 0", self.qml)
        self.assertIn("? (opticalOffsets[iconName] || [0, 0])[1] : 0", self.qml)
        self.assertIn("anchors.centerIn: parent", self.qml)
        self.assertIn("anchors.horizontalCenterOffset: tile.opticalOffsetX", self.qml)
        self.assertIn("anchors.verticalCenterOffset: tile.opticalOffsetY", self.qml)
        self.assertIn("source: tile.iconUrl", self.qml)
        self.assertIn("fillMode: Image.PreserveAspectFit", self.qml)

    def test_all_eight_original_ui_offsets_are_bounded(self):
        expected = {
            "Browser": (1, 0),
            "Mail": (0, -1),
            "Files": (-1, -1),
            "Calendar": (-2, 1),
            "Photos": (0, -1),
            "Music": (0, 1),
            "Settings": (-2, 1),
        }
        pairs = re.findall(
            r'^\s*"([A-Za-z]+)": \[(-?\d+), (-?\d+)\],?$',
            self.qml, flags=re.MULTILINE,
        )
        actual = {name: (int(x), int(y)) for name, x, y in pairs}
        self.assertEqual(actual, expected)
        self.assertIn(
            '"Terminal": canopyTerminalRefinementMode ? [-1, 0] : [-2, 2]',
            self.qml,
        )
        self.assertTrue(all(abs(x) <= 2 and abs(y) <= 2
                            for x, y in actual.values()))

    def test_terminal_refinement_is_distinct_from_original(self):
        self.assertIn("canopyTerminalRefinementMode", self.qml)
        self.assertIn("!terminalCandidatePath.isEmpty()", self.main)
        self.assertIn("CANOPY_OPTICAL_REVIEW_ENABLED", self.main)

    def test_actual_qt_scene_validation_compares_to_offset_bounds(self):
        for phrase in (
            "button->property(\"opticalOffsetX\")",
            "button->property(\"opticalOffsetY\")",
            "qAbs(expectedX) > 2.01",
            "qAbs(expectedY) > 2.01",
            "qAbs(iconMidX - buttonMidX - expectedX) > 0.75",
            "qAbs(iconMidY - buttonMidY - expectedY) > 0.75",
            "dock optical-review offsets applied within 2px",
            "VISUAL APPROVAL STILL REQUIRED",
        ):
            self.assertIn(phrase, self.main)

    def test_source_images_remain_immutable(self):
        self.assertIn("QImageReader reader(sourcePath)", self.provider)
        self.assertIn("Qt::KeepAspectRatio", self.provider)
        self.assertIn("painter.setClipPath(outline)", self.provider)
        self.assertIn("m_images.insert(id, rendered)", self.provider)
        self.assertNotIn("QFile::remove", self.provider)
        self.assertNotIn("QImage::save", self.provider)

    def test_visual_preview_not_auto_applied_as_product_acceptance(self):
        self.assertIn("if (opticalReviewMode && !approvedMode)", self.main)
        self.assertIn("approvedMode ? ", self.main)
        self.assertNotIn("opticalReviewMode = true", self.main)
        self.assertNotIn("ShaderEffect", self.qml)


if __name__ == "__main__":
    unittest.main()
