"""Source gate for the premium top-bar and menu refinement pass.

Offline and deterministic: it guards the readable top-bar spacing, keyboard
focus affordances, status-label clarity and uniform menu typography in the
two owned QML documents. It is not a Qt compile, screenshot or Mint acceptance
test; those are separate evidence stages.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "prototype" / "classic" / "Main.qml"
MENUS = ROOT / "prototype" / "classic" / "ShellMenuPopupSet.qml"

FORBIDDEN_EFFECTS = (
    "Timer {", "NumberAnimation", "PropertyAnimation", "SequentialAnimation",
    "ParallelAnimation", "PauseAnimation", "SmoothedAnimation",
    "SpringAnimation", "AnchorAnimation", "Behavior on", "ShaderEffect",
    "Qt.createProcess", "QProcess",
)

MAIN_REQUIRED = (
    'objectName: "canopyTopBar"',
    'height: canopyTheme.barHeight',
    'color: canopyApprovedMode ? "#995e89a9" : canopyTheme.chrome',
    'anchors.leftMargin: root.compactLayout ? 16 : 24',
    'anchors.rightMargin: root.compactLayout ? 16 : 24',
    'spacing: root.compactLayout ? 10 : 18',
    'source: "qrc:/Canopy/Classic/assets/brand/penguin-launcher.svg"',
    'readonly property bool imageReady: penguinArt.status === Image.Ready',
    'Accessible.name: "Canopy penguin launcher"',
    'Accessible.description: "Open the Canopy applications menu"',
    'ToolTip.text: "Canopy menu"',
    'ToolTip.visible: tuxMark.hovered || tuxMark.activeFocus',
    'tuxMark.hovered || tuxMark.activeFocus || launcherMenu.visible',
    'border.width: tuxMark.activeFocus ? 1 : 0',
    'font.pixelSize: 13',
    'topMenuButton.hovered || topMenuButton.activeFocus',
    'border.width: topMenuButton.activeFocus ? 1 : 0',
    'Accessible.description: "Open the " + modelData + " menu"',
    'Accessible.description: "Local date and time; refreshes once per minute"',
)

MENU_OBJECT_NAMES = (
    "canopyMenuFile", "canopyMenuFileOpen", "canopyMenuFileClose",
    "canopyMenuFileHome", "canopyMenuEdit", "canopyMenuEditFind",
    "canopyMenuEditClear", "canopyMenuView", "canopyMenuViewToggle",
    "canopyMenuViewFocusSearch", "canopyMenuViewPath", "canopyMenuGo",
    "canopyMenuGoBack", "canopyMenuGoUp", "canopyMenuGoHome",
    "canopyMenuWindow", "canopyMenuWindowFiles", "canopyMenuWindowClose",
    "canopyMenuHelp", "canopyMenuHelpApplications", "canopyMenuHelpAbout",
)

MENUS_REQUIRED = (
    "component PremiumMenuItem: MenuItem {",
    "leftPadding: 18",
    "rightPadding: 18",
    "topPadding: 7",
    "bottomPadding: 7",
    "font.pixelSize: 13",
    "font.weight: Font.Medium",
    'Accessible.description: enabled ? "Activate " + text : text + " (unavailable)"',
)


def _no_forbidden_effects(text):
    for token in FORBIDDEN_EFFECTS:
        if token in text:
            raise AssertionError("forbidden machinery reintroduced: " + token)


def check_main(text):
    """Fail closed unless the refined top bar keeps its frozen composition."""
    if not isinstance(text, str):
        raise AssertionError("Main.qml must be text")
    for token in MAIN_REQUIRED:
        if token not in text:
            raise AssertionError("top bar lost " + token)
    if text.count("font.weight: Font.Medium") < 3:
        raise AssertionError("top bar labels lost their medium weight")
    if text.count("font.pixelSize: 13") < 2:
        raise AssertionError("menu labels lost their readable size")
    if "anchors.leftMargin: root.compactLayout ? 14 : 22" in text:
        raise AssertionError("old cramped top-bar margins returned")
    if "spacing: root.compactLayout ? 12 : 20" in text:
        raise AssertionError("old cramped top-bar spacing returned")
    _no_forbidden_effects(text)
    return True


def check_menus(text):
    """Fail closed unless all 15 actions keep identity and uniform typography."""
    if not isinstance(text, str):
        raise AssertionError("ShellMenuPopupSet.qml must be text")
    for token in MENUS_REQUIRED:
        if token not in text:
            raise AssertionError("menu refinement lost " + token)
    instances = re.findall(r"\bPremiumMenuItem\s*\{", text)
    if len(instances) != 15:
        raise AssertionError("expected 15 refined menu actions, got " + str(len(instances)))
    if re.search(r"(?m)^\s*MenuItem\s*\{", text):
        raise AssertionError("a menu action bypasses the shared typography")
    for name in MENU_OBJECT_NAMES:
        if 'objectName: "%s"' % name not in text:
            raise AssertionError("menu identity lost " + name)
    if text.count("MenuSeparator {}") != 4:
        raise AssertionError("approved menu separators changed")
    for menu_name in ("File", "Edit", "View", "Go", "Window", "Help"):
        if 'case "%s": return %sMenu' % (menu_name, menu_name.lower()) not in text:
            raise AssertionError("menu routing lost " + menu_name)
    _no_forbidden_effects(text)
    return True


def _replace_once(text, old, new):
    """Build a negative control without dumping whole sources on failure."""
    if old not in text:
        raise AssertionError("negative control needle missing: " + old)
    hostile = text.replace(old, new, 1)
    if hostile == text:
        raise AssertionError("negative control mutation was a no-op")
    return hostile


class PremiumTopBarMenuTests(unittest.TestCase):
    def setUp(self):
        self.main = MAIN.read_text(encoding="utf-8")
        self.menus = MENUS.read_text(encoding="utf-8")

    def test_top_bar_has_readable_spacing_focus_and_status_clarity(self):
        self.assertTrue(check_main(self.main))

    def test_menu_actions_share_readable_typography_and_keep_identity(self):
        self.assertTrue(check_menus(self.menus))

    def test_negative_control_dropping_focus_state_fails(self):
        hostile = _replace_once(
            self.main,
            "topMenuButton.hovered || topMenuButton.activeFocus",
            "topMenuButton.hovered")
        with self.assertRaises(AssertionError):
            check_main(hostile)

    def test_negative_control_restoring_cramped_spacing_fails(self):
        hostile = _replace_once(
            self.main,
            "spacing: root.compactLayout ? 10 : 18",
            "spacing: root.compactLayout ? 12 : 20")
        with self.assertRaises(AssertionError):
            check_main(hostile)

    def test_negative_control_dropping_menu_padding_fails(self):
        hostile = _replace_once(self.menus, "leftPadding: 18\n", "leftPadding: 8\n")
        with self.assertRaises(AssertionError):
            check_menus(hostile)

    def test_negative_control_bypassing_shared_menu_item_fails(self):
        if self.menus.count("PremiumMenuItem {") < 2:
            raise AssertionError("negative control needs two refined actions")
        hostile = self.menus.replace("PremiumMenuItem {", "MenuItem {", 2)
        with self.assertRaises(AssertionError):
            check_menus(hostile)

    def test_negative_control_adding_timer_fails(self):
        hostile = self.main + "\nTimer { interval: 16 }\n"
        with self.assertRaises(AssertionError):
            check_main(hostile)


if __name__ == "__main__":
    unittest.main()
