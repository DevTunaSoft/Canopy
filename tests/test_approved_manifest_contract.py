"""Protect the exact, user-selected Classic artwork manifest.

Source-only integrity checks; these do not claim images are available or approved
runtime screenshots have been captured.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "prototype" / "classic" / "assets" / "approved"
EXPECTED_ICONS = (
    ("Browser", "Browser_Option_3.png"),
    ("Mail", "Mail_Option_5.png"),
    ("Files", "Files_Option_2.png"),
    ("Calendar", "Calendar_Option_3.png"),
    ("Photos", "Photos_Option_2.png"),
    ("Music", "Music_Option_3.png"),
    ("Terminal", "Terminal_Option_4.png"),
    ("Settings", "Settings_Option_8.png"),
)
EXPECTED_WALLPAPER = "wallpaper/canopy-wave-preview.png"


class ApprovedManifestContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))

    def test_required_exact_artwork_selection_and_order(self):
        manifest = self.manifest
        self.assertEqual(manifest["schema_version"], 1)
        icons = manifest["icons"]
        self.assertEqual(
            [(icon["name"], Path(icon["path"]).name) for icon in icons],
            list(EXPECTED_ICONS),
        )
        self.assertEqual(
            [icon["path"] for icon in icons],
            ["icons/" + filename for _, filename in EXPECTED_ICONS],
        )
        self.assertEqual(manifest["wallpaper"]["path"], EXPECTED_WALLPAPER)

    def test_checksums_and_relative_paths_are_well_formed(self):
        entries = [*self.manifest["icons"], self.manifest["wallpaper"]]
        self.assertEqual(len(entries), 9)
        paths = [entry["path"] for entry in entries]
        self.assertEqual(len(set(paths)), 9)
        for entry in entries:
            with self.subTest(path=entry["path"]):
                path = entry["path"]
                self.assertFalse(path.startswith("/"))
                self.assertNotIn(chr(92), path)
                self.assertNotIn("..", Path(path).parts)
                self.assertTrue(path.endswith(".png"))
                self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")

    def test_runtime_strict_mode_uses_manifest_without_svg_fallback(self):
        cpp = (ROOT / "prototype" / "classic" / "main.cpp").read_text(encoding="utf-8")
        dock = (ROOT / "prototype" / "classic" / "DockTile.qml").read_text(encoding="utf-8")
        wallpaper = (ROOT / "prototype" / "classic" / "Wallpaper.qml").read_text(encoding="utf-8")
        self.assertIn("verifyExactArtwork(requested, &error)", cpp)
        self.assertIn("QCryptographicHash::Sha256", cpp)
        self.assertIn("return 3;", cpp)
        self.assertIn("canopyApprovedMode", dock)
        self.assertIn("canopyApprovedIconBase + approvedFileName", dock)
        self.assertIn("canopyApprovedWallpaperUrl", wallpaper)


if __name__ == "__main__":
    unittest.main()
