"""Independent contracts for real installed-Linux-app launching from the

SEARCH OVERLAY ONLY. The user-approved dock stays unchanged and fully
preview-only. Actual GIO execution is tested in headless Qt CI with an
isolated disposable desktop entry; no workstation apps are started.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"


class ClassicNativeLauncherOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = (CLASSIC / "main.cpp").read_text(encoding="utf-8")
        cls.main = (CLASSIC / "Main.qml").read_text(encoding="utf-8")
        cls.overlay = (CLASSIC / "LauncherOverlay.qml").read_text(encoding="utf-8")
        cls.dock = (CLASSIC / "DockTile.qml").read_text(encoding="utf-8")
        cls.native = (CLASSIC / "SystemAppLauncher.cpp").read_text(encoding="utf-8")
        cls.header = (CLASSIC / "SystemAppLauncher.h").read_text(encoding="utf-8")

    def test_explicit_opt_in_default_off(self):
        self.assertIn('args.contains(QStringLiteral("--enable-system-apps"))', self.cpp)
        self.assertIn("SystemAppLauncher systemLauncher(enableSystemApps)", self.cpp)
        self.assertIn("const bool enableSystemApps =", self.cpp)
        self.assertIn('QStringLiteral("canopySystemLauncher"), &systemLauncher', self.cpp)
        self.assertIn('QStringLiteral("canopySystemLaunchEnabled"), enableSystemApps', self.cpp)
        self.assertIn("nativeAppLaunchEnabled: canopySystemLaunchEnabled", self.main)
        self.assertIn("if (nativeAppLaunchEnabled && canopySystemLauncher.launch(name))",
                      self.overlay)
        self.assertIn("if (!m_enabled)", self.native)

    def test_app_activation_is_launcher_only(self):
        self.assertNotIn("canopySystemLauncher", self.dock)
        self.assertNotIn("canopySystemLaunchEnabled", self.dock)
        self.assertNotIn("canopySystemLauncher.launch(", self.main)
        self.assertIn("applicationSelected(name)", self.overlay)
        self.assertIn('if (name === "Files")', self.overlay)
        self.assertIn('if (applicationName === "Files")', self.main)
        self.assertIn("filesPreview.visible = true", self.main)
        self.assertIn("is not installed or could not start", self.overlay)
        self.assertIn("is not connected in this preview", self.overlay)

    def test_native_service_accepts_only_fixed_categories(self):
        self.assertIn("class SystemAppLauncher final : public QObject", self.header)
        self.assertIn("candidates.value(dockName)", self.native)
        for name in ("Browser", "Mail", "Files", "Calendar",
                     "Photos", "Music", "Terminal", "Settings"):
            self.assertIn(f'QStringLiteral("{name}")', self.native)
        self.assertIn("g_desktop_app_info_new", self.native)
        self.assertIn("g_app_info_should_show", self.native)
        self.assertIn("g_app_info_launch(", self.native)
        for dangerous in ("QProcess", "std::system(", "popen(", "fork(",
                          "execvp(", "QNetworkAccessManager", "QThread", "QTimer"):
            self.assertNotIn(dangerous, self.native)

    def test_glib_header_order_and_compilation_wiring(self):
        self.assertLess(self.native.index("#include <gio/gdesktopappinfo.h>"),
                        self.native.index('#include "SystemAppLauncher.h"'))
        cmake = (CLASSIC / "CMakeLists.txt").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/classic-qt.yml").read_text(encoding="utf-8")
        self.assertIn("PkgConfig::GIO_UNIX", cmake)
        self.assertIn("SystemAppLauncher.cpp SystemAppLauncher.h", cmake)
        self.assertIn("libglib2.0-dev", workflow)
        self.assertIn("--self-test-system-apps-fixture", workflow)
        self.assertIn("XDG_DATA_HOME", workflow)
        self.assertIn("nemo.desktop", workflow)
        self.assertIn("canopy-native-app-launched", workflow)

    def test_no_unrestricted_cli_or_generated_shell(self):
        self.assertIn("SYSTEM_APP_LAUNCH_TEST_PASS", self.cpp)
        self.assertIn("SYSTEM_APP_LAUNCH_FIXTURE_PASS", self.cpp)
        for value in ("Browser;echo hacked", "../firefox.desktop", "firefox.desktop"):
            self.assertIn(value, self.cpp)
        self.assertIn("Q_INVOKABLE bool launch(const QString &dockName) const", self.header)
        self.assertNotIn("QProcess::startDetached", self.cpp)
        self.assertNotIn("Qt.openUrlExternally", self.overlay)


if __name__ == "__main__":
    unittest.main()
