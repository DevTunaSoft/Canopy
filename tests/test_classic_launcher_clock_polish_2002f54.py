"""Source-level gate for the 2002f54 premium launcher/clock polish pass.

These checks are deterministic and offline. They do not replace compilation,
real Qt screenshots or owner visual approval; they fail closed if a later edit
silently drops the keyboard hints, the grid selected state or the explicit
clock separator, or if it reintroduces wakeup/effect machinery.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "prototype" / "classic" / "LauncherOverlay.qml"
CLOCK = ROOT / "prototype" / "classic" / "ClockLabel.qml"

FORBIDDEN_EFFECTS = (
    "NumberAnimation", "PropertyAnimation", "SequentialAnimation",
    "ParallelAnimation", "PauseAnimation", "SmoothedAnimation",
    "SpringAnimation", "AnchorAnimation", "Behavior on", "ShaderEffect",
    "setInterval", "setTimeout", "Timer {", "Qt.createProcess", "QProcess",
)
APPROVED_COLORS = ("#263a4f", "#2b3e52", "#2c4055", "#5687b3", "#5c8fb8",
                   "#657b90", "#690d1a2b", "#b7d0dce8", "#cad7e2", "#dceaf5",
                   "#f3f8fc", "#ffffff")


def check_launcher(text):
    """Fail closed unless the premium launcher contract is intact."""
    if not isinstance(text, str):
        raise AssertionError("launcher source must be text")
    required = (
        'objectName: "canopyLauncherKeyHints"',
        'id: keyHints',
        'text: "Up/Down select · Enter open · Esc close"',
        'Accessible.name: "Launcher keyboard shortcuts: " + text',
        'anchors.bottom: keyHints.top',
        'grid.activeFocus && grid.currentIndex === appButton.index',
        'font.pixelSize: 13',
        'font.weight: Font.Medium',
        'font.pixelSize: 15',
        'anchors.topMargin: 16',
    )
    for token in required:
        if token not in text:
            raise AssertionError("launcher lost " + token)
    if text.count("grid.activeFocus && grid.currentIndex === appButton.index") < 2:
        raise AssertionError("selected state must drive fill and border")
    if "border.width: appButton.activeFocus ||" not in text:
        raise AssertionError("selected state lost its focus border")
    if "width < 470 ? 3 : 4" not in text:
        raise AssertionError("responsive column contract changed")
    if "panel.height < 410 ? 98 : 116" not in text:
        raise AssertionError("frozen cell-height contract changed")
    for token in FORBIDDEN_EFFECTS:
        if token in text:
            raise AssertionError("launcher introduced forbidden machinery: " + token)
    for match in re.findall(r'#[0-9a-fA-F]{3,8}\b', text):
        if match.lower() not in APPROVED_COLORS:
            raise AssertionError("launcher introduced an unapproved colour: " + match)
    return True


def check_clock(text):
    """Fail closed unless the clock separator and one-shot wakeup survive."""
    if not isinstance(text, str):
        raise AssertionError("clock source must be text")
    if 'text: Qt.formatDateTime(currentTime, "ddd d MMM") + " · " +\n' not in text:
        raise AssertionError("explicit date/time separator missing")
    if 'Qt.formatTime(currentTime, "h:mm AP")' not in text:
        raise AssertionError("12-hour time formatting lost")
    if 'color: "#f7f5eb"' not in text or "font.pixelSize: 12" not in text \
            or "font.weight: Font.Medium" not in text:
        raise AssertionError("approved clock typography changed")
    if text.count("Timer {") != 1:
        raise AssertionError("expected exactly one clock Timer")
    blocks = re.findall(r"Timer\s*\{([^{}]*)\}", text)
    if len(blocks) != 1:
        raise AssertionError("clock Timer block is not statically parseable")
    for required in ("interval: 60000", "repeat: false", "running: false",
                     "onTriggered: clock.refreshClock()"):
        if required not in blocks[0]:
            raise AssertionError("clock Timer lost " + required)
    if "readonly property bool refreshScheduled: nextMinute.running" not in text:
        raise AssertionError("refreshScheduled no longer reports the timer")
    if "60000 -" not in text or "nextMinute.restart()" not in text:
        raise AssertionError("wall-clock-aligned minute wakeup removed")
    for token in FORBIDDEN_EFFECTS:
        if token == "Timer {":
            continue
        if token in text:
            raise AssertionError("clock introduced forbidden machinery: " + token)
    return True


class ClassicLauncherClockPolishTests(unittest.TestCase):
    def setUp(self):
        self.launcher = LAUNCHER.read_text(encoding="utf-8")
        self.clock = CLOCK.read_text(encoding="utf-8")

    def test_checked_in_launcher_keeps_hints_selected_state_and_readability(self):
        self.assertTrue(check_launcher(self.launcher))

    def test_checked_in_clock_keeps_separator_and_idle_contract(self):
        self.assertTrue(check_clock(self.clock))

    def test_negative_control_dropped_hints_fail(self):
        hostile = self.launcher.replace(
            '        text: "Up/Down select · Enter open · Esc close"\n', "", 1)
        self.assertNotEqual(hostile, self.launcher)
        with self.assertRaises(AssertionError):
            check_launcher(hostile)

    def test_negative_control_dropped_selected_state_fail(self):
        hostile = self.launcher.replace(
            "grid.activeFocus && grid.currentIndex === appButton.index",
            "appButton.hovered", 2)
        self.assertNotEqual(hostile, self.launcher)
        with self.assertRaises(AssertionError):
            check_launcher(hostile)

    def test_negative_control_new_colour_fails(self):
        hostile = self.launcher.replace('"#dceaf5"', '"#ddeeff"', 1)
        self.assertNotEqual(hostile, self.launcher)
        with self.assertRaises(AssertionError):
            check_launcher(hostile)

    def test_negative_control_per_frame_clock_fails(self):
        hostile = self.clock.replace("interval: 60000", "interval: 16", 1).replace(
            "repeat: false", "repeat: true", 1)
        self.assertNotEqual(hostile, self.clock)
        with self.assertRaises(AssertionError):
            check_clock(hostile)

    def test_negative_control_ambiguous_clock_separator_fails(self):
        hostile = self.clock.replace(' + " · " +', ' + "  " +', 1)
        self.assertNotEqual(hostile, self.clock)
        with self.assertRaises(AssertionError):
            check_clock(hostile)


if __name__ == "__main__":
    unittest.main()
