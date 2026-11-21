"""Bound reproducible Qt screenshot comparisons without freezing live UI."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "prototype" / "classic" / "main.cpp"
WORKFLOW = ROOT / ".github" / "workflows" / "classic-qt.yml"


class FixedClockScreenshotTests(unittest.TestCase):
    def test_only_screenshot_test_mode_can_freeze_clock(self):
        code = CPP.read_text()
        self.assertIn('args.contains(QStringLiteral("--self-test-fixed-clock"))', code)
        self.assertIn("if (fixedCaptureClock && screenshotIndex < 0)", code)
        self.assertIn("if (!fixedCaptureClock)", code)
        self.assertIn('clock->setProperty("currentTime", originalTime)', code)
        self.assertIn("const QDateTime controlledMoment(QDate(2037, 4, 5), QTime(9, 41))", code)

    def test_fixed_clock_is_not_exposed_as_default(self):
        code = CPP.read_text()
        self.assertIn("const bool fixedCaptureClock =", code)
        self.assertNotIn("fixedCaptureClock = true;", code)
        self.assertIn("SELF_TEST_FAIL: --self-test-fixed-clock requires a screenshot", code)

    def test_ci_runs_real_qt_capture_with_stable_clock(self):
        workflow = WORKFLOW.read_text()
        self.assertIn("--self-test-fixed-clock", workflow)
        self.assertIn("classic-fixed-clock-desktop.png", workflow)
        self.assertIn("classic-fixed-clock-launcher.png", workflow)
        self.assertIn("python3 tools/check_screenshot.py", workflow)


if __name__ == "__main__":
    unittest.main()
