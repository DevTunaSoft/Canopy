"""Lightweight source contract tests; not Qt runtime tests."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"

class ClassicSourceTests(unittest.TestCase):
    def test_required_files(self):
        for name in ("CMakeLists.txt", "main.cpp", "Main.qml", "Theme.qml", "DockTile.qml", "README.md"):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())

    def test_theme_is_embedded_without_background_services(self):
        cmake = (ROOT / "CMakeLists.txt").read_text()
        qml = (ROOT / "Main.qml").read_text()
        theme = (ROOT / "Theme.qml").read_text()
        self.assertIn("Main.qml Theme.qml", cmake)
        self.assertIn("Theme { id: canopyTheme }", qml)
        self.assertNotIn("palette.", qml)
        self.assertNotIn("Timer {", qml)
        self.assertNotIn("NumberAnimation", qml)
        self.assertIn("dockSurface", theme)

    def test_classic_defaults_to_light_appearance(self):
        theme = (ROOT / "Theme.qml").read_text()
        dock = (ROOT / "DockTile.qml").read_text()
        self.assertIn('backgroundBottom: "#eef2f8"', theme)
        self.assertIn('foreground: "#273345"', theme)
        self.assertIn('chrome: "#edf6f9fc"', theme)
        self.assertIn('tile.iconName === "Home" ? "#d7e7fb"', dock)

    def test_dock_has_original_vector_artwork(self):
        cmake = (ROOT / "CMakeLists.txt").read_text()
        qml = (ROOT / "Main.qml").read_text()
        dock = (ROOT / "DockTile.qml").read_text()
        self.assertIn("DockTile.qml", cmake)
        self.assertIn("delegate: DockTile", qml)
        self.assertIn("contentItem: Canvas", dock)
        self.assertNotIn("NumberAnimation", dock)
        self.assertNotIn("Timer {", dock)
        self.assertIn('tile.iconName === "Settings"', dock)

    def test_screenshot_rejects_uniform_frames(self):
        source = (ROOT / "main.cpp").read_text()
        self.assertIn("sampledColors.size() < 8", source)
        self.assertIn("SELF_TEST_FAIL: screenshot appears blank or uniform", source)
        self.assertIn("SELF_TEST_PASS: nonuniform window screenshot captured", source)

    def test_chrome_geometry_is_runtime_verified(self):
        source = (ROOT / "main.cpp").read_text()
        qml = (ROOT / "Main.qml").read_text()
        self.assertIn('objectName: "canopyTopBar"', qml)
        self.assertIn('objectName: "canopyDock"', qml)
        self.assertIn('objectName: "canopyLauncher"', qml)
        self.assertIn("launcherFits", source)
        self.assertIn("SELF_TEST_FAIL: desktop chrome geometry invalid", source)
        self.assertIn("SELF_TEST_PASS: desktop chrome geometry", source)

    def test_explicit_nonproduction_scope(self):
        self.assertIn("not a Linux desktop session", (ROOT / "README.md").read_text())
        self.assertIn("Qt6::Quick", (ROOT / "CMakeLists.txt").read_text())
        self.assertIn("ApplicationWindow", (ROOT / "Main.qml").read_text())

if __name__ == "__main__":
    unittest.main()
