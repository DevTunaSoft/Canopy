"""Source contracts for opt-in system-native Linux application launching.

The Qt CI executable smoke tests additionally exercise a real isolated GIO
.desktop entry; these source tests guard policy without spawning user apps.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"


class NativeAppLauncherTests(unittest.TestCase):
    def test_launcher_is_host_owned_and_opt_in(self):
        header = (CLASSIC / "SystemAppLauncher.h").read_text()
        source = (CLASSIC / "SystemAppLauncher.cpp").read_text()
        main = (CLASSIC / "main.cpp").read_text()
        self.assertIn("class SystemAppLauncher final : public QObject", header)
        self.assertIn('args.contains(QStringLiteral("--enable-system-apps"))', main)
        self.assertIn("SystemAppLauncher systemLauncher(enableSystemApps)", main)
        self.assertIn("if (!m_enabled)", source)
        self.assertIn('setContextProperty(\n        QStringLiteral("canopySystemLauncher"), &systemLauncher)', main)
        self.assertIn('QStringLiteral("canopySystemLaunchEnabled"), enableSystemApps)', main)

    def test_only_whitelisted_dock_names_and_desktop_ids(self):
        source = (CLASSIC / "SystemAppLauncher.cpp").read_text()
        for app in ("Browser", "Mail", "Files", "Calendar", "Photos",
                    "Music", "Terminal", "Settings"):
            self.assertIn(f'QStringLiteral("{app}")', source)
        self.assertIn("candidates.value(dockName)", source)
        self.assertIn("if (choices.isEmpty())", source)
        self.assertIn("GDesktopAppInfo *info = g_desktop_app_info_new", source)
        self.assertIn("g_app_info_should_show(G_APP_INFO(info))", source)
        self.assertIn("g_app_info_launch(", source)
        for unsafe in ("QProcess", "std::system(", "popen(", "QDesktopServices::openUrl",
                       "fork(", "execvp(", "system("):
            self.assertNotIn(unsafe, source)

    def test_gio_headers_precede_qt_signals_macro(self):
        # Real Qt6 build initially failed because Qt's "signals" macro
        # rewrote GLib's GDBusSignalInfo::signals member declaration.
        source = (CLASSIC / "SystemAppLauncher.cpp").read_text()
        self.assertLess(
            source.index("#include <gio/gdesktopappinfo.h>"),
            source.index('#include "SystemAppLauncher.h"'),
        )

    def test_launcher_does_not_contain_new_background_services(self):
        source = (CLASSIC / "SystemAppLauncher.cpp").read_text()
        self.assertNotIn("QTimer", source)
        self.assertNotIn("QThread", source)
        self.assertNotIn("QNetworkAccessManager", source)
        self.assertNotIn("QFile::remove", source)

    def test_default_preview_is_preserved(self):
        qml = (CLASSIC / "Main.qml").read_text()
        dock = (CLASSIC / "DockTile.qml").read_text()
        self.assertIn("if (canopySystemLaunchEnabled)", qml)
        self.assertIn("canopySystemLauncher.launch(applicationName)", qml)
        self.assertIn('if (applicationName === "Files")', qml)
        self.assertIn("filesPreview.visible = !filesPreview.visible", qml)
        self.assertIn("previewActive: modelData.title", qml)
        self.assertIn("ToolTip.text: canopySystemLaunchEnabled", dock)
        self.assertIn("Accessible.description: canopySystemLaunchEnabled", dock)
        self.assertNotIn("ShaderEffect", qml)

    def test_cmake_links_gio_unix_without_shell_bridge(self):
        cmake = (CLASSIC / "CMakeLists.txt").read_text()
        workflow = (ROOT / ".github" / "workflows" / "classic-qt.yml").read_text()
        self.assertIn("SystemAppLauncher.cpp SystemAppLauncher.h", cmake)
        self.assertIn("pkg_check_modules(GIO_UNIX REQUIRED IMPORTED_TARGET gio-unix-2.0)", cmake)
        self.assertIn("PkgConfig::GIO_UNIX", cmake)
        self.assertIn("libglib2.0-dev", workflow)
        self.assertIn("--self-test-system-apps", workflow)
        self.assertIn("--self-test-system-apps-fixture", workflow)
        self.assertIn("nemo.desktop", workflow)
        self.assertIn("canopy-native-app-launched", workflow)

    def test_cli_self_test_refuses_untrusted_actions(self):
        main = (CLASSIC / "main.cpp").read_text()
        for value in ("Browser;echo hacked", "../firefox.desktop", "firefox.desktop"):
            self.assertIn(value, main)
        self.assertIn("SYSTEM_APP_LAUNCH_TEST_PASS", main)
        self.assertIn("SYSTEM_APP_LAUNCH_FIXTURE_PASS", main)


if __name__ == "__main__":
    unittest.main()
