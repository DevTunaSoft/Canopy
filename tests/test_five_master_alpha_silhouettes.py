"""Do not regress the five approved-source alpha cutouts or frozen trio."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"prototype"/"classic"


class FiveSourceAlphaContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider=(SOURCE/"RoundedDockIconProvider.cpp").read_text(encoding="utf-8")
        cls.validator=(ROOT/"tools"/"validate_five_production_icons.py").read_text(encoding="utf-8")

    def test_exactly_five_contours_not_three_frozen_icons(self):
        table=self.provider.split("kFiveMasterContours = {")[1].split("};")[0]
        ids=re.findall(r'QStringLiteral\("([a-z]+)"\)',table)
        self.assertEqual(set(ids),{"browser","mail","files","terminal","settings"})
        self.assertEqual(len(ids),5)
        for frozen in ("calendar","photos","music"):
            self.assertNotIn(f'QStringLiteral("{frozen}")',table)

    def test_asymmetric_mask_preserves_art_and_penguin(self):
        s=self.provider
        self.assertIn("QImage alphaCutoutMaster(",s)
        self.assertIn("QPainterPath outline;",s)
        self.assertIn("outline.quadTo(c.x1, c.y0",s)
        self.assertIn("outline.quadTo(c.x1, c.y1",s)
        self.assertIn("outline.quadTo(c.x0, c.y1",s)
        self.assertIn("outline.quadTo(c.x0, c.y0",s)
        self.assertIn("QPainter::CompositionMode_DestinationIn",s)
        self.assertIn("alpha.fill(Qt::transparent);",s)
        self.assertIn("cutout.pixelColor(0, 0).alpha()",s)
        self.assertIn("const QImage source = alphaCutoutMaster(original, id, error)",s)
        self.assertIn("const QRectF inner(face.left() + 1",s)
        self.assertIn("painter.drawImage(artwork, source)",s)
        self.assertIn("painter.setClipPath(outline)",s)
        self.assertNotIn("QImageWriter",s)

    def test_pack_version_invalidates_all_previous_mattes(self):
        self.assertIn('kPackRenderer = "canopy-five-qt-v3-alpha"',self.provider)
        self.assertIn('EXPECTED_RENDERER = "canopy-five-qt-v3-alpha"',self.validator)
        self.assertIn("sha256(originalManifestBytes)",self.provider)
        self.assertIn("m_productionPackValid = true",self.provider)
        self.assertIn("renderFiveAtDensity(original, id, density, error)",self.provider)

    def test_original_eight_masters_sha_locked(self):
        root=SOURCE/"assets"/"approved"
        manifest=json.loads((root/"manifest.json").read_text())
        self.assertEqual(len(manifest["icons"]),8)
        for row in manifest["icons"]:
            current=root/row["path"]
            self.assertEqual(hashlib.sha256(current.read_bytes()).hexdigest(),row["sha256"])

    def test_no_frozen_three_or_dock_geometry_edit_from_provider(self):
        self.assertIn("if (fiveOnlyCenterReviewMode && terminalCandidatePath.isEmpty() &&",self.provider)
        self.assertIn("kFiveDockCenterOffsets.contains(id)",self.provider)
        self.assertIn("painter.drawImage(inner, source)",self.provider)
        self.assertEqual(self.provider.count("alphaCutoutMaster(original, id, error)"),1)


if __name__=="__main__":
    unittest.main()
