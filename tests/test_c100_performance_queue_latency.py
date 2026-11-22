"""Offline unit tests: no real queue, Qt, Mint or desktop session is exercised."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import unittest

from canopy_features.performance.queue_latency import (
    MAX_LATENCY_NS, MAX_SAMPLES, LatencyEvidenceError, analyze,
)


def sample(sequence, enqueued, latency, depth=0):
    return {
        "sequence": sequence,
        "enqueued_ns": enqueued,
        "dequeued_ns": enqueued + latency,
        "depth": depth,
    }


def ordered_trace():
    return [sample(i, 1000 * (i + 1), 100 * (i + 1), i % 4) for i in range(10)]


class QueueLatencyTests(unittest.TestCase):
    def test_empty_trace_is_no_data_and_never_passes(self):
        for budget in (None, 1, MAX_LATENCY_NS):
            with self.subTest(budget=budget):
                report = analyze([], capacity=8, budget_ns=budget)
                self.assertEqual(report.status, "NO_DATA")
                self.assertEqual(report.sample_count, 0)
                self.assertEqual((report.min_ns, report.max_ns, report.mean_ns),
                                 (0, 0, 0.0))
                self.assertEqual((report.median_ns, report.p95_ns, report.p99_ns),
                                 (0, 0, 0))
                self.assertEqual((report.peak_depth, report.saturated_samples), (0, 0))

    def test_metrics_of_known_trace(self):
        report = analyze(ordered_trace(), capacity=8)
        self.assertEqual(report.status, "MEASURED")
        self.assertEqual(report.sample_count, 10)
        self.assertEqual((report.min_ns, report.max_ns), (100, 1000))
        self.assertEqual(report.mean_ns, 550.0)
        self.assertEqual((report.median_ns, report.p95_ns, report.p99_ns),
                         (500, 1000, 1000))
        self.assertEqual((report.peak_depth, report.saturated_samples), (3, 0))
        self.assertEqual(report.out_of_order_steps, 0)

    def test_out_of_order_timestamps_match_sorted_trace(self):
        ordered = ordered_trace()
        permutation = [5, 0, 7, 2, 9, 1, 4, 8, 3, 6]
        shuffled = [ordered[i] for i in permutation]
        expected = analyze(ordered, capacity=8)
        actual = analyze(shuffled, capacity=8)
        self.assertEqual(actual.out_of_order_steps, 4)
        self.assertEqual(replace(actual, out_of_order_steps=0), expected)

    def test_budget_classification_applies_only_to_nonempty_traces(self):
        trace = ordered_trace()
        self.assertEqual(analyze(trace, capacity=8, budget_ns=1000).status, "PASS")
        self.assertEqual(analyze(trace, capacity=8, budget_ns=999).status, "FAIL")
        self.assertEqual(analyze([], capacity=8, budget_ns=10**15).status, "NO_DATA")

    def test_saturation_is_reported(self):
        trace = [sample(i, i, 10, 8 if i == 2 else 1) for i in range(5)]
        report = analyze(trace, capacity=8)
        self.assertEqual(report.peak_depth, 8)
        self.assertEqual(report.saturated_samples, 1)

    def test_analyzer_does_not_mutate_caller_trace(self):
        trace = ordered_trace()
        original = deepcopy(trace)
        analyze(trace, capacity=8)
        self.assertEqual(trace, original)

    def test_oversized_trace_is_refused_before_analysis(self):
        trace = [sample(i, i, 1) for i in range(MAX_SAMPLES + 1)]
        with self.assertRaisesRegex(LatencyEvidenceError, "sample bound"):
            analyze(trace, capacity=8)

    def test_invalid_samples_are_refused(self):
        valid = sample(0, 100, 10)
        bad_traces = [
            [1],
            [{"sequence": 0, "enqueued_ns": 1, "dequeued_ns": 2}],
            [dict(valid, extra=1)],
            [dict(valid, sequence=True)],
            [dict(valid, enqueued_ns=-1)],
            [dict(valid, enqueued_ns=100.0)],
            [sample(0, 100, -1)],
            [sample(0, 100, MAX_LATENCY_NS + 1)],
            [sample(0, 100, 10, 9)],
            [valid, sample(0, 200, 10)],
            [dict(valid, sequence=10**14)],
        ]
        for trace in bad_traces:
            with self.subTest(trace=repr(trace)[:60]):
                with self.assertRaises(LatencyEvidenceError):
                    analyze(trace, capacity=8)

    def test_invalid_bounds_and_input_container_are_refused(self):
        for capacity in (0, -1, True, 8.0, MAX_SAMPLES + 1):
            with self.subTest(capacity=capacity):
                with self.assertRaises(LatencyEvidenceError):
                    analyze([], capacity=capacity)
        for budget in (0, -1, True, 1.0, MAX_LATENCY_NS + 1):
            with self.subTest(budget=budget):
                with self.assertRaises(LatencyEvidenceError):
                    analyze([], capacity=8, budget_ns=budget)
        for trace in (None, "trace", iter([]), {0: 1}):
            with self.subTest(trace=type(trace).__name__):
                with self.assertRaises(LatencyEvidenceError):
                    analyze(trace, capacity=8)

    def test_module_has_no_polling_service_or_io_dependencies(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/performance/queue_latency.py").read_text()
        for token in ("QTimer", "Thread(", "socket", "subprocess", "asyncio",
                      "time.sleep", "import os", "open(", "requests", "while True"):
            with self.subTest(token=token):
                self.assertNotIn(token, code)


if __name__ == "__main__":
    unittest.main()
