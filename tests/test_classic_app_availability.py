"""Availability indicators are real, on-demand GIO state, never invented.

Qt CI independently tests the actual installed Nemo XDG fixture and QML
property through --self-test-launcher-ui-fixture.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"


class AppAvailabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qml = (CLASSIC / "LauncherOverlay.qml").read_text(encoding="utf-8")
        cls.cpp = (CLASSIC / "main.cpp").read_text(encoding="utf-8")
        cls.native = (CLASSIC / "SystemAppLauncher.cpp").read_text(encoding="utf-8")

    def test_refresh_on_open_without_polling_or_background_thread(self):
        q = self.qml
        self.assertIn("function refreshNativeAvailability()", q)
        self.assertIn("refreshNativeAvailability()\n        opened = true", q)
        self.assertIn("if (!nativeAppLaunchEnabled)", q)
        self.assertIn("canopySystemLauncher.canLaunch(title)", q)
        self.assertIn("nativeAppAvailability = available", q)
        self.assertIn("nativeAvailableCount = count", q)
        self.assertNotIn("Timer {", q)
        self.assertNotIn("Connections {", q)
        self.assertNotIn("WorkerScript", q)
        self.assertNotIn("QProcess", q)
        self.assertNotIn("XMLHttpRequest", q)

    def test_all_labels_disclose_installed_or_preview_status_when_opted_in(self):
        q = self.qml
        self.assertIn("Accessible.description: !launcher.nativeAppLaunchEnabled", q)
        self.assertIn('"Installed Linux application"', q)
        self.assertIn('"No matching installed Linux application"', q)
        self.assertIn('objectName: "canopyLauncherNativeAppState"', q)
        self.assertIn("visible: launcher.nativeAppLaunchEnabled", q)
        self.assertIn('"Installed"', q)
        self.assertIn('"Preview only"', q)
        self.assertIn('"Not installed"', q)
        self.assertIn('launcher.nativeAvailableCount + " installed application categories', q)
        self.assertIn('Files opens the sample window · others are preview-only', q)
        self.assertIn('text: "Applications"', q)

    def test_only_native_opt_in_queries_real_gio_catalog(self):
        self.assertIn("if (!m_enabled)", self.native)
        self.assertIn("g_desktop_app_info_new", self.native)
        self.assertIn("g_app_info_should_show", self.native)
        self.assertIn('if (!applicationLauncher->property("nativeAppLaunchEnabled").toBool()', self.cpp)
        self.assertIn('applicationLauncher->property("nativeAvailableCount").toInt() != 0', self.cpp)

    def test_compiled_qt_fixture_requires_actual_native_files_category(self):
        self.assertIn('overlay->property("nativeAppAvailability").toMap()', self.cpp)
        self.assertIn('availability.value(QStringLiteral("Files")).toBool()', self.cpp)
        self.assertIn('overlay->property("nativeAvailableCount").toInt() < 1', self.cpp)
        self.assertIn("SYSTEM_APP_AVAILABILITY_PASS", self.cpp)
        self.assertIn("SYSTEM_APP_UI_FIXTURE_PASS", self.cpp)

    def test_frozen_dock_not_part_of_app_catalog_queries(self):
        tile = (CLASSIC / "DockTile.qml").read_text(encoding="utf-8")
        main = (CLASSIC / "Main.qml").read_text(encoding="utf-8")
        self.assertNotIn("nativeAppAvailability", tile)
        self.assertNotIn("nativeAppLaunchEnabled", tile)
        self.assertNotIn("nativeAppAvailability", main)
        self.assertNotIn("nativeAvailableCount", main)


if __name__ == "__main__":
    unittest.main()
