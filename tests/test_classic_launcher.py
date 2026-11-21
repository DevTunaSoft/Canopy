"""Regression contracts for the isolated Qt Classic application search.

Source checks supplement, but do not replace, the compiled Qt screenshot
self-test that invokes the actual QML launcher and search binding.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"


class ClassicLauncherContracts(unittest.TestCase):
    def test_qml_compiles_into_existing_module(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        main = (ROOT / "Main.qml").read_text(encoding="utf-8")
        self.assertEqual(cmake.count("LauncherOverlay.qml"), 1)
        self.assertIn("LauncherOverlay {", main)
        self.assertIn("approvedMode: root.approvedAssetsActive", main)

    def test_preserves_original_catalog_for_approved_mode(self):
        code = (ROOT / "LauncherOverlay.qml").read_text(encoding="utf-8")
        for name in ("Browser", "Mail", "Files", "Calendar", "Photos",
                     "Music", "Terminal", "Settings"):
            self.assertIn('{ title: "' + name + '" }', code)
        self.assertIn("readonly property int catalogCount:", code)
        self.assertIn("readonly property int filteredCount:", code)
        self.assertIn('objectName: "canopyLauncherSearch"', code)
        self.assertIn('objectName: "canopyApplicationLauncher"', code)
        self.assertIn('"image://canopy-dock/" + appButton.modelData.title.toLowerCase()', code)
        self.assertNotIn("NumberAnimation", code)
        self.assertNotIn("ShaderEffect", code)
        self.assertNotIn("Timer {", code)

    def test_open_via_existing_tux_menu_and_preview_shortcut(self):
        main = (ROOT / "Main.qml").read_text(encoding="utf-8")
        self.assertIn('text: "Browse applications"', main)
        self.assertIn("onTriggered: appLauncher.openLauncher()", main)
        self.assertIn('sequence: "Ctrl+Space"', main)
        self.assertIn("onActivated: appLauncher.toggleLauncher()", main)
        self.assertIn("z: 20", main)
        self.assertIn("if (applicationName === \"Files\")", main)
        self.assertIn("filesPreview.visible = true", main)

    def test_explicit_no_real_system_process_launch(self):
        code = (ROOT / "LauncherOverlay.qml").read_text(encoding="utf-8")
        cpp = (ROOT / "main.cpp").read_text(encoding="utf-8")
        self.assertIn("is not connected in this preview", code)
        self.assertIn("Files opens the sample window", code)
        self.assertNotIn("QProcess", cpp)
        self.assertNotIn("Qt.openUrlExternally", code)
        self.assertNotIn("gio launch", code)
        self.assertNotIn("XMLHttpRequest", code)

    def test_open_launcher_uses_real_qt_capture_not_generated_art(self):
        cpp = (ROOT / "main.cpp").read_text(encoding="utf-8")
        workflow = (ROOT.parents[1] / ".github" / "workflows" /
                    "classic-qt.yml").read_text(encoding="utf-8")
        self.assertIn("--self-test-launcher-screenshot", cpp)
        self.assertIn("launcherFrame = window->grabWindow()", cpp)
        self.assertIn("QTimer::singleShot(250, window", cpp)
        self.assertIn("QCursor::setPos(window->mapToGlobal", cpp)
        self.assertIn("SELF_TEST_PASS: actual launcher overlay screenshot captured", cpp)
        self.assertIn("classic-launcher-open.png", workflow)
        self.assertIn("classic-launcher-desktop.png", workflow)
        self.assertIn("cmp -s", workflow)
        self.assertIn("python3 tools/check_screenshot.py test-artifacts/classic-launcher-open.png 1200 750", workflow)

    def test_compiled_runtime_checks_search_and_close(self):
        code = (ROOT / "main.cpp").read_text(encoding="utf-8")
        self.assertIn('QStringLiteral("canopyApplicationLauncher")', code)
        self.assertIn('QStringLiteral("canopyLauncherSearch")', code)
        self.assertIn('QStringLiteral("fIlEs")', code)
        self.assertIn("approvedMode ? 8 : 6", code)
        self.assertIn('"openLauncher"', code)
        self.assertIn('"closeLauncher"', code)
        self.assertIn("SELF_TEST_FAIL: launcher search or dismissal inconsistent", code)
        self.assertIn("SELF_TEST_PASS: actual Qt launcher opens, searches and closes", code)


if __name__ == "__main__":
    unittest.main()
