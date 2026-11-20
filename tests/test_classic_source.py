"""Lightweight source contract tests; not Qt runtime tests."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"

class ClassicSourceTests(unittest.TestCase):
    def test_required_files(self):
        for name in ("CMakeLists.txt", "main.cpp", "Main.qml", "Theme.qml", "DockTile.qml", "PreviewWindow.qml", "Landscape.qml", "LauncherOverlay.qml", "README.md"):
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
        self.assertIn('chrome: "#dd090f2d"', theme)
        self.assertIn('iconName === "Browser" ? "#2385ef"', dock)
        self.assertIn('gradient: Gradient', dock)

    def test_dock_has_original_vector_artwork(self):
        cmake = (ROOT / "CMakeLists.txt").read_text()
        qml = (ROOT / "Main.qml").read_text()
        dock = (ROOT / "DockTile.qml").read_text()
        self.assertIn("DockTile.qml", cmake)
        self.assertIn("delegate: DockTile", qml)
        self.assertIn("contentItem: Canvas", dock)
        self.assertIn("NOT the user-approved high-detail icon artwork", dock)
        self.assertNotIn("NumberAnimation", dock)
        self.assertNotIn("Timer {", dock)
        self.assertIn('tile.iconName === "Settings"', dock)
        for icon in ("Browser", "Mail", "Files", "Calendar", "Photos", "Music", "Terminal", "Settings"):
            with self.subTest(icon=icon):
                self.assertIn('tile.iconName === "' + icon + '"', dock)
        for icon in ("Browser", "Mail", "Files", "Calendar", "Photos", "Music", "Terminal", "Settings"):
            self.assertIn('{ name: "' + icon + '", icon: "' + icon + '" }', qml)
        self.assertNotIn("roundedRect(", dock)
        self.assertIn("model: root.classicApps", qml)
        self.assertIn("applications: root.classicApps", qml)
        self.assertIn('objectName: "canopyDockRepeater"', qml)
        self.assertIn("resultCount: filteredApps.length", (ROOT / "LauncherOverlay.qml").read_text())
        runtime = (ROOT / "main.cpp").read_text()
        self.assertIn("SELF_TEST_FAIL: Classic approved application catalog mismatch", runtime)
        self.assertIn("SELF_TEST_PASS: Classic eight-app dock and launcher catalog", runtime)
        self.assertIn("property var applications: []", (ROOT / "LauncherOverlay.qml").read_text())
        self.assertNotIn('{ title: "Notes" }', qml)
        self.assertNotIn('{ title: "Search" }', qml)


    def test_original_wallpaper_is_static(self):
        cmake = (ROOT / "CMakeLists.txt").read_text()
        desktop = (ROOT / "Main.qml").read_text()
        landscape = (ROOT / "Landscape.qml").read_text()
        self.assertIn("Landscape.qml", cmake)
        self.assertIn("Landscape {", desktop)
        self.assertIn('objectName: "canopyLandscape"', landscape)
        self.assertIn('function ribbon(points, colors)', landscape)
        self.assertIn('base.addColorStop(0, "#090c36")', landscape)
        self.assertNotIn("Timer {", landscape)
        self.assertNotIn("NumberAnimation", landscape)
        self.assertNotIn("ShaderEffect", landscape)

    def test_reference_locked_visual_reset(self):
        design = (ROOT.parents[1] / "docs" / "CLASSIC_VISUAL_RESET_REFERENCE.md").read_text()
        qml = (ROOT / "Main.qml").read_text()
        files = (ROOT / "PreviewWindow.qml").read_text()
        self.assertIn("Mockup 2", design)
        self.assertIn("Mockup 1", design)
        self.assertIn('text: "Window"', qml)
        self.assertIn('text: "Help"', qml)
        self.assertIn('columns: preview.compact ? 2 : 4', files)
        self.assertIn('color: "#eeeafa"', files)
        self.assertNotIn("Timer {", files)

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
        self.assertIn('not a functional file manager', window)
        self.assertNotIn("Timer {", window)
        self.assertNotIn("NumberAnimation", window)

    def test_files_toolbar_is_preview_only_and_responsive(self):
        window = (ROOT / "PreviewWindow.qml").read_text()
        self.assertIn('objectName: "canopyFilesToolbar"', window)
        self.assertIn('anchors.top: contentToolbar.bottom', window)
        self.assertIn('visible: !preview.compact', window)
        self.assertIn('not interactive', window)
        self.assertNotIn("Timer {", window)
        self.assertNotIn("NumberAnimation", window)

    def test_low_cost_static_surface_depth(self):
        qml = (ROOT / "Main.qml").read_text()
        self.assertIn('anchors.fill: filesPreview', qml)
        self.assertIn('z: 0.3', qml)
        self.assertNotIn("ShaderEffect {", qml)
        self.assertNotIn("GaussianBlur {", qml)
        self.assertNotIn("MultiEffect {", qml)

    def test_full_hd_screenshot_is_required(self):
        workflow = (ROOT.parents[1] / ".github" / "workflows" / "classic-qt.yml").read_text()
        self.assertIn("classic-fullhd.png", workflow)
        self.assertIn("--self-test-size 1920x1080", workflow)

    def test_launcher_is_interactive_but_never_executes_commands(self):
        desktop = (ROOT / "Main.qml").read_text()
        launcher = (ROOT / "LauncherOverlay.qml").read_text()
        cmake = (ROOT / "CMakeLists.txt").read_text()
        self.assertIn("LauncherOverlay.qml", cmake)
        self.assertIn("LauncherOverlay {", desktop)
        self.assertIn('sequence: "Ctrl+Space"', desktop)
        self.assertIn('objectName: "canopyApplicationLauncher"', launcher)
        self.assertIn('objectName: "canopyLauncherSearch"', launcher)
        self.assertIn('objectName: "canopyLauncherGrid"', launcher)
        self.assertIn('onCloseRequested: root.launcherOpen = false', desktop)
        self.assertIn('filteredApps: applications.filter', launcher)
        self.assertNotIn("Timer {", launcher)
        self.assertNotIn("NumberAnimation", launcher)
        self.assertNotIn("QProcess", launcher)
        self.assertIn("visible: !root.launcherOpen", desktop)
        self.assertIn("cellHeight: panel.height < 360 ? 64 : 110", launcher)
        self.assertIn("height: Math.min(parent.height - 170, 405)", launcher)

    def test_search_is_validated_from_live_qt_not_only_qml_source(self):
        source = (ROOT / "main.cpp").read_text()
        workflow = (ROOT.parents[1] / ".github" / "workflows" / "classic-qt.yml").read_text()
        self.assertIn('QStringLiteral("--self-test-search")', source)
        self.assertIn("SELF_TEST_PASS: Classic live application search", source)
        self.assertIn("SELF_TEST_FAIL: Classic live application search", source)
        self.assertIn('QStringLiteral("mUsIc")', source)
        self.assertIn('QStringLiteral("zz-canopy-no-match")', source)
        self.assertIn("--self-test-search --self-test-screenshot", workflow)
        self.assertIn("classic-search-standard.png", workflow)

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
