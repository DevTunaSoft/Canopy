"""Lightweight source contract tests; not Qt runtime tests."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"

class ClassicSourceTests(unittest.TestCase):
    def test_required_files(self):
        for name in ("CMakeLists.txt", "main.cpp", "Main.qml", "Theme.qml", "DockTile.qml", "PreviewWindow.qml", "Wallpaper.qml", "FolderTile.qml", "README.md"):
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
        self.assertIn('iconName === "Home" ? "#72b5e8"', dock)

    def test_dock_has_original_vector_artwork(self):
        cmake = (ROOT / "CMakeLists.txt").read_text()
        qml = (ROOT / "Main.qml").read_text()
        dock = (ROOT / "DockTile.qml").read_text()
        self.assertIn("DockTile.qml", cmake)
        self.assertIn("delegate: DockTile", qml)
        self.assertIn("contentItem: Item", dock)
        self.assertIn("Canvas {", dock)
        self.assertIn('iconName === "Photos"', dock)
        self.assertIn('iconName === "Calendar"', dock)
        self.assertNotIn("NumberAnimation", dock)
        self.assertNotIn("Timer {", dock)
        self.assertIn('tile.iconName === "Settings"', dock)

    def test_representative_preview_is_included(self):
        cmake = (ROOT / "CMakeLists.txt").read_text()
        desktop = (ROOT / "Main.qml").read_text()
        window = (ROOT / "PreviewWindow.qml").read_text()
        self.assertIn("PreviewWindow.qml", cmake)
        self.assertIn("PreviewWindow {", desktop)
        self.assertIn('objectName: "canopyPreviewWindow"', window)
        cpp = (ROOT / "main.cpp").read_text()
        self.assertIn("SELF_TEST_PASS: preview window fits above dock", cpp)
        self.assertIn("SELF_TEST_FAIL: preview overlaps desktop chrome or is too small", cpp)
        self.assertIn("previewOrigin.y() + preview->height() <= dockOrigin.y() - 12", cpp)
        self.assertIn("canopyTheme.barHeight - 148, 420", desktop)
        self.assertIn('not a filesystem browser', window)
        self.assertIn('FolderTile {', window)
        self.assertIn('objectName: "canopyPreviewSearch"', window)
        self.assertIn('onClicked: preview.selectedFolder = folderName', window)
        self.assertIn('No local files are loaded in this preview.', window)
        tiles = (ROOT / "FolderTile.qml").read_text()
        self.assertIn("Accessible.description:", tiles)
        self.assertNotIn("Timer {", tiles)
        self.assertNotIn("Timer {", window)
        self.assertNotIn("NumberAnimation", window)

    def test_original_wallpaper_replaces_geometric_placeholders(self):
        cmake = (ROOT / "CMakeLists.txt").read_text()
        desktop = (ROOT / "Main.qml").read_text()
        wallpaper = (ROOT / "Wallpaper.qml").read_text()
        self.assertIn("Wallpaper.qml", cmake)
        self.assertIn("Wallpaper { anchors.fill: parent }", desktop)
        self.assertNotIn("root.width * 1.04", desktop)
        self.assertNotIn("root.width * 0.83", desktop)
        self.assertIn('objectName: "canopyWallpaper"', wallpaper)
        self.assertIn("renderTarget: Canvas.Image", wallpaper)
        self.assertNotIn("Timer {", wallpaper)
        self.assertNotIn("NumberAnimation", wallpaper)
        self.assertNotIn("ShaderEffect", wallpaper)
        self.assertIn('title: "Browser"', desktop)
        self.assertIn('title: "Calendar"', desktop)
        self.assertIn('previewActive: modelData.title === "Files"', desktop)
        runtime = (ROOT / "main.cpp").read_text()
        self.assertIn("SELF_TEST_PASS: original wallpaper and seven dock icons present", runtime)
        self.assertIn("SELF_TEST_FAIL: wallpaper bounds or dock icon count invalid", runtime)
        self.assertIn("countVisualItems", runtime)
        self.assertIn("parent->childItems()", runtime)
        self.assertIn("SELF_TEST_PASS: six demo folders and one search control present", runtime)
        self.assertIn("SELF_TEST_FAIL: sample Files preview content incomplete", runtime)
        self.assertIn("SELF_TEST_PASS: wallpaper sky and foreground visually distinct", runtime)
        self.assertIn('objectName: "canopyFolderTile"', (ROOT / "FolderTile.qml").read_text())
        self.assertNotIn("dock->findChildren<QQuickItem *>", runtime)

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
