"""Offline gate: Classic clock accessibility change with frozen visual inputs.

Deterministic and offline. The gate reads the checked-in QML and fails closed if
any rendering input (visible text, approved ink, typography or wakeup) changes.
It never compiles Qt, launches a screen reader, or claims Mint acceptance.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOCK = ROOT / "prototype" / "classic" / "ClockLabel.qml"
MAX_CLOCK_BYTES = 16_384
APPROVED_INK = '"#f7f5eb"'
REJECTED_INK = "#1f2326"
# Every literal below feeds rendered pixels or the wakeup cadence.
FROZEN_VISIBLE_LINES = (
    'text: Qt.formatDateTime(currentTime, "ddd d MMM") + " · " +',
    'Qt.formatTime(currentTime, "h:mm AP")',
    'color: "#f7f5eb"',
    "font.pixelSize: 12",
    "font.weight: Font.Medium",
    "interval: 60000",
    "repeat: false",
    "running: false",
    "readonly property bool refreshScheduled: nextMinute.running",
)
SPOKEN_DATE_LINE = (
    'readonly property string spokenDateTime: '
    'Qt.formatDate(currentTime, "dddd, d MMMM") +'
)
SPOKEN_TIME_LINE = ', " + Qt.formatTime(currentTime, "h:mm AP")'
SPOKEN_NAME_LINE = 'Accessible.name: "Local date and time: " + spokenDateTime'
COMPACT_NAME_LINE = 'Accessible.name: "Local date and time: " + text'
FORBIDDEN_WAKEUPS = (
    "NumberAnimation", "PropertyAnimation", "SequentialAnimation",
    "ParallelAnimation", "PauseAnimation", "SmoothedAnimation",
    "SpringAnimation", "AnchorAnimation", "Behavior on",
    "setInterval", "setTimeout", "QProcess", "Qt.createProcess",
)


def normalized(text: str) -> str:
    """Normalize line endings so the source gate works on CRLF checkouts."""
    if not isinstance(text, str):
        raise AssertionError("ClockLabel source must be text")
    return text.replace("\r\n", "\n")


def check_clock_source(text: str) -> bool:
    """Fail closed unless only the accessible name changed."""
    source = normalized(text)
    if len(source.encode("utf-8")) > MAX_CLOCK_BYTES:
        raise AssertionError("ClockLabel source is unexpectedly large")

    for line in FROZEN_VISIBLE_LINES:
        if line not in source:
            raise AssertionError("frozen visual/wakeup input changed: " + line)
    colors = re.findall(r"^\s*color\s*:\s*([^\n]+)$", source, re.MULTILINE)
    if colors != [APPROVED_INK]:
        raise AssertionError("approved ink binding changed: %r" % (colors,))
    if REJECTED_INK in source or "canopyApprovedMode" in source:
        raise AssertionError("pixel-changing ink proposal leaked into ClockLabel.qml")

    if SPOKEN_DATE_LINE not in source or SPOKEN_TIME_LINE not in source:
        raise AssertionError("unabbreviated spoken date/time missing")
    if SPOKEN_NAME_LINE not in source:
        raise AssertionError("Accessible.name no longer uses the spoken date")
    if COMPACT_NAME_LINE in source:
        raise AssertionError("Accessible.name fell back to abbreviated visible text")
    if "Accessible.role: Accessible.StaticText" not in source:
        raise AssertionError("static-text role lost")

    if source.count("Timer {") != 1:
        raise AssertionError("expected exactly one clock Timer")
    blocks = re.findall(r"Timer\s*\{([^{}]*)\}", source)
    if len(blocks) != 1:
        raise AssertionError("clock Timer block is not statically parseable")
    for required in ("interval: 60000", "repeat: false", "running: false",
                     "onTriggered: clock.refreshClock()"):
        if required not in blocks[0]:
            raise AssertionError("clock Timer lost " + required)
    if "const now = new Date()" not in source \
            or "nextMinute.interval = Math.max(1, 60000 -" not in source \
            or "now.getSeconds() * 1000 + now.getMilliseconds()" not in source:
        raise AssertionError("minute-aligned rearm changed")
    if "if (visible)" not in source or "nextMinute.restart()" not in source \
            or "nextMinute.stop()" not in source \
            or "Qt.application.state === Qt.ApplicationActive" not in source \
            or "Component.onCompleted: refreshClock()" not in source:
        raise AssertionError("visibility/application-resume contract changed")
    for token in FORBIDDEN_WAKEUPS:
        if token in source:
            raise AssertionError("clock introduced forbidden machinery: " + token)
    return True


def minute_delay_ms(seconds: int, milliseconds: int) -> int:
    """Python mirror of the unchanged QML wall-clock delay."""
    if type(seconds) is not int or type(milliseconds) is not int:
        raise AssertionError("minute components must be integers")
    if not 0 <= seconds < 60 or not 0 <= milliseconds < 1000:
        raise AssertionError("minute components out of range")
    return max(1, 60000 - (seconds * 1000 + milliseconds))


class ClockAccessibilityNoVisualChangeTests(unittest.TestCase):
    def setUp(self):
        self.raw = CLOCK.read_bytes()
        self.source = self.raw.decode("utf-8")

    def test_checked_in_clock_keeps_a11y_only_contract(self):
        self.assertTrue(check_clock_source(self.source))

    def test_approved_ink_is_byte_identical(self):
        self.assertEqual(self.raw.count(b'color: "#f7f5eb"'), 1)
        self.assertNotIn(REJECTED_INK.encode("ascii"), self.raw)
        self.assertNotIn(b"canopyApprovedMode", self.raw)

    def test_visible_rendering_inputs_are_frozen(self):
        for line in FROZEN_VISIBLE_LINES:
            with self.subTest(line=line):
                self.assertIn(line, normalized(self.source))

    def test_exposed_delay_is_aligned_to_one_minute(self):
        for seconds in range(60):
            for milliseconds in (0, 1, 250, 999):
                with self.subTest(seconds=seconds, milliseconds=milliseconds):
                    delay = minute_delay_ms(seconds, milliseconds)
                    self.assertTrue(1 <= delay <= 60000)
                    self.assertEqual((seconds * 1000 + milliseconds + delay) % 60000, 0)

    def test_negative_control_compact_accessible_name_fails(self):
        hostile = normalized(self.source).replace(SPOKEN_NAME_LINE, COMPACT_NAME_LINE, 1)
        self.assertNotEqual(hostile, normalized(self.source))
        with self.assertRaises(AssertionError):
            check_clock_source(hostile)

    def test_negative_control_dark_ink_fails(self):
        hostile = normalized(self.source).replace(
            'color: "#f7f5eb"', 'color: canopyApprovedMode ? "#1f2326" : "#f7f5eb"', 1)
        self.assertNotEqual(hostile, normalized(self.source))
        with self.assertRaises(AssertionError):
            check_clock_source(hostile)

    def test_negative_control_changed_visible_text_fails(self):
        hostile = normalized(self.source).replace(
            '"ddd d MMM"', '"dddd, d MMMM"', 1)
        self.assertNotEqual(hostile, normalized(self.source))
        with self.assertRaises(AssertionError):
            check_clock_source(hostile)

    def test_negative_control_per_second_timer_fails(self):
        hostile = normalized(self.source).replace("interval: 60000", "interval: 1000", 1)
        self.assertNotEqual(hostile, normalized(self.source))
        with self.assertRaises(AssertionError):
            check_clock_source(hostile)


if __name__ == "__main__":
    unittest.main()
