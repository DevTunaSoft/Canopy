"""Quality controls for approved-source clean edge experiment.

The original eight PNGs and QML geometry must be byte-identical; the
candidate is generated in Qt memory once on demand, never invented artwork.
"""
from pathlib import Path
import hashlib
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "prototype" / "classic"


class CleanIconEdgesContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = (P / "main.cpp").read_text(encoding="utf-8")
        cls.provider = (P / "RoundedDockIconProvider.cpp").read_text(encoding="utf-8")
        cls.header = (P / "RoundedDockIconProvider.h").read_text(encoding="utf-8")

    def test_selected_default_and_verified_master_required(self):
        self.assertIn('args.contains(QStringLiteral("--dock-clean-edges-review"))', self.main)
        self.assertIn("if (dockCleanEdgesReviewMode && !approvedMode)", self.main)
        self.assertIn("DOCK_CLEAN_EDGES_FAIL", self.main)
        self.assertIn("dockCleanEdgesReviewModeSelected =", self.main)
        self.assertIn("approvedMode && !dockOriginalFitMode &&", self.main)
        self.assertIn("!explicitOpticalBalanceReview;", self.main)
        self.assertIn("approvedMode && explicitOpticalBalanceReview;", self.main)
        self.assertIn("if (dockOriginalFitMode && !approvedMode)", self.main)
        self.assertIn("bool cleanSourceEdgesReviewMode = false", self.header)
        self.assertIn("if (cleanSourceEdgesReviewMode && !terminalDerivative)", self.provider)
        self.assertNotIn("dockCleanEdgesReviewMode = true", self.main)

    def test_originals_read_only_no_overwrite(self):
        self.assertIn("QImageReader reader(sourcePath)", self.provider)
        self.assertIn("const QImage original = reader.read()", self.provider)
        self.assertIn('QStringLiteral(":/Canopy/Classic/assets/approved/manifest.json")',
                      self.provider)
        self.assertIn("entries.size() != 8", self.provider)
        self.assertIn("const QImage source = original.copy(", self.provider)
        self.assertNotIn("QImageWriter", self.provider)
        self.assertNotIn("QFile::remove(", self.provider)
        self.assertNotIn("QFile::rename(", self.provider)
        self.assertNotIn("original.save(", self.provider)

    def test_source_crop_only_removes_bounded_top_and_bottom_matte(self):
        trim = self.provider.split("kSourceMatteRowTrim = {")[1].split("};")[0]
        entries = re.findall(
            r'QStringLiteral\("([a-z]+)"\), \{(\d+), (\d+)\}', trim
        )
        self.assertEqual(len(entries), 8)
        self.assertEqual({x[0] for x in entries},
                         {"browser", "mail", "files", "calendar",
                          "photos", "music", "terminal", "settings"})
        for name, top, bottom in entries:
            self.assertGreaterEqual(int(top), 0)
            self.assertLessEqual(int(top), 15)
            self.assertGreaterEqual(int(bottom), 0)
            self.assertLessEqual(int(bottom), 7)
        self.assertIn("original.width() != 345", self.provider)
        self.assertIn("original.height() != 333", self.provider)
        self.assertIn("original.height() != 334", self.provider)
        self.assertIn("cropTop + cropBottom >= original.height() - 32", self.provider)

    def test_same_rounded_mask_fixed_geometry_no_runtime_cost(self):
        self.assertIn("constexpr int kCanvasPixels = 192;", self.provider)
        self.assertIn("constexpr int kInsetPixels = 12;", self.provider)
        self.assertIn("constexpr int kRoundedRadius = 36;", self.provider)
        self.assertIn("outline.addRoundedRect(face, kRoundedRadius", self.provider)
        self.assertIn("painter.setClipPath(outline)", self.provider)
        self.assertIn("const QImage edgeFill = source.scaled(", self.provider)
        self.assertIn("painter.drawImage(face, edgeFill)", self.provider)
        self.assertIn("painter.drawImage(inner, source)", self.provider)
        self.assertNotIn("QTimer", self.provider)
        self.assertNotIn("QThread", self.provider)
        self.assertNotIn("ShaderEffect", self.provider)

    def test_approved_master_sha_values_remain_exact(self):
        import json
        import subprocess
        manifest = json.loads(
            (P / "assets/approved/manifest.json").read_text()
        )
        self.assertEqual(len(manifest["icons"]), 8)
        for row in manifest["icons"]:
            current = P / "assets/approved" / row["path"]
            self.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(), row["sha256"])

    def test_no_dock_tile_qml_modifications_or_app_runtime_overrides(self):
        tile = (P / "DockTile.qml").read_text()
        self.assertIn("anchors.centerIn: parent", tile)
        self.assertIn("width: 66", tile)
        self.assertIn("height: 66", tile)
        self.assertIn("SELF_TEST_PASS: approved icon matte cleaned only inside dock", self.main)


if __name__ == "__main__":
    unittest.main()
