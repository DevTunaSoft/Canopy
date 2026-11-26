"""Focused source contracts for the opt-in Classic desktop context menu.

These tests are text-level contracts, not Qt runtime or visual acceptance.
They keep the right-click menu inert by default, bound to the existing host
launcher service, and outside the frozen dock/asset surface.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_classic_dock_frozen import (  # noqa: E402
    APPROVED_DOCK_FNV64,
    fnv1a64,
)

CLASSIC = ROOT / "prototype" / "classic"
QML = (CLASSIC / "DesktopContextMenu.qml").read_text(encoding="utf-8")
MAIN = (CLASSIC / "Main.qml").read_text(encoding="utf-8")
CPP = (CLASSIC / "main.cpp").read_text(encoding="utf-8")
CMAKE = (CLASSIC / "CMakeLists.txt").read_text(encoding="utf-8")


class DesktopContextMenuContracts(unittest.TestCase):
    def test_view_is_registered_and_wired_once(self):
        self.assertTrue((CLASSIC / "DesktopContextMenu.qml").is_file())
        self.assertIn("DesktopContextMenu.qml", CMAKE)
        self.assertEqual(MAIN.count("DesktopContextMenu {"), 1)
        for wiring in (
            "onOpenLauncherRequested: appLauncher.openLauncher()",
            "onShowFilesRequested: filesPreview.visible = true",
            "onAboutRequested: aboutPopup.open()",
        ):
            with self.subTest(wiring=wiring):
                self.assertIn(wiring, MAIN)
        self.assertIn('objectName: "canopyDesktopContextMenu"', QML)
        self.assertEqual(QML.count("Menu {"), 1)
        self.assertIn("canopyDesktopContextMenu", CPP)

    def test_runtime_opt_in_and_graceful_unavailable_state(self):
        for marker in (
            '--enable-desktop-context-menu',
            "DesktopContextMenuBridge desktopContextMenuBridge",
            "bool enabled() const { return m_enabled; }",
            "setContextProperty",
            '"canopyDesktopContextMenu"',
            "--self-test-desktop-context-menu",
            "DESKTOP_CONTEXT_FIXTURE_PASS",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, CPP)
        self.assertIn("readonly property bool contextEnabled: bridge && bridge.enabled", QML)
        self.assertIn("enabled: desktopContextMenu.contextEnabled", QML)
        self.assertIn("enabled: desktopContextMenu.nativeAvailable", QML)
        self.assertIn("visible: !desktopContextMenu.nativeAvailable", QML)
        self.assertIn("Unavailable — desktop context menu is not enabled", CPP)
        self.assertIn("Unavailable — native application launching is not enabled", CPP)
        self.assertIn("if (!nativeAvailable()) {", CPP)
        self.assertIn("return false;", CPP)

    def test_native_action_delegates_to_existing_service_only(self):
        self.assertIn("class DesktopContextMenuBridge final : public QObject", CPP)
        self.assertIn("Q_PROPERTY(bool enabled READ enabled CONSTANT)", CPP)
        self.assertIn("Q_PROPERTY(bool nativeAvailable READ nativeAvailable CONSTANT)", CPP)
        self.assertIn("Q_PROPERTY(QString disclosure READ disclosure CONSTANT)", CPP)
        self.assertIn("SystemAppLauncher &m_launcher", CPP)
        self.assertIn('m_launcher.canLaunch(QStringLiteral("Terminal"))', CPP)
        self.assertIn('m_launcher.launch(QStringLiteral("Terminal"))', CPP)
        self.assertIn("CANOPY_DESKTOP_CONTEXT_NATIVE_REFUSED", CPP)
        # No second native stack and no user-supplied executable path.
        for forbidden in (
            "QProcess", "gio_", "g_app_info", "QThread", "QTimer", "QTcp",
            "QLocalSocket", "exec(", "system(", "QDesktopServices",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, QML)
        for forbidden in ("QProcess", "gio_", "g_app_info", "QThread", "system("):
            with self.subTest(cpp_forbidden=forbidden):
                # Global main.cpp legitimately uses QTimer for existing
                # self-tests; the bridge itself must stay passive.
                bridge = CPP.split("class DesktopContextMenuBridge", 1)[1].split(
                    "// Host-side adapter", 1)[0]
                self.assertNotIn(forbidden, bridge)

    def test_no_second_panel_menu_service_or_asset_edits(self):
        for forbidden in (
            "Image {", "source:", "assets/", "#", "font.", "width:", "height:",
            "opacity:", "color:", "Timer {", "Loader {",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, QML)
        self.assertNotIn("ShellMenuBar", QML)
        self.assertNotIn("canopySystemLauncher", QML)
        self.assertNotIn("canopySystemLauncher", MAIN)
        # The dock block is the final Main.qml child; inserting the hidden
        # view above it must not perturb its frozen bytes.
        start = MAIN.index("    Rectangle {\n        id: dock")
        self.assertEqual(fnv1a64(MAIN[start:-1].encode("ascii")),
                         APPROVED_DOCK_FNV64)

    def test_compiled_selftest_checks_resting_and_opt_in_states(self):
        for marker in (
            "--self-test-desktop-context-menu",
            "popup gate",
            "popup close",
            "no app launched; visuals untouched",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, CPP)


if __name__ == "__main__":
    unittest.main()
