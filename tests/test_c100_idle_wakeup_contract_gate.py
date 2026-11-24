"""Bounded regression gate for the measured Classic Qt idle-wakeup contract.

Runtime evidence on the Windows host (QT_QPA_PLATFORM=offscreen, 15 s idle,
454 samples): 0.00% CPU of one core, 0 active 20 ms CPU windows, ~65.5 MiB
working set. The mechanism behind that profile is one wall-clock-aligned
60-second one-shot QML timer with no animation loop. This gate is a static,
deterministic guard on that mechanism; it deliberately contains no timing
threshold, because the host is noisy. It is NOT Mint acceptance evidence.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic" / "ClockLabel.qml"
MAX_SOURCE_BYTES = 16_384
FORBIDDEN_WAKEUP_TYPES = (
    "NumberAnimation", "PropertyAnimation", "SequentialAnimation",
    "ParallelAnimation", "PauseAnimation", "SmoothedAnimation",
    "SpringAnimation", "AnchorAnimation", "Behavior on",
    "setInterval", "setTimeout",
)


def check_idle_contract(text):
    """Fail closed unless the clock keeps exactly one 60 s one-shot timer."""
    if not isinstance(text, str):
        raise AssertionError("ClockLabel source must be text")
    if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise AssertionError("ClockLabel source is unexpectedly large")
    if text.count("Timer {") != 1:
        raise AssertionError("expected exactly one clock Timer")
    blocks = re.findall(r"Timer\s*\{([^{}]*)\}", text)
    if len(blocks) != 1:
        raise AssertionError("clock Timer block is not statically parseable")
    block = blocks[0]
    for required in ("interval: 60000", "repeat: false", "running: false",
                     "onTriggered: clock.refreshClock()"):
        if required not in block:
            raise AssertionError("clock Timer lost " + required)
    if "readonly property bool refreshScheduled: nextMinute.running" not in text:
        raise AssertionError("refreshScheduled no longer reports the timer")
    if "60000 -" not in text or "nextMinute.restart()" not in text:
        raise AssertionError("wall-clock-aligned minute wakeup was removed")
    for token in FORBIDDEN_WAKEUP_TYPES:
        if token in text:
            raise AssertionError("per-frame/animation wakeup introduced: " + token)
    return True


class IdleWakeupContractGate(unittest.TestCase):
    def test_compiled_source_keeps_measured_idle_contract(self):
        check_idle_contract(SOURCE.read_text(encoding="utf-8"))

    def test_gate_rejects_a_per_frame_timer_variant(self):
        source = SOURCE.read_text(encoding="utf-8")
        hostile = source.replace("interval: 60000", "interval: 16", 1).replace(
            "repeat: false", "repeat: true", 1)
        self.assertNotEqual(hostile, source)
        with self.assertRaises(AssertionError):
            check_idle_contract(hostile)


if __name__ == "__main__":
    unittest.main()
