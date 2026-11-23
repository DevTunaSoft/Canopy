"""Offline unit tests for memory_delta: synthetic numbers test logic only.

No memory is sampled here and no Linux Mint or compiled Qt result is claimed.
"""
import json
import unittest

from canopy_features.performance.memory_delta import (
    MAX_SAMPLES, MemorySample, SampleError, delta, report_growth,
)


def sample(interaction, kib):
    return MemorySample(interaction=interaction, memory_kib=kib)


class MemoryDeltaTests(unittest.TestCase):
    def test_positive_growth_across_interactions(self):
        result = report_growth([
            sample(0, 120_000), sample(1, 131_000), sample(2, 145_000),
        ])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["start_kib"], 120_000)
        self.assertEqual(result["end_kib"], 145_000)
        self.assertEqual(result["delta_kib"], 25_000)
        self.assertEqual(result["sample_count"], 3)
        self.assertEqual(result["interactions"], 2)
        self.assertEqual(result["peak_kib"], 145_000)
        self.assertEqual(result["min_kib"], 120_000)
        self.assertGreater(result["mean_growth_per_interaction_kib"], 0)

    def test_negative_delta_reported_not_clamped(self):
        result = delta(sample(0, 200_000), sample(3, 180_000))
        self.assertEqual(result["delta_kib"], -20_000)
        self.assertEqual(result["delta_percent"], -10.0)
        self.assertEqual(result["interactions"], 3)
        series = report_growth([
            sample(0, 200_000), sample(1, 190_000), sample(2, 180_000),
        ])
        self.assertEqual(series["delta_kib"], -20_000)
        self.assertLess(series["mean_growth_per_interaction_kib"], 0)
        self.assertEqual(series["min_kib"], 180_000)

    def test_missing_start_and_end_are_errors(self):
        with self.assertRaisesRegex(SampleError, "missing start sample"):
            delta(None, sample(1, 100))
        with self.assertRaisesRegex(SampleError, "missing end sample"):
            delta(sample(0, 100), None)
        with self.assertRaisesRegex(SampleError, "missing start and end samples"):
            report_growth([])
        with self.assertRaisesRegex(SampleError, "missing end sample"):
            report_growth([sample(0, 100)])

    def test_zero_baseline_percent_is_none(self):
        result = delta(sample(0, 0), sample(1, 4096))
        self.assertEqual(result["delta_kib"], 4096)
        self.assertIsNone(result["delta_percent"])

    def test_rejects_invalid_and_unbounded_samples(self):
        bad_samples = (
            MemorySample(interaction=-1, memory_kib=100),
            MemorySample(interaction=0, memory_kib=-1),
            MemorySample(interaction=0, memory_kib=True),
            MemorySample(interaction=0, memory_kib=10 ** 12),
        )
        for bad in bad_samples:
            with self.subTest(bad=bad):
                with self.assertRaises(SampleError):
                    report_growth([bad, sample(1, 100)])
        with self.assertRaisesRegex(SampleError, "must be a MemorySample"):
            report_growth([(0, 100), sample(1, 100)])
        with self.assertRaisesRegex(SampleError, "precedes start"):
            delta(sample(2, 100), sample(1, 100))

    def test_bounded_sample_count(self):
        many = (sample(0, 100) for _ in range(MAX_SAMPLES + 1))
        with self.assertRaisesRegex(SampleError, "exceeds bound"):
            report_growth(many)

    def test_generator_of_samples_is_supported(self):
        result = report_growth(sample(i, 100 + i) for i in range(4))
        self.assertEqual(result["sample_count"], 4)
        self.assertEqual(result["delta_kib"], 3)

    def test_report_is_json_serializable(self):
        result = report_growth([sample(0, 100), sample(1, 120)])
        self.assertEqual(json.loads(json.dumps(result)), result)


if __name__ == "__main__":
    unittest.main()
