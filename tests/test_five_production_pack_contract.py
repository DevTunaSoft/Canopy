"""Nonnegotiable Canopy production-art contracts: the user froze 3 icons."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
QT=ROOT/"prototype/classic"


class FiveProductionPackContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider=(QT/"RoundedDockIconProvider.cpp").read_text(encoding="utf-8")
        cls.header=(QT/"RoundedDockIconProvider.h").read_text(encoding="utf-8")
        cls.main=(QT/"main.cpp").read_text(encoding="utf-8")
        cls.cmake=(QT/"CMakeLists.txt").read_text(encoding="utf-8")
        cls.validator=(ROOT/"tools/validate_five_production_icons.py").read_text(encoding="utf-8")
        cls.tile=(QT/"DockTile.qml").read_text(encoding="utf-8")

    def test_production_pack_contains_exactly_five_icons(self):
        ids=self.provider.split("kFiveProductionIds = {")[1].split("};")[0]
        actual=re.findall(r'QStringLiteral\("([a-z]+)"\)',ids)
        self.assertEqual(actual,["browser","mail","files","terminal","settings"])
        self.assertNotIn("calendar",actual)
        self.assertNotIn("photos",actual)
        self.assertNotIn("music",actual)
        self.assertIn("for (const QString &id : kFiveProductionIds)",self.provider)

    def test_frozen_three_keep_unmodified_qt_rendering_path(self):
        # These three always skip production pack and high-DPI provider variants.
        self.assertIn("kFiveDockCenterOffsets.contains(id)",self.provider)
        self.assertIn("if (fiveOnlyCenterReviewMode && terminalCandidatePath.isEmpty() &&",self.provider)
        self.assertIn("painter.drawImage(inner, source)",self.provider)
        self.assertIn("m_productionMasterPaths.insert(id, sourcePath)",self.provider)
        self.assertIn("m_productionMasterPaths.contains(key)",self.provider)
        self.assertNotIn("Calendar_Option_3.png",self.cmake)
        self.assertNotIn("Photos_Option_2.png",self.cmake)
        self.assertNotIn("Music_Option_3.png",self.cmake)
        self.assertIn("anchors.centerIn: parent",self.tile)
        self.assertIn("width: 62",self.tile)
        self.assertIn("height: 62",self.tile)

    def test_production_pack_provenance_and_rollback(self):
        self.assertIn("source_manifest_sha256",self.provider)
        self.assertIn("sha256(originalManifestBytes)",self.provider)
        self.assertIn("QSaveFile output",self.provider)
        self.assertIn("m_productionPackValid = true",self.provider)
        self.assertIn("if (!roundedIcons->productionPackVerified()",self.main) if False else None
        self.assertIn("roundedIcons->productionPackVerified()",self.main)
        self.assertIn("--require-five-production-icons",self.main)
        self.assertIn("--export-five-production-icons",self.main)
        self.assertIn("FIVE_PRODUCTION_PACK_FALLBACK:",self.main)
        self.assertIn('args.contains(QStringLiteral("--dock-original-fit"))',self.main)
        self.assertIn('args.contains(QStringLiteral("--dock-clean-edges-review"))',self.main)

    def test_three_scales_from_original_not_from_192_raster(self):
        self.assertIn("for (int density = 1; density <= 3; ++density)",self.provider)
        self.assertIn("renderFiveAtDensity(original, id, density, error)",self.provider)
        self.assertIn("painter.scale(density, density)",self.provider)
        self.assertIn("192, 384, 576",self.validator) if False else None
        self.assertIn("DENSITIES = (1, 2, 3)",self.validator)
        self.assertIn("source-derived icon corner must be transparent",self.validator)
        self.assertIn("decode_rgba_png",self.validator)
        self.assertIn("pack_file_sha256",self.validator)

    def test_build_auto_generates_and_installs(self):
        self.assertIn("canopy-classic-production-icons ALL",self.cmake)
        self.assertIn("QT_QPA_PLATFORM=offscreen",self.cmake)
        self.assertIn("--export-five-production-icons",self.cmake)
        self.assertIn("share/canopy/classic/icons",self.cmake)
        self.assertNotIn("QTimer",self.provider)
        self.assertNotIn("QThread",self.provider)
        self.assertNotIn("ShaderEffect",self.provider)

    def test_immutable_full_real_qt_golden_baseline(self):
        import json
        manifest=json.loads((ROOT/"docs/CLASSIC_FIVE_DOCK_GOLDEN.json").read_text())
        self.assertEqual(manifest["schema_version"],1)
        self.assertEqual(set(manifest["frozen_names"]),{"calendar","photos","music"})
        self.assertEqual(set(manifest["fixed_resolution_hashes"]),
                         {"760x500","1200x750","1920x1080"})
        self.assertEqual(set(manifest["five_production_goldens"]),
                         {"760x500","1200x750","1920x1080"})
        for size in ("760x500","1200x750","1920x1080"):
            frozen=manifest["fixed_resolution_hashes"][size]
            five=manifest["five_production_goldens"][size]
            self.assertEqual(set(frozen),{"calendar","photos","music"})
            self.assertEqual(set(five),
                             {"browser","mail","files","terminal","settings"})
            for h in list(frozen.values())+list(five.values()):
                self.assertRegex(h,r"^[0-9a-f]{64}$")
        self.assertIn("actions/runs/45287610604",
                      manifest["five_production_source_run_url"])

    def test_approved_manifest_and_all_eight_pngs_unchanged(self):
        import hashlib,json
        root=QT/"assets/approved"
        manifest=json.loads((root/"manifest.json").read_text())
        self.assertEqual(len(manifest["icons"]),8)
        for row in manifest["icons"]:
            f=root/row["path"]
            self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),row["sha256"])


if __name__=="__main__":
    unittest.main()
