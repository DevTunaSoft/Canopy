"""Prevent the real 150%-scaling screenshot failure from regressing."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ClassicHighDpiTests(unittest.TestCase):
    def test_qt_compares_actual_physical_image_sizes_not_logical_window(self):
        cpp = (ROOT / "prototype/classic/main.cpp").read_text(encoding="utf-8")
        self.assertIn("const QSize desktopPhysicalPixels = frame.size()", cpp)
        self.assertIn("launcherFrame.size() != desktopPhysicalPixels", cpp)
        self.assertNotIn("launcherFrame.width() != window->width()", cpp)
        self.assertNotIn("launcherFrame.height() != window->height()", cpp)
        self.assertIn("QTimer::singleShot(250, window", cpp)
        self.assertIn("!launcherFrame.save(launcherScreenshotPath", cpp)

    def test_ci_runs_fractional_and_retina_dpi_on_compiled_qt(self):
        workflow = (ROOT / ".github/workflows/classic-qt.yml").read_text(encoding="utf-8")
        self.assertIn("for scale in 1.25 1.5 2.0; do", workflow)
        self.assertIn('QT_SCALE_FACTOR="$scale"', workflow)
        self.assertIn("--self-test-launcher-screenshot", workflow)
        self.assertIn('verify_png(path, width, height)', workflow)
        self.assertIn('HIDPI_QT_SCREENSHOT_PASS', workflow)
        self.assertIn('dimensions[0] == dimensions[1]', workflow)


if __name__ == "__main__":
    unittest.main()
