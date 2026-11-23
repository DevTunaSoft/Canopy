"""Pure mechanical tests for visual centroid improvement & default checks."""
import unittest

from tools.check_classic_icon_frame_diff import ComparisonError
from tools.check_dock_optical_balance_quality import score_centers


NAMES = ("Browser", "Mail", "Files", "Calendar", "Photos", "Music",
         "Terminal", "Settings")
OLD = [(name, float(20 + i * 2), float(18 + i * 2))
       for i, name in enumerate(NAMES)]
GOOD = [(name, 26 + (i % 3 - 1) * 0.2,
         26 + (i % 3 - 1) * 0.2) for i, name in enumerate(NAMES)]


class DockOpticalBalanceQualityTests(unittest.TestCase):
    def test_measurable_improvement_in_both_axes(self):
        score = score_centers(OLD, GOOD)
        self.assertGreater(score["percent_reduction_x"], 20)
        self.assertGreater(score["percent_reduction_y"], 20)

    def test_same_artwork_or_no_improvement_rejected(self):
        with self.assertRaisesRegex(ComparisonError, "did not improve"):
            score_centers(OLD, OLD)

    def test_only_one_axis_improved_is_not_sufficient(self):
        partial = [(row[0], good[1], row[2]) for row, good in zip(OLD, GOOD)]
        with self.assertRaisesRegex(ComparisonError, "both axes"):
            score_centers(OLD, partial)

    def test_missing_duplicate_or_reordered_eight_rejected(self):
        with self.assertRaisesRegex(ComparisonError, "eight"):
            score_centers(OLD[:-1], GOOD[:-1])
        with self.assertRaisesRegex(ComparisonError, "order changed"):
            score_centers(OLD, list(reversed(GOOD)))

    def test_false_precision_from_uniform_reference_rejected(self):
        reference = [(name, 26.0, 26.0) for name in NAMES]
        with self.assertRaisesRegex(ComparisonError, "too small"):
            score_centers(reference, GOOD)


if __name__ == "__main__":
    unittest.main()
