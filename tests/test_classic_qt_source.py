"""Source-level contract tests for the ported Classic Qt application.

These tests do not replace compilation, runtime screenshots or Mint acceptance.
They guard the build target, self-test contract and frozen visual constants.
"""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools import check_screenshot

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic"


class ClassicQtSourceTests(unittest.TestCase):
    def test_cmake_declares_real_qt6_executable(self):
        text = (SOURCE / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("cmake_minimum_required(VERSION 3.21)", text)
        self.assertIn("find_package(Qt6 6.4 REQUIRED", text)
        self.assertIn("RoundedDockIconProvider.cpp", text)
        self.assertIn("qt_add_resources", text)
        for qml in ("Main.qml", "Theme.qml", "DockTile.qml", "ClockLabel.qml",
                    "LauncherOverlay.qml", "PreviewWindow.qml", "Wallpaper.qml",
                    "FolderTile.qml"):
            self.assertIn(qml, text)

    def test_main_has_runtime_and_screenshot_contract(self):
        text = (SOURCE / "main.cpp").read_text(encoding="utf-8")
        for marker in ("CANOPY_CLASSIC_WINDOW_READY", "--self-test-size",
                       "--self-test-screenshot", "SELF_TEST_PASS", "grabWindow()",
                       "frame.save(screenshotPath", "QCoreApplication::quit()"):
            self.assertIn(marker, text)

    def test_frozen_visual_constants_are_unchanged(self):
        text = (SOURCE / "Theme.qml").read_text(encoding="utf-8")
        # Owner-approved 32/96/14/7 geometry restored at base fef38c31.
        for constant in ("barHeight: 32", "dockSize: 96", "tileSize: 52",
                         "cornerRadius: 24", "dockSpacing: 7", "dockPadding: 14"):
            self.assertIn(constant, text)
        main = (SOURCE / "Main.qml").read_text(encoding="utf-8")
        for name in ("canopyTopBar", "canopyDock", "canopyLauncher"):
            self.assertIn(name, main)
        for icon in ("Browser", "Mail", "Files", "Calendar", "Photos", "Music",
                     "Terminal", "Settings"):
            self.assertIn('title: "' + icon + '"', main)

    def test_approved_artwork_matches_locked_manifest(self):
        from tools.prepare_approved_art import check_exact, read_manifest
        manifest = read_manifest()
        base = SOURCE / "assets" / "approved"
        for entry in [*manifest["icons"], manifest["wallpaper"]]:
            check_exact(base / entry["path"], entry["sha256"])

    def test_restored_geometry_leaves_approved_visual_blobs_unchanged(self):
        """Two-line Theme.qml restoration must not touch any approved art."""
        pinned = {
            # Manifest and the eight approved icon PNGs.
            "prototype/classic/assets/approved/manifest.json":
                "b120dc891a614ddbc5ef863514424112c02efee6",
            "prototype/classic/assets/approved/icons/Browser_Option_3.png":
                "1f2739b56bae3374223f52a6c64a17b1388bbc87",
            "prototype/classic/assets/approved/icons/Calendar_Option_3.png":
                "484f16165fd49280a96a19ec7966d1624d801616",
            "prototype/classic/assets/approved/icons/Files_Option_2.png":
                "03a67d1515b15c7db7e2cf41b53a7b6de9164aae",
            "prototype/classic/assets/approved/icons/Mail_Option_5.png":
                "37ac1e8b0301f782daa3b64079fdb867dc783046",
            "prototype/classic/assets/approved/icons/Music_Option_3.png":
                "bba53550523a2588c208ab5aa753e7e78b020d3d",
            "prototype/classic/assets/approved/icons/Photos_Option_2.png":
                "158d30018b938ce46ea5849b442d07ed9f7b7e5d",
            "prototype/classic/assets/approved/icons/Settings_Option_8.png":
                "41c678a2d5a797a5c454ea9edc925de98859f1ec",
            "prototype/classic/assets/approved/icons/Terminal_Option_4.png":
                "3ba31680bc21eee25cc5442baf9f984d4388ea29",
            # Both wallpaper copies carried by the integration tree.
            "prototype/classic/assets/approved/wallpaper/"
            "Canopy_Classic_Master_Wallpaper_1920x1080.png":
                "2802e690e1a7d0f16336b90a456dbaea9f5f014d",
            "prototype/classic/assets/approved/wallpaper/"
            "canopy-wave-preview.png":
                "38a5243c55316729194e4a72ec0b57b28e47d28f",
            "prototype/classic/assets/wallpapers/"
            "Canopy_Classic_Master_Wallpaper_1920x1080.png":
                "2802e690e1a7d0f16336b90a456dbaea9f5f014d",
        }

        def committed_blob_sha1(relative):
            # Read committed bytes, not CRLF-converted working-tree bytes.
            content = subprocess.check_output(
                ["git", "-C", str(ROOT), "show", "HEAD:" + relative])
            return hashlib.sha1(
                b"blob " + str(len(content)).encode() + b"\0" + content
            ).hexdigest()

        for relative, expected in pinned.items():
            with self.subTest(path=relative):
                self.assertEqual(committed_blob_sha1(relative), expected)

    def test_workflow_captures_three_resolutions_and_five_minute_sample(self):
        text = (ROOT / ".github" / "workflows" / "classic-qt.yml").read_text(encoding="utf-8")
        for resolution in ("1920x1080", "1200x750", "760x500"):
            self.assertIn(resolution, text)
        self.assertIn("--seconds 300", text)
        self.assertIn("cmake --build build/classic", text)
        self.assertNotIn("merge", text.lower())

    def test_screenshot_validator_rejects_fake_png(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.png"
            path.write_bytes(b"not a png")
            with self.assertRaises(ValueError):
                check_screenshot.verify_png(path, 1200, 750)


if __name__ == "__main__":
    unittest.main()
