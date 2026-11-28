"""Source-contract tests for the owned Classic preview/theme/menu QML.

These guard the scrollbar theming refinement and the frozen visual tokens.
They are not a substitute for compiled screenshots or owner visual acceptance.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic"


def read(name):
    return (SOURCE / name).read_text(encoding="utf-8")


class ClassicPreviewScrollbarTests(unittest.TestCase):
    def sidebar_scroll_source(self):
        text = read("PreviewWindow.qml")
        start = text.index("id: sidebarScroll")
        end = text.index("id: mainArea")
        return text[start:end]

    def test_sidebar_scrollbar_has_light_theme_override(self):
        block = self.sidebar_scroll_source()
        self.assertIn("ScrollBar.vertical: ScrollBar {", block)
        self.assertIn("policy: ScrollBar.AsNeeded", block)
        self.assertIn("background: Rectangle {", block)
        self.assertIn('color: "#e8f0f8"', block)
        self.assertIn("contentItem: Rectangle {", block)
        self.assertIn('color: parent.active ? "#8fb0cd" : "#b3c9de"', block)

    def test_sidebar_geometry_contract_unchanged(self):
        text = read("PreviewWindow.qml")
        sidebar = text[text.index("id: sidebar\n"):text.index("id: sidebarScroll")]
        block = self.sidebar_scroll_source()
        self.assertIn("width: preview.condensed ? 135 : 176", sidebar)
        self.assertIn("contentHeight: sidebarList.implicitHeight + 9", block)
        self.assertIn("boundsBehavior: Flickable.StopAtBounds", block)
        self.assertIn("spacing: 3", block)

    def test_no_timers_animation_or_effects_introduced(self):
        for name in ("PreviewWindow.qml", "Theme.qml", "ShellMenuBar.qml"):
            text = read(name)
            for banned in ("Timer {", "Animation {", "Behavior on ",
                           "ShaderEffect", "Blur", "PropertyAnimation"):
                self.assertNotIn(banned, text, f"{banned!r} found in {name}")

    def test_theme_identity_tokens_frozen(self):
        text = read("Theme.qml")
        for token in ('backgroundTop: "#cbdff2"', 'foreground: "#273345"',
                      'accent: "#537da4"', 'indicator: "#d8b87a"',
                      "barHeight: 32", "dockSize: 96", "dockPadding: 14",
                      "dockSpacing: 7", "tileSize: 52", "cornerRadius: 24"):
            self.assertIn(token, text)

    def test_shell_menu_proxy_contract_intact(self):
        text = read("ShellMenuBar.qml")
        self.assertIn("source: \"ShellMenuPopupSet.qml\"", text)
        self.assertIn("active: false", text)
        for name in ("File", "Edit", "View", "Go", "Window", "Help"):
            self.assertIn(f'menuFor("{name}")', text)
        for signal in ("showLauncherRequested()", "aboutRequested()"):
            self.assertIn(f"signal {signal}", text)


if __name__ == "__main__":
    unittest.main()
