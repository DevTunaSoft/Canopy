"""Source contracts for Classic shell menus and opt-in launcher navigation.

These are text-level checks, not Qt runtime tests. They keep the menu bar
bound to the explicit filesPreview interface and reject stale demo copy.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"
MAIN = (ROOT / "Main.qml").read_text(encoding="utf-8")
# The six approved popups now live in a deferred QML document. Source
# contracts inspect both documents as one menu definition surface.
MENUS = ((ROOT / "ShellMenuBar.qml").read_text(encoding="utf-8")
         + (ROOT / "ShellMenuPopupSet.qml").read_text(encoding="utf-8"))
LAUNCHER = (ROOT / "LauncherOverlay.qml").read_text(encoding="utf-8")

MENU_NAMES = ("File", "Edit", "View", "Go", "Window", "Help")


class ClassicShellMenuContracts(unittest.TestCase):
    def test_shell_menu_bar_is_used_by_main(self):
        self.assertIn('objectName: "canopyShellMenuBar"', MENUS)
        self.assertIn("ShellMenuBar {", MAIN)
        self.assertIn("filesWindow: filesPreview", MAIN)
        self.assertIn('model: ["File", "Edit", "View", "Go", "Window", "Help"]', MAIN)
        self.assertIn("readonly property var actionMenu: shellMenus.menuFor(modelData)", MAIN)
        self.assertIn("onClicked: actionMenu.open()", MAIN)
        self.assertIn("function menuFor(name)", MENUS)
        for name in MENU_NAMES:
            with self.subTest(menu=name):
                self.assertIn('id: %sMenu' % name.lower(), MENUS)
                self.assertIn('title: "%s"' % name, MENUS)
                self.assertIn('case "%s": return %sMenu' % (name, name.lower()), MENUS)

    def test_actions_use_exact_files_preview_interface(self):
        required = (
            "shellMenus.filesWindow.currentPath",
            "shellMenus.filesWindow.searchQuery",
            "shellMenus.filesWindow.canGoBack",
            "shellMenus.filesWindow.canGoUp",
            "shellMenus.filesWindow.navigate(",
            "shellMenus.filesWindow.goBack()",
            "shellMenus.filesWindow.goUp()",
            "shellMenus.filesWindow.setSearch(",
            "shellMenus.filesWindow.requestClose()",
        )
        for member in required:
            with self.subTest(member=member):
                self.assertIn(member, MENUS)
        # Close requests go through the interface, including the keyboard path.
        self.assertIn("onActivated: filesPreview.requestClose()", MAIN)
        self.assertIn("onClosed: filesPreview.visible = false", MAIN)
        # Stale preview properties must not leak into the menu wiring.
        self.assertNotIn("filesPreview.currentSection", MAIN)
        self.assertNotIn("filesPreview.selectedFolder", MAIN)
        self.assertNotIn("currentSection", MENUS)
        self.assertNotIn("selectedFolder", MENUS)

    def test_named_actions_are_wired(self):
        pairs = (
            ("onShowLauncherRequested: appLauncher.openLauncher()", MAIN),
            ("onAboutRequested: aboutPopup.open()", MAIN),
            ("signal showLauncherRequested()", MENUS),
            ("signal aboutRequested()", MENUS),
            ("onTriggered: shellMenus.showLauncherRequested()", MENUS),
            ("onTriggered: shellMenus.aboutRequested()", MENUS),
            ("shellMenus.filesWindow.visible = true", MENUS),
            ("shellMenus.filesWindow.navigate(shellMenus.homePath)", MENUS),
            ("onTriggered: shellMenus.filesWindow.goBack()", MENUS),
            ("onTriggered: shellMenus.filesWindow.goUp()", MENUS),
            ("shellMenus.filesWindow.searchQuery)", MENUS),
            ("enabled: shellMenus.filesWindow && shellMenus.filesWindow.canGoBack", MENUS),
            ("enabled: shellMenus.filesWindow && shellMenus.filesWindow.canGoUp", MENUS),
            ("checkable: true", MENUS),
            ("onTriggered: shellMenus.filesWindow.visible = checked", MENUS),
        )
        for text, source in pairs:
            with self.subTest(text=text):
                self.assertIn(text, source)

    def test_no_placeholder_menu_copy_remains(self):
        stale = (
            "demo menu",
            "Reset demo view",
            "Clear selection",
            "About this preview",
            "Show Files preview",
            "preview-only",
            "are not implemented",
            "visual-only composition",
            "Target only this standalone demo",
        )
        for source_name, source in (("Main.qml", MAIN),
                                    ("ShellMenuBar.qml", MENUS),
                                    ("LauncherOverlay.qml", LAUNCHER)):
            for text in stale:
                with self.subTest(source=source_name, text=text):
                    self.assertNotIn(text, source)

    def test_accessibility_names_exist(self):
        names = (
            "Open Files window",
            "Close Files window",
            "Go to Files home",
            "Find in Files",
            "Clear Files search",
            "Toggle Files window",
            "Focus Files search field",
            "Current Files location",
            "Go back in Files",
            "Go up in Files",
            "Go to Files home folder",
            "Bring Files window to front",
            "Close Files window from Window menu",
            "Browse installed applications",
            "About Canopy Classic",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIn('Accessible.name: "%s"' % name, MENUS)
        self.assertIn('Accessible.name: modelData + " menu"', MAIN)
        self.assertIn('Accessible.name: "Canopy penguin launcher"', MAIN)
        self.assertIn('Accessible.name: "Search available preview applications"', LAUNCHER)
        self.assertIn('Accessible.name: "Select " + modelData.title', LAUNCHER)
        self.assertIn("Accessible.description: launcher.isInstalled(modelData.title)", LAUNCHER)

    def test_launcher_uses_existing_host_bridge_only(self):
        self.assertIn("canopySystemLaunchEnabled", LAUNCHER)
        self.assertIn("canopySystemLauncher.canLaunch(", LAUNCHER)
        self.assertIn("canopySystemLauncher.launch(", LAUNCHER)
        self.assertIn("function isInstalled(name)", LAUNCHER)
        self.assertIn("applicationSelected(name)", LAUNCHER)
        self.assertIn("Files opens the in-preview window", LAUNCHER)
        self.assertIn("could not be launched", LAUNCHER)
        self.assertIn("Not installed on this system", LAUNCHER)
        for text in ("QProcess", "Process {", "Qt.createProcess", "exec("):
            with self.subTest(forbidden=text):
                self.assertNotIn(text, LAUNCHER)
        # Native launch code stays in the launcher overlay, not the menus.
        self.assertNotIn("canopySystemLauncher", MENUS)
        self.assertNotIn("canopySystemLauncher", MAIN)

    def test_eight_icon_catalog_and_navigation_preserved(self):
        for title in ("Browser", "Mail", "Files", "Calendar",
                      "Photos", "Music", "Terminal", "Settings"):
            with self.subTest(title=title):
                self.assertIn('{ title: "%s" }' % title, LAUNCHER)
        for binding in (
            "Keys.onEscapePressed",
            "Keys.onDownPressed",
            "Keys.onReturnPressed",
            "Keys.onUpPressed",
            "Keys.onBacktabPressed",
            "keyNavigationWraps: true",
            "forceActiveFocus()",
            "width < 470 ? 3 : 4",
            "panel.height < 410 ? 98 : 116",
        ):
            with self.subTest(binding=binding):
                self.assertIn(binding, LAUNCHER)

    def test_approved_chrome_geometry_and_shortcuts_unchanged(self):
        frozen = (
            'objectName: "canopyTopBar"',
            'height: canopyTheme.barHeight',
            'color: canopyApprovedMode ? "#995e89a9" : canopyTheme.chrome',
            'objectName: "canopyLauncher"',
            'assets/brand/penguin-launcher.svg',
            'readonly property bool imageReady: penguinArt.status === Image.Ready',
            'onClicked: launcherMenu.open()',
            'objectName: "canopyDock"',
            "root.width * 0.56",
            "root.height * 0.56",
            "canopyTheme.barHeight - 166",
            "root.compactLayout",
            'objectName: "canopyFilesCloseShortcut"',
            'sequence: "Ctrl+W"',
            'objectName: "canopyFilesOpenShortcut"',
            'sequence: "Ctrl+Shift+F"',
        )
        for text in frozen:
            with self.subTest(text=text):
                self.assertIn(text, MAIN)


if __name__ == "__main__":
    unittest.main()
