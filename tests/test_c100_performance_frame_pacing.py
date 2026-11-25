"""Offline tests for the frame-time distribution parser.

No real GPU, Linux Mint guest, or compiled Qt is used here. These synthetic
samples test only the parser's arithmetic, bounds, and provenance labels.
"""
import json
from pathlib import Path
import unittest

from canopy_features.performance import frame_pacing as fp


class FramePacingTests(unittest.TestCase):
    def test_distribution_and_percentiles(self):
        report = fp.parse_frame_times(
            [10.0, 20.0, 30.0, 40.0, 50.0], refresh_hz=60, backend="software")
        self.assertEqual(report.samples_total, 5)
        self.assertEqual(report.samples_valid, 5)
        self.assertEqual(report.samples_dropped, 0)
        self.assertEqual(report.min_ms, 10.0)
        self.assertEqual(report.max_ms, 50.0)
        self.assertEqual(report.mean_ms, 30.0)
        self.assertEqual(report.p50_ms, 30.0)
        self.assertEqual(report.p95_ms, 50.0)
        self.assertEqual(report.p99_ms, 50.0)
        self.assertEqual(report.frame_budget_ms, round(1000.0 / 60, 4))

    def test_dropped_samples_excluded_from_distribution(self):
        clean = [16.0, 16.0, 16.5]
        mixed = [None, float("nan"), float("inf"), -1.0, 0.0,
                 True, "16.7", 20000.0] + clean
        report = fp.parse_frame_times(mixed)
        self.assertEqual(report.samples_total, 11)
        self.assertEqual(report.samples_valid, 3)
        self.assertEqual(report.samples_dropped, 8)
        self.assertEqual(report.min_ms, 16.0)
        self.assertEqual(report.max_ms, 16.5)
        self.assertEqual(report.p50_ms, 16.0)
        self.assertEqual(report.dropped_frames, 0)

    def test_unknown_backend_is_reported_without_gpu_claim(self):
        report = fp.parse_frame_times([16.7], backend="metal")
        self.assertEqual(report.backend, "metal")
        self.assertFalse(report.backend_known)
        self.assertFalse(report.real_gpu_measurement)
        self.assertEqual(report.measurement_source, fp.MEASUREMENT_SOURCE)
        self.assertTrue(fp.parse_frame_times([16.7]).backend_known)

    def test_dropped_frames_over_refresh_budget(self):
        report = fp.parse_frame_times(
            [16.0, 16.0, 33.4, 16.0, 50.1], refresh_hz=60)
        self.assertEqual(report.dropped_frames, 2)
        self.assertEqual(report.dropped_frame_rate, 0.4)
        self.assertEqual(report.samples_dropped, 0)

    def test_single_sample_percentiles_are_that_sample(self):
        report = fp.parse_frame_times([8.0])
        self.assertEqual((report.p50_ms, report.p95_ms, report.p99_ms),
                         (8.0, 8.0, 8.0))

    def test_all_invalid_samples_raises(self):
        with self.assertRaisesRegex(fp.FramePacingError, "no valid"):
            fp.parse_frame_times([None, -1.0, float("nan")])

    def test_sample_count_is_bounded(self):
        with self.assertRaisesRegex(fp.FramePacingError, "bound"):
            fp.parse_frame_times([16.7] * (fp.MAX_SAMPLES + 1))

    def test_invalid_refresh_backend_and_container_rejected(self):
        with self.assertRaises(fp.FramePacingError):
            fp.parse_frame_times([16.7], refresh_hz=0)
        with self.assertRaises(fp.FramePacingError):
            fp.parse_frame_times([16.7], refresh_hz=60.0)
        with self.assertRaises(fp.FramePacingError):
            fp.parse_frame_times([16.7], backend=None)
        with self.assertRaises(fp.FramePacingError):
            fp.parse_frame_times(iter([16.7]))

    def test_report_is_json_serializable(self):
        report = fp.parse_frame_times([16.7, 33.4], backend="opengl")
        data = json.loads(json.dumps(report.as_dict()))
        self.assertEqual(data["backend"], "opengl")
        self.assertFalse(data["real_gpu_measurement"])

    def test_module_has_no_polling_or_service_hooks(self):
        source = (Path(fp.__file__)).read_text(encoding="utf-8")
        for forbidden in ("import socket", "import subprocess", "import threading",
                          "import time", "while True"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
