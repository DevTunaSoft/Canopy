"""Offline unit tests for monotonic bounded idle-CPU sampling.

No real Qt, Linux Mint, or host measurement is performed here.
"""
from pathlib import Path
import unittest

from canopy_features.performance.cpu_idle_samples import (
    MAX_SAMPLES, MAX_TICKS, CounterResetError, CpuIdleSamples, CpuSample,
    SampleError, ZeroDurationError, idle_percentage,
)


def sample(t, idle, total):
    return CpuSample(t, idle, total)


class IdlePercentageTests(unittest.TestCase):
    def test_fully_idle_and_fully_busy(self):
        a = sample(10.0, 100, 1000)
        b = sample(11.0, 1100, 2000)  # all 1000 new ticks idle
        self.assertAlmostEqual(idle_percentage(a, b), 100.0)
        c = sample(12.0, 1100, 3000)  # all 1000 new ticks busy
        self.assertAlmostEqual(idle_percentage(b, c), 0.0)

    def test_mixed_idle_fraction(self):
        a = sample(0.0, 100, 1000)
        b = sample(2.5, 160, 1500)    # 60 idle of 500 new ticks -> 12%
        self.assertAlmostEqual(idle_percentage(a, b), 12.0)

    def test_counter_reset_raises_distinct_error(self):
        a = sample(1.0, 300, 900)
        for bad in (sample(2.0, 50, 950),    # idle counter dropped
                    sample(2.0, 310, 850)):  # total counter dropped
            with self.subTest(bad=bad):
                with self.assertRaises(CounterResetError) as ctx:
                    idle_percentage(a, bad)
                self.assertIsInstance(ctx.exception, SampleError)

    def test_zero_duration_raises(self):
        a = sample(5.0, 100, 1000)
        b = sample(5.0, 110, 1100)    # identical timestamp
        with self.assertRaises(ZeroDurationError) as ctx:
            idle_percentage(a, b)
        self.assertIsInstance(ctx.exception, SampleError)

    def test_no_total_progress_raises(self):
        a = sample(5.0, 100, 1000)
        b = sample(6.0, 100, 1000)    # total_ticks unchanged
        with self.assertRaises(SampleError):
            idle_percentage(a, b)

    def test_non_monotonic_time_raises(self):
        with self.assertRaises(SampleError):
            idle_percentage(sample(6.0, 100, 1000), sample(5.0, 110, 1100))

    def test_invalid_samples_rejected(self):
        good = sample(5.0, 100, 1000)
        bad_samples = (
            ("not a sample", None),
            ("bool time", CpuSample(True, 100, 1000)),
            ("nan time", CpuSample(float("nan"), 100, 1000)),
            ("infinite time", CpuSample(float("inf"), 100, 1000)),
            ("negative time", sample(-1.0, 100, 1000)),
            ("bool tick", CpuSample(1.0, True, 1000)),
            ("float tick", CpuSample(1.0, 100.0, 1000)),
            ("negative tick", sample(1.0, -1, 1000)),
            ("idle exceeds total", sample(1.0, 1100, 1000)),
            ("counter over bound", sample(1.0, 100, MAX_TICKS + 1)),
        )
        for label, bad in bad_samples:
            with self.subTest(label=label):
                with self.assertRaises(SampleError):
                    idle_percentage(bad, good)


class CpuIdleSamplesTests(unittest.TestCase):
    def test_bounded_history_keeps_newest_pair(self):
        meter = CpuIdleSamples(max_samples=3)
        for i in range(10):
            meter.add(sample(float(i), i * 10, i * 100 + 1000))
        self.assertEqual(len(meter), 3)
        # Samples 8 and 9: idle +10 of total +100 -> 10%.
        self.assertAlmostEqual(meter.latest_idle_percentage(), 10.0)

    def test_add_rejects_reset_without_mutating(self):
        meter = CpuIdleSamples()
        meter.add(sample(1.0, 300, 900))
        meter.add(sample(2.0, 320, 1000))
        with self.assertRaises(CounterResetError):
            meter.add(sample(3.0, 10, 1100))
        self.assertEqual(len(meter), 2)
        meter.reset()
        self.assertEqual(len(meter), 0)

    def test_add_rejects_non_monotonic_time_and_zero_duration_pair(self):
        meter = CpuIdleSamples()
        meter.add(sample(2.0, 100, 1000))
        with self.assertRaises(SampleError):
            meter.add(sample(1.0, 110, 1100))
        self.assertEqual(len(meter), 1)
        meter.add(sample(2.0, 110, 1100))  # same time is stored...
        with self.assertRaises(ZeroDurationError):
            meter.latest_idle_percentage()  # ...but cannot yield a percentage

    def test_requires_two_samples_and_valid_capacity(self):
        meter = CpuIdleSamples()
        with self.assertRaises(SampleError):
            meter.latest_idle_percentage()
        for bad in (1, True, MAX_SAMPLES + 1, 2.0):
            with self.subTest(bad=bad):
                with self.assertRaises(SampleError):
                    CpuIdleSamples(max_samples=bad)


class NoBackgroundWorkTests(unittest.TestCase):
    def test_source_has_no_polling_or_service_hooks(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/performance/cpu_idle_samples.py").read_text()
        for token in ("time.sleep", "QTimer", "while True", "threading",
                      "subprocess", "socket", "import os", "open("):
            with self.subTest(token=token):
                self.assertNotIn(token, code)


if __name__ == "__main__":
    unittest.main()
