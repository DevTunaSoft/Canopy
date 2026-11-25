"""Source contracts for the Classic shell-menu presentation polish.

These are deterministic text-level checks over the two owned QML documents.
They keep the six approved menus, their actions and the explicit filesPreview
interface intact while proving that typography, spacing, hover/pressed/focus
states and disabled disclosure come only from existing Theme tokens.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAR = (ROOT / "prototype" / "classic" / "ShellMenuBar.qml").read_text(encoding="utf-8")
POPUP = (ROOT / "prototype" / "classic" / "ShellMenuPopupSet.qml").read_text(encoding="utf-8")
THEME = (ROOT / "prototype" / "classic" / "Theme.qml").read_text(encoding="utf-8")
SOURCES = (BAR, POPUP)

TOKEN_RE = re.compile(r"readonly property (?:color|int|real|bool|string)\s+(\w+)\s*:")
HEX_RE = re.compile(r'"#[0-9a-fA-F]{3,8}"')
GEOMETRY_RE = re.compile(r"(?m)^\s*(?:width|height):")

MENU_NAMES = ("File", "Edit", "View", "Go", "Window", "Help")
ACTION_OBJECT_NAMES = (
    "canopyMenuFileOpen", "canopyMenuFileClose", "canopyMenuFileHome",
    "canopyMenuEditFind", "canopyMenuEditClear",
    "canopyMenuViewToggle", "canopyMenuViewFocusSearch", "canopyMenuViewPath",
    "canopyMenuGoBack", "canopyMenuGoUp", "canopyMenuGoHome",
    "canopyMenuWindowFiles", "canopyMenuWindowClose",
    "canopyMenuHelpApplications", "canopyMenuHelpAbout",
)


class ClassicShellMenuPolishContracts(unittest.TestCase):
    def test_bar_supplies_existing_theme_to_deferred_popup(self):
        self.assertIn('objectName: "canopyShellMenuBar"', BAR)
        self.assertIn("Theme { id: menuTheme }", BAR)
        self.assertIn(
            "menusLoader.item.menuPaletteSource = Qt.binding(function() { return menuTheme })",
            BAR)
        self.assertIn("menusLoader.item.presentation", BAR)
        self.assertIn("readonly property var menuPresentation:", BAR)
        self.assertIn("property var menuPaletteSource: null", POPUP)
        self.assertIn("Theme { id: fallbackPalette }", POPUP)
        self.assertIn(
            "readonly property var effectivePalette: menuPaletteSource || fallbackPalette",
            POPUP)
        self.assertIn("readonly property var presentation: menuPresentation", POPUP)
        # The explicit filesPreview bridge and signals are untouched.
        for text in ("property var filesWindow: null",
                     'property string homePath: "Home"',
                     "signal showLauncherRequested()",
                     "signal aboutRequested()"):
            with self.subTest(text=text):
                self.assertTrue(all(text in source for source in SOURCES))
        self.assertIn('source: "ShellMenuPopupSet.qml"', BAR)
        self.assertIn("active: false", BAR)

    def test_presentation_references_only_existing_theme_tokens(self):
        available = set(TOKEN_RE.findall(THEME))
        referenced = set(re.findall(r"shellMenus\.effectivePalette\.(\w+)", POPUP))
        self.assertTrue(referenced)
        self.assertLessEqual(referenced, available)
        for token in ("foreground", "muted", "accent", "tile", "tileHover", "dockBorder", "cornerRadius"):
            with self.subTest(token=token):
                self.assertIn(token, referenced)
        for source in SOURCES:
            self.assertIsNone(HEX_RE.search(source))
        self.assertIn("pragma ComponentBehavior: Bound", POPUP)

    def test_typography_and_spacing_are_one_contract_for_all_actions(self):
        for declaration in (
            "readonly property int leftPadding: 18",
            "readonly property int rightPadding: 18",
            "readonly property int topPadding: 7",
            "readonly property int bottomPadding: 7",
            "readonly property int labelPixelSize: 13",
            "readonly property int labelWeight: Font.Medium",
            "readonly property real disabledOpacity: 0.55",
        ):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, POPUP)
        for binding in (
            "leftPadding: menuPresentation.leftPadding",
            "rightPadding: menuPresentation.rightPadding",
            "topPadding: menuPresentation.topPadding",
            "bottomPadding: menuPresentation.bottomPadding",
            "font.pixelSize: menuPresentation.labelPixelSize",
            "font.weight: menuPresentation.labelWeight",
        ):
            with self.subTest(binding=binding):
                self.assertIn(binding, POPUP)
        # The approved source gate reads these literal markers from the same
        # contract object; no cramped padding value may be reintroduced.
        for marker in ("leftPadding: 18", "rightPadding: 18",
                       "topPadding: 7", "bottomPadding: 7",
                       "// font.pixelSize: 13", "// font.weight: Font.Medium"):
            with self.subTest(marker=marker):
                self.assertEqual(POPUP.count(marker), 1)
        for stale in ("leftPadding: 8", "rightPadding: 8", "topPadding: 5"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, POPUP)
        self.assertEqual(POPUP.count("component PremiumMenuItem: MenuItem {"), 1)
        self.assertEqual(POPUP.count("PremiumMenuItem {"), 15)
        self.assertEqual(POPUP.count("component PremiumMenu: Menu {"), 1)
        self.assertEqual(POPUP.count("PremiumMenu {"), 6)
        self.assertEqual(POPUP.count("MenuSeparator {}"), 4)
        self.assertNotIn("PremiumSeparator", POPUP)

    def test_hover_pressed_focus_states_are_distinct_and_token_backed(self):
        self.assertIn("hoverEnabled: true", POPUP)
        for clause in (
            'if (!premiumItem.enabled) return "transparent"',
            "if (premiumItem.down) return menuPresentation.pressedColor",
            "if (premiumItem.highlighted || premiumItem.activeFocus) return menuPresentation.focusColor",
            "if (premiumItem.hovered) return menuPresentation.hoverColor",
            'return "transparent"',
            "border.color: premiumItem.enabled && premiumItem.activeFocus",
            "border.width: premiumItem.enabled && premiumItem.activeFocus ? 1 : 0",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, POPUP)
        for mapping in (
            "readonly property color hoverColor: shellMenus.effectivePalette.tileHover",
            "readonly property color pressedColor: shellMenus.effectivePalette.accent",
            "readonly property color focusColor: shellMenus.effectivePalette.tile",
            "readonly property color focusBorderColor: shellMenus.effectivePalette.accent",
            "readonly property color textColor: shellMenus.effectivePalette.foreground",
            "readonly property color pressedTextColor: shellMenus.effectivePalette.tile",
            "readonly property color surfaceColor: shellMenus.effectivePalette.tile",
        ):
            with self.subTest(mapping=mapping):
                self.assertIn(mapping, POPUP)

        for mapping in (
            "visible: premiumItem.checkable",
            "visible: premiumItem.checked",
            "? menuPresentation.focusBorderColor\n                                  : menuPresentation.dividerColor",
        ):
            with self.subTest(checked_state=mapping):
                self.assertIn(mapping.replace("\r\n", "\n"), POPUP.replace("\r\n", "\n"))

    def test_disabled_entries_disclose_unavailability(self):
        self.assertIn(
            'Accessible.description: enabled ? "Activate " + text : text + " (unavailable)"',
            POPUP)
        self.assertIn(
            'text: premiumItem.text + (premiumItem.enabled ? "" : " (unavailable)")',
            POPUP)
        self.assertIn(
            "color: !premiumItem.enabled ? menuPresentation.mutedTextColor", POPUP)
        self.assertIn(
            "readonly property color mutedTextColor: shellMenus.effectivePalette.muted",
            POPUP)
        self.assertIn(
            "opacity: premiumItem.enabled ? 1 : menuPresentation.disabledOpacity",
            POPUP)
        self.assertIn("enabled: false\n            text: shellMenus.filesWindow", POPUP.replace("\r\n", "\n"))
        for binding in (
            "enabled: shellMenus.filesWindow && shellMenus.filesWindow.visible",
            "enabled: shellMenus.filesWindow && shellMenus.filesWindow.canGoBack",
            "enabled: shellMenus.filesWindow && shellMenus.filesWindow.canGoUp",
        ):
            with self.subTest(binding=binding):
                self.assertIn(binding, POPUP)

    def test_approved_menu_structure_and_interface_are_unchanged(self):
        for name in MENU_NAMES:
            with self.subTest(menu=name):
                self.assertIn('id: %sMenu' % name.lower(), POPUP)
                self.assertIn('title: "%s"' % name, POPUP)
                self.assertIn('case "%s": return %sMenu' % (name, name.lower()), POPUP)
        for object_name in ACTION_OBJECT_NAMES:
            with self.subTest(objectName=object_name):
                self.assertIn('objectName: "%s"' % object_name, POPUP)
        for member in ("shellMenus.filesWindow.currentPath",
                       "shellMenus.filesWindow.searchQuery",
                       "shellMenus.filesWindow.canGoBack",
                       "shellMenus.filesWindow.canGoUp",
                       "shellMenus.filesWindow.navigate(",
                       "shellMenus.filesWindow.goBack()",
                       "shellMenus.filesWindow.goUp()",
                       "shellMenus.filesWindow.setSearch(",
                       "shellMenus.filesWindow.requestClose()",
                       "onTriggered: shellMenus.showLauncherRequested()",
                       "onTriggered: shellMenus.aboutRequested()",
                       "checkable: true"):
            with self.subTest(member=member):
                self.assertIn(member, POPUP)

    def test_no_new_geometry_artwork_animation_or_process(self):
        forbidden = (
            "Image {", "Timer {", "Animation {",
            "NumberAnimation", "SequentialAnimation", "Behavior on", "QProcess",
            "Qt.createQmlObject", "Qt.createComponent", "Process {", "exec(",
            "canopySystemLauncher", "wallpaper", "dockSpacing", "dockSize",
        )
        for source_name, source in (("ShellMenuBar.qml", BAR),
                                    ("ShellMenuPopupSet.qml", POPUP)):
            self.assertIsNone(GEOMETRY_RE.search(source), source_name)
            for text in forbidden:
                with self.subTest(source=source_name, forbidden=text):
                    self.assertNotIn(text, source)


if __name__ == "__main__":
    unittest.main()
