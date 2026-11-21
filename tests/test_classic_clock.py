"""Source-level contracts for the live Classic top-bar clock.

The compiled Qt screenshot smoke test in main.cpp supplies runtime evidence.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "prototype" / "classic"


class ClassicClockContractTests(unittest.TestCase):
    def test_registered_as_one_embedded_component(self):
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        main = (ROOT / "Main.qml").read_text(encoding="utf-8")
        self.assertEqual(cmake.count("ClockLabel.qml"), 1)
        self.assertIn("ClockLabel {", main)
        self.assertNotIn('Qt.formatDateTime(new Date(), "ddd d MMM")', main)
        self.assertNotIn("Timer {", main)
        self.assertTrue((ROOT / "ClockLabel.qml").is_file())

    def test_clock_is_minute_driven_and_resynchronizes(self):
        clock = (ROOT / "ClockLabel.qml").read_text(encoding="utf-8")
        self.assertIn('objectName: "canopyTopBarClock"', clock)
        self.assertIn("property date currentTime: new Date()", clock)
        self.assertIn("Qt.formatDateTime(currentTime", clock)
        self.assertIn("getSeconds()", clock)
        self.assertIn("getMilliseconds()", clock)
        self.assertIn("60000 -", clock)
        self.assertIn("repeat: false", clock)
        self.assertIn("running: false", clock)
        self.assertIn("onTriggered: clock.refreshClock()", clock)
        self.assertIn("Component.onCompleted: refreshClock()", clock)
        self.assertIn("onVisibleChanged:", clock)
        self.assertIn("Qt.ApplicationActive", clock)
        self.assertIn('Accessible.name: "Local date and time: " + text', clock)
        self.assertNotIn("NumberAnimation", clock)
        self.assertNotIn("ShaderEffect", clock)
        self.assertNotIn("setInterval", clock)
        self.assertEqual(len(re.findall(r"\\bTimer\\s*\\{", clock)), 1)

    def test_real_compiled_qt_test_exercises_binding_and_bounds(self):
        cpp = (ROOT / "main.cpp").read_text(encoding="utf-8")
        self.assertIn('QStringLiteral("canopyTopBarClock")', cpp)
        self.assertIn('clock->property("refreshScheduled").toBool()', cpp)
        self.assertIn('clock->setProperty("currentTime", controlledMoment)', cpp)
        self.assertIn('updatedText == originalText', cpp)
        self.assertIn('clockOrigin.x() + clock->width() > window->width()', cpp)
        self.assertIn('SELF_TEST_PASS: local top bar clock updates and fits', cpp)
        self.assertIn('SELF_TEST_FAIL: local clock text is frozen', cpp)


if __name__ == "__main__":
    unittest.main()
