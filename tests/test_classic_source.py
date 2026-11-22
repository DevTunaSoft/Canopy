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
        self.assertIn('chrome: "#ed1f2326"', theme)
        self.assertIn('source: tile.iconUrl', dock)

    def test_dock_has_original_vector_artwork(self):
        cmake = (ROOT / "CMakeLists.txt").read_text()
        qml = (ROOT / "Main.qml").read_text()
        dock = (ROOT / "DockTile.qml").read_text()
        self.assertIn("DockTile.qml", cmake)
        self.assertIn("delegate: DockTile", qml)
        self.assertIn("contentItem: Item", dock)
        self.assertIn("Image {", dock)
        self.assertIn("readonly property bool iconReady", dock)
        self.assertIn('objectName: "canopyDockIcon"', dock)
        self.assertIn("source: tile.iconUrl", dock)
        self.assertNotIn("Canvas {", dock)
        self.assertIn('iconName.toLowerCase()', dock)
        self.assertIn('assets/icons/', dock)
        self.assertNotIn("NumberAnimation", dock)
        self.assertNotIn("Timer {", dock)
        self.assertIn('ToolTip.text: iconName === "Files" ? "Toggle Files preview" : iconName + " — preview only"', dock)

    def test_files_dock_button_toggles_preview_without_launching_apps(self):
        dock = (ROOT / "DockTile.qml").read_text()
        desktop = (ROOT / "Main.qml").read_text()
        self.assertIn("signal activated(string applicationName)", dock)
        self.assertIn("onClicked: tile.activated(tile.iconName)", dock)
        self.assertIn('if (applicationName === "Files")', desktop)
        self.assertIn("filesPreview.visible = !filesPreview.visible", desktop)
        self.assertIn('previewActive: modelData.title === "Files" && filesPreview.visible', desktop)
        self.assertNotIn('QProcess', (ROOT / "main.cpp").read_text())

    def test_runtime_dock_toggle_is_checked_in_screenshot_smoke(self):
        cpp = (ROOT / "main.cpp").read_text()
        self.assertIn('findDockTile(dock, QStringLiteral("Files"))', cpp)
        self.assertIn('QMetaObject::invokeMethod(filesTile, "clicked", Qt::DirectConnection)', cpp)
        self.assertIn('SELF_TEST_FAIL: Files dock did not hide preview', cpp)
        self.assertIn('SELF_TEST_FAIL: Files dock did not restore preview', cpp)
        self.assertIn('SELF_TEST_PASS: Files dock hide/restore and activity indicator', cpp)

    def test_preview_close_button_and_dock_reopen_runtime_gate(self):
        window = (ROOT / "PreviewWindow.qml").read_text()
        cpp = (ROOT / "main.cpp").read_text()
        self.assertIn('objectName: "canopyPreviewClose"', window)
        self.assertIn('Accessible.name: "Close Files preview"', window)
        self.assertIn("onClicked: preview.visible = false", window)
        self.assertIn('findVisualItem(preview, QStringLiteral("canopyPreviewClose"))', cpp)
        self.assertIn('SELF_TEST_PASS: Files close control and dock reopen', cpp)
        self.assertIn('SELF_TEST_FAIL: Files preview failed to reopen after close', cpp)

    def test_keyboard_shortcut_bindings_and_runtime_gate(self):
        qml = (ROOT / "Main.qml").read_text()
        runtime = (ROOT / "main.cpp").read_text()
        self.assertIn('objectName: "canopyFilesCloseShortcut"', qml)
        self.assertIn('sequence: "Ctrl+W"', qml)
        self.assertIn('objectName: "canopyFilesOpenShortcut"', qml)
        self.assertIn('sequence: "Ctrl+Shift+F"', qml)
        self.assertIn('SELF_TEST_PASS: Files keyboard close and reopen bindings', runtime)

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
        self.assertIn("root.width * 0.56", desktop)
        self.assertIn("root.height * 0.56", desktop)
        self.assertIn("canopyTheme.barHeight - 166", desktop)
        self.assertIn('not a filesystem browser', window)
        self.assertIn('FolderTile {', window)
        self.assertIn('objectName: "canopyPreviewSearch"', window)
        self.assertIn('onClicked: preview.selectedFolder = folderName', window)
        self.assertIn('No local files are loaded in this preview.', window)
        self.assertIn('objectName: "canopyFolderScroller"', window)
        self.assertIn('objectName: "canopySidebarScroller"', window)
        self.assertIn('name: "Templates"', window)
        self.assertIn('name: "Public"', window)
        self.assertIn('"Recent", "Starred", "Home", "Desktop", "Documents"', window)
        self.assertIn('assets/ui/folder-blue.svg', cmake)
        self.assertIn("ScrollBar.vertical: ScrollBar", window)
        self.assertIn("clip: true", window)
        self.assertIn("contentHeight: Math.max(height, folders.height + 10)", window)
        self.assertIn("height: childrenRect.height", window)
        self.assertIn("policy: ScrollBar.AsNeeded", window)
        tiles = (ROOT / "FolderTile.qml").read_text()
        # Compact Files cards must fit two rows without a forced scrollbar.
        self.assertIn("compact: preview.condensed", window)
        self.assertIn("height: compact ? 68 : 90", tiles)
        # A four-column cap prevents the 1920x1080 7+1 orphan row.
        self.assertIn("width: Math.min(folderScroller.width - 13", window)
        self.assertIn('objectName: "canopyFolderFlow"', window)
        self.assertIn("const bool fourColumnGrid = folderFlow", (ROOT / "main.cpp").read_text())

        self.assertIn("4 * 108 + 3 * (preview.condensed ? 6 : 10)", window)
        self.assertIn("Accessible.description:", tiles)
        self.assertIn("source: \"qrc:/Canopy/Classic/assets/ui/folder-blue.svg\"", tiles)
        self.assertIn("readonly property bool imageReady", tiles)
        self.assertNotIn("gradient: Gradient", tiles)
        self.assertNotIn("Canvas {", tiles)
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
        self.assertIn("canopyApprovedMode ? canopyApprovedWallpaperUrl", wallpaper)
        self.assertIn('"qrc:/Canopy/Classic/assets/wallpapers/blue-current.svg"', wallpaper)
        self.assertIn('readonly property bool imageReady', wallpaper)
        self.assertNotIn("Canvas {", wallpaper)
        self.assertIn('qt_add_resources(canopy-classic-spike "canopy-original-art"', cmake)
        self.assertIn("assets/wallpapers/blue-current.svg", cmake)
        self.assertNotIn("Timer {", wallpaper)
        self.assertNotIn("NumberAnimation", wallpaper)
        self.assertNotIn("ShaderEffect", wallpaper)
        self.assertIn('title: "Browser"', desktop)
        self.assertIn('title: "Terminal"', desktop)
        self.assertIn('title: "Trash"', desktop)
        self.assertIn('title: "Mail"', desktop)
        self.assertIn('title: "Calendar"', desktop)
        self.assertIn('title: "Music"', desktop)
        self.assertIn('approvedAssetsActive: canopyApprovedMode', desktop)
        self.assertIn('model: canopyApprovedMode', desktop)
        self.assertNotIn('title: "Canopy"', desktop)
        self.assertIn('previewActive: modelData.title === "Files"', desktop)
        runtime = (ROOT / "main.cpp").read_text()
        self.assertIn("SELF_TEST_PASS: original wallpaper and six dock icon candidates present", runtime)
        self.assertIn("SELF_TEST_FAIL: wallpaper bounds or dock icon count invalid", runtime)
        self.assertIn("countVisualItems", runtime)
        self.assertIn("parent->childItems()", runtime)
        self.assertIn("SELF_TEST_PASS: eight demo folders and one search control present", runtime)
        self.assertIn("SELF_TEST_FAIL: sample Files preview content incomplete", runtime)
        self.assertIn("SELF_TEST_PASS: wallpaper regions visually distinct", runtime)
        self.assertIn("SELF_TEST_FAIL: Blue Current wallpaper image did not load", runtime)
        self.assertIn("SELF_TEST_PASS: original SVG wallpaper image loaded", runtime)
        self.assertIn("SELF_TEST_PASS: all six SVG dock candidates loaded", runtime)
        self.assertIn("SELF_TEST_PASS: all eight original sample folder images loaded", runtime)
        self.assertIn("SELF_TEST_PASS: compact folder grid fits and four-column cap verified", runtime)
        self.assertIn("SELF_TEST_FAIL: Files folder grid clipped or unbalanced", runtime)
        self.assertIn("SELF_TEST_FAIL: folder artwork did not load", runtime)
        self.assertIn("SELF_TEST_FAIL: original dock artwork failed to load", runtime)
        self.assertIn("countReadyDockTiles", runtime)
        for icon in ("files", "browser", "photos", "settings",
                     "terminal", "trash"):
            self.assertIn(f"assets/icons/{icon}.svg", cmake)
            self.assertTrue((ROOT / f"assets/icons/{icon}.svg").is_file())
        self.assertIn('objectName: "canopyFolderTile"', (ROOT / "FolderTile.qml").read_text())
        self.assertNotIn("dock->findChildren<QQuickItem *>", runtime)

    def test_menu_bar_actions_are_real_files_interface_calls(self):
        menus = (ROOT / "ShellMenuBar.qml").read_text()
        main = (ROOT / "Main.qml").read_text()
        for title in ("File", "Edit", "View", "Go", "Window", "Help"):
            self.assertIn('title: "' + title + '"', menus)
        for action in ("requestClose()", "setSearch(", "goBack()", "goUp()",
                       "showLauncherRequested()", "aboutRequested()"):
            self.assertIn(action, menus)
        self.assertIn("property var filesWindow: null", menus)
        self.assertIn("ShellMenuBar {", main)
        self.assertIn("filesWindow: filesPreview", main)
        self.assertIn("onClosed: filesPreview.visible = false", main)
        self.assertIn("sequence: \"Ctrl+W\"", main)
        self.assertIn('title: "Canopy Classic Preview"', main)
        self.assertIn("width: 360", main)
        self.assertIn("implicitWidth: 290", main)
        self.assertNotIn("Timer {", main)
        self.assertNotIn("selectedFolder = \"\"", main)

    def test_screenshot_rejects_uniform_frames(self):
        source = (ROOT / "main.cpp").read_text()
        self.assertIn("sampledColors.size() < 8", source)
        self.assertIn("SELF_TEST_FAIL: screenshot appears blank or uniform", source)
        self.assertIn("SELF_TEST_PASS: nonuniform window screenshot captured", source)

    def test_wallpaper_visual_gate_samples_both_unobscured_edges(self):
        source = (ROOT / "main.cpp").read_text()
        self.assertIn("QVector<QRgb> wallpaperSamples", source)
        self.assertIn("frame.width() - edgeX - 1", source)
        self.assertIn("maxArtworkDifference", source)
        self.assertIn('SELF_TEST_FAIL: wallpaper regions unexpectedly uniform', source)

    def test_chrome_geometry_is_runtime_verified(self):
        source = (ROOT / "main.cpp").read_text()
        qml = (ROOT / "Main.qml").read_text()
        self.assertIn('objectName: "canopyTopBar"', qml)
        self.assertIn('objectName: "canopyDock"', qml)
        self.assertIn('objectName: "canopyLauncher"', qml)
        self.assertIn('assets/brand/penguin-launcher.svg', qml)
        self.assertIn('onClicked: launcherMenu.open()', qml)
        self.assertIn('readonly property bool imageReady: penguinArt.status === Image.Ready', qml)
        self.assertIn("launcherFits", source)
        self.assertIn("SELF_TEST_FAIL: desktop chrome geometry invalid", source)
        self.assertIn("SELF_TEST_FAIL: original Canopy launcher icon did not load", source)
        self.assertIn("SELF_TEST_PASS: original Canopy penguin launcher loaded", source)
        self.assertIn("SELF_TEST_PASS: desktop chrome geometry", source)

    def test_explicit_nonproduction_scope(self):
        self.assertIn("not a Linux desktop session", (ROOT / "README.md").read_text())
        self.assertIn("Qt6::Quick", (ROOT / "CMakeLists.txt").read_text())
        self.assertIn("ApplicationWindow", (ROOT / "Main.qml").read_text())

if __name__ == "__main__":
    unittest.main()
