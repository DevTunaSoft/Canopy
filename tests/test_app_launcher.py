"""Regression contract for the Canopy Classic in-process app launcher.

These tests are source-level guards; the GitHub Qt workflow compiles and renders
the same QML in both desktop and compact screenshot modes.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AppLauncherTests(unittest.TestCase):
    def test_launcher_registered_and_wired_to_penguin(self):
        cmake = (ROOT / "prototype/classic/CMakeLists.txt").read_text()
        main = (ROOT / "prototype/classic/Main.qml").read_text()
        self.assertIn("AppLauncher.qml", cmake)
        self.assertIn("id: appLauncher", main)
        self.assertIn("onClicked: appLauncher.visible ?", main)
        self.assertIn("onFilesPreviewRequested: filesPreview.visible = true", main)

    def test_search_and_keyboard_without_background_work(self):
        qml = (ROOT / "prototype/classic/AppLauncher.qml").read_text()
        self.assertIn('objectName: "canopyAppLauncher"', qml)
        self.assertIn('objectName: "canopyLauncherSearch"', qml)
        self.assertIn("applicationNames.filter(", qml)
        self.assertIn("Keys.onEscapePressed: launcher.closeLauncher()", qml)
        self.assertIn("DockTile {", qml)
        self.assertIn("canopyApprovedMode", qml)
        self.assertNotIn("ShaderEffect", qml)
        self.assertNotIn("Timer {", qml)
        self.assertNotIn("XMLHttpRequest", qml)

    def test_runtime_checks_include_actual_launcher_icons(self):
        main = (ROOT / "prototype/classic/main.cpp").read_text()
        workflow = (ROOT / ".github/workflows/classic-qt.yml").read_text()
        self.assertIn("--self-test-launcher", main)
        self.assertIn("countReadyDockTiles(launcherOverlay) != expected", main)
        self.assertIn("SELF_TEST_PASS: searchable application launcher", main)
        self.assertIn("--self-test-launcher", workflow)


if __name__ == "__main__":
    unittest.main()
