"""Static regression gate for the launcher/clock premium polish pass.

These guards protect only the two owned QML files. They do not claim visual
approval, compiled keyboard dispatch or Mint acceptance; compiled evidence is
recorded separately at 1920x1080, 1200x750 and 760x500.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
OVERLAY = (CLASSIC / "LauncherOverlay.qml").read_text(encoding="utf-8")
CLOCK = (CLASSIC / "ClockLabel.qml").read_text(encoding="utf-8")


def require(condition, message):
    if not condition:
        raise AssertionError(message)
    return True


def check_overlay(text):
    require('objectName: "canopyLauncherKeyHints"' in text,
            "keyboard hint label removed")
    require('text: "Up/Down select · Enter open · Esc close"' in text,
            "keyboard hint text changed")
    require('Accessible.name: "Launcher keyboard shortcuts: " + text' in text,
            "keyboard hints lack an accessible name")
    require("anchors.bottom: footer.top" in text,
            "keyboard hints no longer sit directly above the status line")
    require("anchors.bottom: keyHints.top" in text,
            "grid no longer reserves space for the keyboard hints")
    require("grid.activeFocus && grid.currentIndex === appButton.index" in text,
            "grid keyboard selection has no visible selected state")
    require('? "#dceaf5" : "transparent"' in text,
            "approved selected background changed")
    require('border.color: "#5687b3"' in text,
            "approved focus border colour changed")
    return True


def check_clock(text):
    require('Qt.formatDateTime(currentTime, "ddd d MMM") + " · " +' in text,
            "explicit date/time separator removed")
    require('Qt.formatTime(currentTime, "h:mm AP")' in text,
            "clock time format removed")
    require('"ddd d MMM  h:mm AP"' not in text,
            "ambiguous double-space clock format restored")
    require('color: "#f7f5eb"' in text, "approved clock colour changed")
    require("font.pixelSize: 12" in text, "clock typography changed")
    require("font.weight: Font.Medium" in text, "clock typography changed")
    require(text.count("Timer {") == 1, "clock wakeup count changed")
    for token in ("interval: 60000", "repeat: false", "running: false",
                  "refreshScheduled: nextMinute.running", "60000 -",
                  "nextMinute.restart()"):
        require(token in text, "clock wakeup contract lost " + token)
    for token in ("Animation", "Behavior on", "setInterval", "setTimeout",
                  "setImmediate"):
        require(token not in text, "clock gained a forbidden wakeup: " + token)
    return True


class LauncherClockPolishTests(unittest.TestCase):
    def test_overlay_keyboard_hints_and_selected_state(self):
        check_overlay(OVERLAY)

    def test_clock_separator_and_idle_wakeup_contract(self):
        check_clock(CLOCK)

    def test_approved_visual_identity_is_frozen(self):
        for snippet in (
            'width: Math.min(parent.width - 42, 814)',
            'height: Math.min(parent.height - 106, 465)',
            'radius: 22', 'color: "#f3f8fc"', 'border.color: "#b7d0dce8"',
            'width: Math.min(parent.width - 42, 590)',
            'height: 40', 'radius: 12', 'border.color: searchField.activeFocus ? "#5c8fb8" : "#cad7e2"',
            'readonly property int columns: width < 470 ? 3 : 4',
            'cellHeight: panel.height < 410 ? 98 : 116',
            'image://canopy-dock/', 'qrc:/Canopy/Classic/assets/icons/',
            'Files opens the in-preview window · native launch is opt-in',
        ):
            with self.subTest(snippet=snippet[:48]):
                self.assertIn(snippet, OVERLAY)
        for app in ("Browser", "Mail", "Files", "Calendar", "Photos",
                    "Music", "Terminal", "Settings"):
            with self.subTest(app=app):
                self.assertIn('{ title: "%s" }' % app, OVERLAY)

    def test_no_new_animation_or_process_in_launcher(self):
        for token in ("Animation", "Timer {", "QProcess", "Process {",
                      "QtNetwork", "Qt.createQmlObject"):
            with self.subTest(token=token):
                self.assertNotIn(token, OVERLAY)

    def test_guard_rejects_removed_hints(self):
        hostile = OVERLAY.replace(
            'text: "Up/Down select · Enter open · Esc close"',
            'text: ""', 1)
        self.assertNotEqual(hostile, OVERLAY)
        with self.assertRaises(AssertionError):
            check_overlay(hostile)

    def test_guard_rejects_grid_selection_regression(self):
        hostile = OVERLAY.replace(
            "grid.activeFocus && grid.currentIndex === appButton.index",
            "appButton.activeFocus")
        self.assertNotEqual(hostile, OVERLAY)
        with self.assertRaises(AssertionError):
            check_overlay(hostile)

    def test_guard_rejects_clock_format_regression(self):
        hostile = CLOCK.replace(
            'Qt.formatDateTime(currentTime, "ddd d MMM") + " · " +\n'
            '          Qt.formatTime(currentTime, "h:mm AP")',
            'Qt.formatDateTime(currentTime, "ddd d MMM  h:mm AP")', 1)
        hostile = hostile.replace('\r\n', '\n')
        if hostile == CLOCK.replace('\r\n', '\n'):
            # CRLF source: replace the binding as a single logical expression.
            hostile = CLOCK.replace(
                'Qt.formatDateTime(currentTime, "ddd d MMM") + " · " +',
                'Qt.formatDateTime(currentTime, "ddd d MMM  h:mm AP") +', 1)
        self.assertNotEqual(hostile, CLOCK)
        with self.assertRaises(AssertionError):
            check_clock(hostile)


if __name__ == "__main__":
    unittest.main()
