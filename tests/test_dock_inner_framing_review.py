"""Regression tests for strictly isolated optional dock optical framing."""
from pathlib import Path
import tempfile
import unittest

from tools.check_classic_icon_frame_diff import CENTERS, ComparisonError
from tools.check_dock_inner_framing import compare_dock_pair
from tests.test_classic_icon_frame_diff import make_rgba_png


class DockInnerFramingReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.a = Path(self.tmp.name) / "before.png"
        self.b = Path(self.tmp.name) / "after.png"
        self.size = "760x500"
        self.centers = CENTERS[self.size]["desktop"]
        self.a.write_bytes(make_rgba_png(760, 500))

    def simulate(self, changes):
        self.b.write_bytes(make_rgba_png(760, 500, changes))
        return compare_dock_pair(self.a, self.b, self.size)

    def test_desktop_capture_neutralizes_qt_hover_before_grab(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "prototype/classic/main.cpp").read_text()
        neutralize = "QCursor::setPos(window->mapToGlobal(QPoint(8, window->height() - 8)));"
        self.assertIn(neutralize, source)
        self.assertIn('setProperty("hoverEnabled", false)', source)
        self.assertIn("neutralizedHoverControls < 8", source)
        self.assertLess(source.index(neutralize),
                        source.index('setProperty("hoverEnabled", false)'))
        self.assertLess(source.index('setProperty("hoverEnabled", false)'),
                        source.index("const QImage frame = window->grabWindow()"))

    def test_all_eight_inner_art_changes_pass(self):
        result = self.simulate(self.centers)
        self.assertEqual(result["changed_icon_pixels"], 8)
        self.assertEqual(result["unexpected_changed_pixels"], 0)
        self.assertFalse(result["owner_visual_approval"])

    def test_one_icon_only_fails(self):
        with self.assertRaisesRegex(ComparisonError, "every dock icon"):
            self.simulate(self.centers[:1])

    def test_wallpaper_change_is_rejected(self):
        with self.assertRaisesRegex(ComparisonError, "unexpected non-icon"):
            self.simulate(self.centers + [(20, 200)])

    def test_clock_minute_rollover_is_tolerated_only_in_clock_region(self):
        result = self.simulate(self.centers + [(750, 10)])
        self.assertEqual(result["clock_delta_pixels"], 1)
        with self.assertRaisesRegex(ComparisonError, "unexpected non-icon"):
            self.simulate(self.centers + [(10, 10)])

    def test_card_corner_movement_is_rejected(self):
        cx, cy = self.centers[0]
        with self.assertRaisesRegex(ComparisonError, "silhouette corner"):
            self.simulate(self.centers + [(cx - 26, cy - 26)])

    def test_missing_and_mismatched_screenshots_fail_closed(self):
        with self.assertRaises(ComparisonError):
            self.simulate([])
        self.b.write_bytes(make_rgba_png(720, 480))
        with self.assertRaisesRegex(ComparisonError, "wrong screenshot dimensions"):
            compare_dock_pair(self.a, self.b, self.size)
        with self.assertRaisesRegex(ComparisonError, "unsupported"):
            compare_dock_pair(self.a, self.a, "640x480")

    def test_symlinked_screenshot_rejected(self):
        valid = Path(self.tmp.name) / "valid.png"
        valid.write_bytes(make_rgba_png(760, 500, self.centers))
        self.b.symlink_to(valid)
        with self.assertRaisesRegex(ComparisonError, "unsafe"):
            compare_dock_pair(self.a, self.b, self.size)


if __name__ == "__main__":
    unittest.main()
