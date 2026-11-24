"""Source-level contract tests for the ported Classic Qt application.

These tests do not replace compilation, runtime screenshots or Mint acceptance.
They guard the build target, self-test contract and frozen visual constants.
"""
from pathlib import Path
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
