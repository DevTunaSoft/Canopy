"""Source contracts for the Browser dock -> host GIO launcher bridge.

Workstream A second app. These are source-level invariants, not runtime Qt
tests: the compiled self-tests are exercised by the classic-qt CI workflow.
The bridge must reuse the already-validated SystemAppLauncher adapter, accept
only the exact frozen ``Browser`` dock label, and leave all QML/artwork bytes
untouched.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_classic_dock_frozen import (
    APPROVED_DOCK_FNV64,
    fnv1a64,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic"


class ClassicBrowserDockIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = (SOURCE / "main.cpp").read_text(encoding="utf-8")
        cls.launcher_h = (SOURCE / "SystemAppLauncher.h").read_text(encoding="utf-8")
        cls.launcher_cpp = (SOURCE / "SystemAppLauncher.cpp").read_text(encoding="utf-8")

    def test_browser_dock_reuses_validated_host_launcher(self):
        cpp = self.cpp
        self.assertIn("class BrowserDockLaunchBridge final : public QObject", cpp)
        self.assertIn('if (name != QStringLiteral("Browser"))', cpp)
        self.assertIn("m_launcher.launch(name)", cpp)
        self.assertIn(
            "QObject::connect(browserLaunchTile, SIGNAL(activated(QString)),",
            cpp,
        )
        self.assertIn("browserBridge, SLOT(activate(QString)))", cpp)
        self.assertIn("CANOPY_BROWSER_DOCK_NATIVE_LAUNCH_CONNECTED", cpp)
        # The exact-name allowlist still lives only in SystemAppLauncher.
        self.assertIn("candidates.value(dockName)", self.launcher_cpp)
        self.assertIn('QStringLiteral("Browser")', self.launcher_cpp)

    def test_browser_is_removed_from_direct_connect_loop(self):
        cpp = self.cpp
        self.assertIn(
            'if (name == QStringLiteral("Files") || name == QStringLiteral("Browser"))',
            cpp,
        )
        # No second launch path: no shell, argv builder or new GIO code.
        for forbidden in ("QProcess", "build_launch_argv", "gio launch",
                          "g_app_info_launch"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, cpp)

    def test_fail_closed_user_visible_refusal(self):
        cpp = self.cpp
        self.assertIn("CANOPY_BROWSER_DOCK_LAUNCH_REFUSED", cpp)
        self.assertIn('"openLauncher"', cpp)
        self.assertIn("setProperty(\"selectionMessage\"", cpp)
        self.assertIn('QStringLiteral("Browser could not be launched")', cpp)
        self.assertIn("CANOPY_BROWSER_DOCK_STATUS_UNAVAILABLE", cpp)
        overlay = (SOURCE / "LauncherOverlay.qml").read_text(encoding="utf-8")
        self.assertIn('objectName: "canopyLauncherStatus"', overlay)
        self.assertIn("launcher.selectionMessage", overlay)

    def test_browser_compiled_selftests_exposed(self):
        cpp = self.cpp
        for marker in (
            "--self-test-browser-dock-status",
            "--self-test-browser-dock-fixture",
            "BROWSER_DOCK_STATUS_FIXTURE_PASS",
            "BROWSER_DOCK_LAUNCH_FIXTURE_PASS",
            "BROWSER_DOCK_FIXTURE_FAIL: unknown action accepted",
            "BROWSER_DOCK_FIXTURE_FAIL: refusal not visible to user",
            'QStringLiteral("Browser;echo bad")',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)

    def test_frozen_visual_dock_and_assets_unchanged(self):
        # read_text() normalises newlines so this is stable on LF CI / CRLF host.
        main = (SOURCE / "Main.qml").read_text(encoding="utf-8")
        start = main.index("    Rectangle {\n        id: dock")
        self.assertEqual(fnv1a64(main[start:-1].encode("ascii")),
                         APPROVED_DOCK_FNV64)
        self.assertIn('signal activated(string applicationName)',
                      (SOURCE / "DockTile.qml").read_text(encoding="utf-8"))
        # No Browser-specific visual behaviour was introduced in the frozen QML.
        self.assertIn('if (applicationName === "Files")', main)
        self.assertNotIn('applicationName === "Browser"', main)


if __name__ == "__main__":
    unittest.main()
