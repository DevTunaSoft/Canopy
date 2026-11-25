"""Offline gates for Classic clock-label readability, a11y and contrast.

These checks are deterministic: they read the checked-in QML plus the SHA-locked
approved wallpaper PNG and use the repository's WCAG contrast helpers. They do
not compile Qt, launch a screen reader or claim Linux Mint acceptance.
"""
from __future__ import annotations

import re
import struct
import unittest
import zlib
from pathlib import Path

from canopy_features.accessibility.contrast_audit import (
    AA_NORMAL,
    composite,
    contrast_ratio,
    parse_color,
)

ROOT = Path(__file__).resolve().parents[1]
CLOCK = ROOT / "prototype" / "classic" / "ClockLabel.qml"
THEME = ROOT / "prototype" / "classic" / "Theme.qml"
WALLPAPER = (ROOT / "prototype" / "classic" / "assets" / "approved" /
             "wallpaper" / "canopy-wave-preview.png")

APPROVED_PLATE = "#995e89a9"   # Main.qml approved-mode top-bar plate
LIGHT_PLATE_INK = "#1f2326"    # dark ink for the translucent light plate
DARK_PLATE_INK = "#f7f5eb"     # original off-white for the dark chrome
MAX_CLOCK_BYTES = 16_384
FORBIDDEN_WAKEUPS = (
    "NumberAnimation", "PropertyAnimation", "SequentialAnimation",
    "ParallelAnimation", "PauseAnimation", "SmoothedAnimation",
    "SpringAnimation", "AnchorAnimation", "Behavior on",
    "setInterval", "setTimeout", "QProcess", "Qt.createProcess",
)


def check_clock_source(text: str) -> bool:
    """Fail closed unless the readable, accessible idle contract survives."""
    if not isinstance(text, str):
        raise AssertionError("ClockLabel source must be text")
    if len(text.encode("utf-8")) > MAX_CLOCK_BYTES:
        raise AssertionError("ClockLabel source is unexpectedly large")

    # Visible geometry/typography and the explicit separator stay frozen.
    if 'text: Qt.formatDateTime(currentTime, "ddd d MMM") + " · " +\n' not in text:
        raise AssertionError("explicit date/time separator missing")
    if 'Qt.formatTime(currentTime, "h:mm AP")' not in text:
        raise AssertionError("12-hour visible time formatting lost")
    if "font.pixelSize: 12" not in text or "font.weight: Font.Medium" not in text:
        raise AssertionError("approved clock typography changed")

    # Screen-reader name must spell out weekday and month, not the compact
    # visible abbreviations.
    if 'readonly property string spokenDateTime: Qt.formatDate(currentTime, "dddd, d MMMM") +' not in text:
        raise AssertionError("unabbreviated spoken date missing")
    if '", " + Qt.formatTime(currentTime, "h:mm AP")' not in text:
        raise AssertionError("spoken time missing from accessible name")
    if 'Accessible.name: "Local date and time: " + spokenDateTime' not in text:
        raise AssertionError("Accessible.name no longer uses the spoken date")
    if 'Accessible.name: "Local date and time: " + text' in text:
        raise AssertionError("Accessible.name fell back to abbreviated text")
    if "Accessible.role: Accessible.StaticText" not in text:
        raise AssertionError("static-text role lost")

    # Contrast-aware ink selection; both literals are approved colours.
    if 'color: canopyApprovedMode ? "#1f2326" : "#f7f5eb"' not in text:
        raise AssertionError("approved-mode dark ink or dark-chrome off-white lost")

    # Exactly one wall-clock-aligned, non-repeating timer.
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
    if "function nextMinuteDelay(now)" not in text:
        raise AssertionError("wall-clock delay helper missing")
    if "Math.max(1, 60000 -" not in text \
            or "now.getSeconds() * 1000 + now.getMilliseconds()" not in text:
        raise AssertionError("minute delay is no longer wall-clock aligned")
    if "const now = new Date()" not in text \
            or "nextMinute.interval = nextMinuteDelay(now)" not in text:
        raise AssertionError("refresh does not re-arm from the current wall clock")
    if "if (visible)" not in text or "nextMinute.restart()" not in text:
        raise AssertionError("hidden clocks no longer suppress the wakeup")
    if "nextMinute.stop()" not in text \
            or "Qt.application.state === Qt.ApplicationActive" not in text \
            or "Component.onCompleted: refreshClock()" not in text:
        raise AssertionError("visibility/application-resume rearm contract changed")
    for token in FORBIDDEN_WAKEUPS:
        if token in text:
            raise AssertionError("clock introduced forbidden machinery: " + token)
    return True


def minute_delay_ms(seconds: int, milliseconds: int) -> int:
    """Python model of the QML delay; one boundary, never a polling cadence."""
    if not isinstance(seconds, int) or not isinstance(milliseconds, int):
        raise AssertionError("minute components must be integers")
    if not 0 <= seconds < 60 or not 0 <= milliseconds < 1000:
        raise AssertionError("minute components out of range")
    return max(1, 60000 - (seconds * 1000 + milliseconds))


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distances = (abs(estimate - left), abs(estimate - above),
                 abs(estimate - upper_left))
    if distances[0] <= distances[1] and distances[0] <= distances[2]:
        return left
    if distances[1] <= distances[2]:
        return above
    return upper_left


def decode_png_rgb(path: Path):
    """Decode a bounded 8-bit non-interlaced RGB PNG with the stdlib only."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("approved wallpaper is not a PNG")
    offset = 8
    compressed = []
    width = height = None
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 8 + length
        if end + 4 > len(data):
            raise AssertionError("truncated PNG chunk")
        payload = data[offset + 8:end]
        if kind == b"IHDR":
            if len(payload) != 13:
                raise AssertionError("malformed PNG IHDR")
            width, height, depth, colour, _, _, interlace = struct.unpack(
                ">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.append(payload)
        elif kind == b"IEND":
            break
        offset = end + 4
    if not width or not height or width > 8192 or height > 8192:
        raise AssertionError("unbounded PNG dimensions")
    if (depth, colour, interlace) != (8, 2, 0):
        raise AssertionError("approved wallpaper must be 8-bit RGB, non-interlaced")
    raw = zlib.decompress(b"".join(compressed))
    stride = width * 3
    if len(raw) != height * (stride + 1):
        raise AssertionError("unexpected PNG scanline size")
    rows = []
    previous = bytearray(stride)
    for y in range(height):
        base = y * (stride + 1)
        filter_type = raw[base]
        line = bytearray(raw[base + 1:base + stride + 1])
        if filter_type == 0:
            pass
        elif filter_type == 1:
            for i in range(3, stride):
                line[i] = (line[i] + line[i - 3]) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = line[i - 3] if i >= 3 else 0
                line[i] = (line[i] + ((left + previous[i]) // 2)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                left = line[i - 3] if i >= 3 else 0
                line[i] = (line[i] + _paeth(left, previous[i],
                                            previous[i - 3] if i >= 3 else 0)) & 0xFF
        else:
            raise AssertionError("unsupported PNG filter")
        rows.append(bytes(line))
        previous = line
    return width, height, rows


def wallpaper_top_colors():
    """Bounded sample of the approved wallpaper behind the top-bar plate."""
    width, height, rows = decode_png_rgb(WALLPAPER)
    row_step = max(1, height // 120)
    col_step = max(1, width // 64)
    colors = []
    for y in range(0, min(height, max(2, height // 20)), row_step):
        row = rows[y]
        for x in range(0, width, col_step):
            r, g, b = row[3 * x:3 * x + 3]
            colors.append("#%02x%02x%02x" % (r, g, b))
    if len(colors) < 64:
        raise AssertionError("insufficient wallpaper samples")
    return colors


def worst_plate_ratio(ink: str) -> float:
    plate = parse_color(APPROVED_PLATE)
    return min(contrast_ratio(ink, composite(plate, parse_color(bg)))
               for bg in wallpaper_top_colors())


def dark_chrome_color() -> str:
    theme = THEME.read_text(encoding="utf-8")
    match = re.search(r'readonly property color chrome: "(#[0-9a-fA-F]+)"', theme)
    if not match:
        raise AssertionError("dark chrome colour missing from Theme.qml")
    return match.group(1)


class ClockLabelPolishTests(unittest.TestCase):
    def setUp(self):
        self.source = CLOCK.read_text(encoding="utf-8")

    def test_checked_in_clock_keeps_readable_accessible_idle_contract(self):
        self.assertTrue(check_clock_source(self.source))

    def test_exposed_delay_is_aligned_to_one_minute(self):
        self.assertIn("Math.max(1, 60000 -", self.source)
        for seconds in range(60):
            for milliseconds in (0, 1, 250, 999):
                with self.subTest(seconds=seconds, milliseconds=milliseconds):
                    delay = minute_delay_ms(seconds, milliseconds)
                    self.assertTrue(1 <= delay <= 60000)
                    self.assertEqual((seconds * 1000 + milliseconds + delay) % 60000, 0)

    def test_negative_control_compact_accessible_name_fails(self):
        hostile = self.source.replace(
            'Accessible.name: "Local date and time: " + spokenDateTime',
            'Accessible.name: "Local date and time: " + text', 1)
        self.assertNotEqual(hostile, self.source)
        with self.assertRaises(AssertionError):
            check_clock_source(hostile)

    def test_negative_control_unaligned_delay_fails(self):
        hostile = self.source.replace(
            "now.getSeconds() * 1000 + now.getMilliseconds()",
            "now.getSeconds() * 1000", 1)
        self.assertNotEqual(hostile, self.source)
        with self.assertRaises(AssertionError):
            check_clock_source(hostile)

    def test_negative_control_per_second_timer_fails(self):
        hostile = self.source.replace("interval: 60000", "interval: 1000", 1)
        self.assertNotEqual(hostile, self.source)
        with self.assertRaises(AssertionError):
            check_clock_source(hostile)


class ClockContrastTests(unittest.TestCase):
    def test_approved_light_plate_dark_ink_meets_aa(self):
        worst = worst_plate_ratio(LIGHT_PLATE_INK)
        self.assertGreaterEqual(worst, AA_NORMAL)

    def test_legacy_offwhite_on_approved_plate_fails_negative_control(self):
        worst = worst_plate_ratio(DARK_PLATE_INK)
        self.assertLess(worst, AA_NORMAL)

    def test_dark_chrome_keeps_aa_with_original_offwhite(self):
        chrome = dark_chrome_color()
        ratio = min(contrast_ratio(DARK_PLATE_INK,
                                   composite(parse_color(chrome), parse_color(bg)))
                    for bg in wallpaper_top_colors())
        self.assertGreaterEqual(ratio, AA_NORMAL)

    def test_source_selects_the_measured_ink_for_each_plate(self):
        source = CLOCK.read_text(encoding="utf-8")
        self.assertIn('"#1f2326"', source)
        self.assertIn('"#f7f5eb"', source)
        self.assertTrue(check_clock_source(source))


if __name__ == "__main__":
    unittest.main()
