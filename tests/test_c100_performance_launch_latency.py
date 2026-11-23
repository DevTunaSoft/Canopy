"""Offline unit tests for cold/warm launch latency summaries.

Synthetic timestamps only: no Qt process is launched, no real Mint host is
tested and no wall clock is read. These tests validate the summarizer and
its provenance/exclusion logic, not any desktop startup time.
"""
from copy import deepcopy
import unittest

from canopy_features.performance import launch_latency as ll

SOURCE = "measure_qt:CANOPY_CLASSIC_WINDOW_READY"
SHA = "a" * 64


def sample(kind, start, ready, **overrides):
    fields = dict(kind=kind, start_ns=start, ready_ns=ready, source=SOURCE)
    fields.update(overrides)
    return ll.LaunchSample(**fields)


class LaunchLatencyTests(unittest.TestCase):
    def test_cold_warm_stats_and_ms_conversion(self):
        samples = [
            sample("cold", 0, 2_000_000),
            sample("cold", 10_000_000, 13_000_000),
            sample("warm", 0, 500_000),
            sample("warm", 1_000_000, 2_000_000),
            sample("warm", 5_000_000, 6_500_000),
        ]
        result = ll.summarize(samples)
        self.assertEqual(result["schema"], 1)
        self.assertEqual(result["cold"], {
            "count": 2, "min_ms": 2.0, "max_ms": 3.0,
            "mean_ms": 2.5, "median_ms": 2.5,
        })
        self.assertEqual(result["warm"], {
            "count": 3, "min_ms": 0.5, "max_ms": 1.5,
            "mean_ms": 1.0, "median_ms": 1.0,
        })
        self.assertEqual(result["provenance"]["included_count"], 5)
        self.assertEqual(result["provenance"]["excluded_count"], 0)

    def test_provenance_records_sources_clocks_and_sha(self):
        result = ll.summarize([
            sample("cold", 0, 1_000_000, source="zeta", source_sha256=SHA),
            sample("warm", 0, 1_000_000, source="alpha", source_sha256=SHA),
            sample("warm", 0, 1_000_000, source="alpha"),
        ])
        prov = result["provenance"]
        self.assertEqual(prov["sources"], ["alpha", "zeta"])
        self.assertEqual(prov["clocks"], ["monotonic"])
        self.assertEqual(prov["source_sha256"], [SHA])
        self.assertNotIn("mixed_clocks", prov["warnings"])
        self.assertNotIn("wall_clock_timestamps", prov["warnings"])

    def test_backward_clock_jump_is_excluded_not_aggregated(self):
        result = ll.summarize([
            sample("cold", 10_000_000, 9_000_000),
            sample("cold", 0, 2_000_000),
        ])
        self.assertEqual(result["cold"]["count"], 1)
        self.assertEqual(result["cold"]["min_ms"], 2.0)
        excluded = result["provenance"]["excluded"]
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["reason"], "backward_clock_jump")
        self.assertEqual(excluded[0]["source"], SOURCE)
        self.assertEqual(result["provenance"]["excluded_count"], 1)

    def test_forward_clock_jump_is_excluded(self):
        jumped = sample("warm", 0, ll.MAX_LATENCY_NS + 1)
        result = ll.summarize([jumped])
        self.assertEqual(result["warm"]["count"], 0)
        self.assertEqual(result["provenance"]["excluded"][0]["reason"],
                         "forward_clock_jump")

    def test_missing_timestamps_are_excluded_with_reason(self):
        for field, value in (("start_ns", None), ("ready_ns", None)):
            with self.subTest(missing=field):
                fields = dict(start_ns=0, ready_ns=1_000_000)
                fields[field] = value
                missing = ll.LaunchSample(kind="cold", source=SOURCE, **fields)
                result = ll.summarize([missing])
                self.assertEqual(result["cold"]["count"], 0)
                excluded = result["provenance"]["excluded"]
                self.assertEqual(len(excluded), 1)
                self.assertEqual(excluded[0]["reason"], "missing_timestamp")

    def test_invalid_timestamps_are_excluded(self):
        cases = [
            sample("cold", -1, 1_000_000),
            sample("cold", 0, -1),
            sample("cold", 0, True),
            sample("cold", 0, 1.5),
        ]
        result = ll.summarize(cases)
        self.assertEqual(result["cold"]["count"], 0)
        self.assertEqual([e["reason"] for e in result["provenance"]["excluded"]],
                         ["invalid_timestamp"] * len(cases))

    def test_empty_and_all_excluded_are_null_and_deterministic(self):
        empty = ll.summarize([])
        for kind in ("cold", "warm"):
            self.assertEqual(empty[kind], {
                "count": 0, "min_ms": None, "max_ms": None,
                "mean_ms": None, "median_ms": None,
            })
        self.assertEqual(empty["provenance"]["warnings"],
                         ["no_cold_samples", "no_warm_samples"])
        all_bad = [sample("cold", 5, 4), sample("warm", None, 1)]
        self.assertEqual(ll.summarize(all_bad), ll.summarize(all_bad))
        self.assertEqual(ll.summarize([]), empty)

    def test_mixed_clocks_and_wall_clock_warning(self):
        result = ll.summarize([
            sample("cold", 0, 1_000_000, clock="monotonic"),
            sample("warm", 0, 1_000_000, clock="realtime"),
        ])
        prov = result["provenance"]
        self.assertEqual(prov["clocks"], ["monotonic", "realtime"])
        self.assertIn("mixed_clocks", prov["warnings"])
        self.assertIn("wall_clock_timestamps", prov["warnings"])

    def test_structural_contract_violations_raise(self):
        with self.assertRaisesRegex(ll.LatencyError, "list or tuple"):
            ll.summarize((s for s in []))
        with self.assertRaisesRegex(ll.LatencyError, "bound"):
            ll.summarize([sample("cold", 0, 1)] * (ll.MAX_SAMPLES + 1))
        with self.assertRaisesRegex(ll.LatencyError, "LaunchSample"):
            ll.summarize([{"kind": "cold"}])
        with self.assertRaisesRegex(ll.LatencyError, "kind"):
            ll.summarize([sample("hot", 0, 1)])
        with self.assertRaisesRegex(ll.LatencyError, "clock"):
            ll.summarize([sample("cold", 0, 1, clock="guess")])
        with self.assertRaisesRegex(ll.LatencyError, "source"):
            ll.summarize([sample("cold", 0, 1, source="")])
        with self.assertRaisesRegex(ll.LatencyError, "source_sha256"):
            ll.summarize([sample("cold", 0, 1, source_sha256="xyz")])

    def test_inputs_not_mutated_and_result_independent(self):
        samples = [sample("cold", 0, 2_000_000)]
        before = deepcopy(samples)
        result = ll.summarize(samples)
        self.assertEqual(samples, before)
        result["cold"]["count"] = 999
        result["provenance"]["excluded"].append({"tampered": True})
        self.assertEqual(ll.summarize(samples)["cold"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
