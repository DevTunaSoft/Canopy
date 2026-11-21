"""No invented Qt idle performance; synthetic numbers test the validator only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.qa import perf_evidence_gate as gate

SOURCE = "f" * 40
BINARY = "e" * 64


def long_case():
    return {
        "schema": 2, "kind": "five-minute-idle-linux-qt",
        "environment": "linuxmint",
        "measurement_method": "proc-smaps-rollup-and-stat",
        "source_sha": SOURCE, "binary_sha256": BINARY,
        "backend": "software", "duration_seconds": 305,
        "sample_count": 62, "cpu_ticks_start": 12340,
        "cpu_ticks_end": 12500, "clock_ticks_per_second": 100,
        "pss_kib_start": 55000, "pss_kib_end": 62000,
        "pss_kib_peak": 65000,
    }


class PerformanceEvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.case = long_case()

    def check(self, sha=SOURCE, binary=BINARY):
        return gate.assess(self.case, expected_source_sha=sha,
                           expected_binary_sha256=binary)

    def test_five_minute_numeric_targets_are_not_release_claims(self):
        result = self.check()
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["release_approved"])
        self.assertFalse(result["linux_mint_guest_proven"])
        self.assertEqual(result["cpu_percent_one_core_calculated"], 0.5246)
        self.assertEqual(result["memory_target_kib"], 204800)

    def test_real_old_five_second_baseline_never_becomes_release_pass(self):
        sample = {
            "schema": 1,
            "kind": "short-headless-baseline-not-mint-acceptance",
            "duration_seconds": 5.0,
            "cpu_percent_one_core": 0.4,
            "pss_kib_start": 57181,
            "pss_kib_end": 59667,
            "backend": "software",
        }
        result = gate.assess(sample)
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(result["release_approved"])

    def test_short_or_sparse_real_report_is_not_sufficient(self):
        for key, value in (("duration_seconds", 299.99), ("sample_count", 59)):
            with self.subTest(field=key):
                self.case[key] = value
                self.assertEqual(self.check()["status"], "INSUFFICIENT_EVIDENCE")
                self.case = long_case()

    def test_cpu_and_memory_targets_are_independent(self):
        self.case["pss_kib_peak"] = 204801
        self.assertEqual(self.check()["status"], "FAIL")
        self.case = long_case()
        self.case["cpu_ticks_end"] = 12700
        self.assertEqual(self.check()["status"], "FAIL")

    def test_raw_tick_recalculation_defeats_fake_passing_percent(self):
        self.case["cpu_percent_one_core"] = 0.0
        with self.assertRaisesRegex(gate.EvidenceError, "schema"):
            self.check()

    def test_reject_mismatched_source_or_binary_and_self_reported_method(self):
        for field, value in (("measurement_method", "fake-simulator"),
                             ("environment", "ubuntu"),
                             ("kind", "short-headless-baseline-not-mint-acceptance")):
            with self.subTest(field=field):
                self.case[field] = value
                with self.assertRaises(gate.EvidenceError):
                    self.check()
                self.case = long_case()
        with self.assertRaisesRegex(gate.EvidenceError, "provenance"):
            self.check("a" * 40)
        with self.assertRaisesRegex(gate.EvidenceError, "provenance"):
            self.check(SOURCE, "b" * 64)
        with self.assertRaisesRegex(gate.EvidenceError, "external"):
            self.check("invalid", BINARY)

    def test_reject_nan_bool_negative_and_unbounded_values(self):
        for field, value in (
            ("duration_seconds", float("nan")), ("duration_seconds", float("inf")),
            ("sample_count", True), ("cpu_ticks_end", -1),
            ("clock_ticks_per_second", 0), ("pss_kib_peak", 10**25),
            ("pss_kib_end", 1e4), ("schema", True),
        ):
            with self.subTest(field=field):
                self.case[field] = value
                with self.assertRaises(gate.EvidenceError):
                    self.check()
                self.case = long_case()

    def test_reject_impossible_counter_sequence_or_memory_peak(self):
        for field, value in (("cpu_ticks_end", 12339),
                             ("pss_kib_peak", 50000),
                             ("clock_ticks_per_second", 20000),
                             ("sample_count", 200000)):
            with self.subTest(field=field):
                self.case[field] = value
                with self.assertRaises(gate.EvidenceError):
                    self.check()
                self.case = long_case()

    def test_bounded_report_reader_and_cli_status_codes(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            path = folder / "metrics.json"
            path.write_text(json.dumps(self.case), encoding="utf-8")
            self.assertEqual(gate._real_file(path), self.case)
            self.assertEqual(gate.main([str(path), "--expected-source-sha", SOURCE,
                                        "--expected-binary-sha256", BINARY]), 0)
            path.write_bytes(b"x" * (gate.MAX_REPORT_BYTES + 1))
            with self.assertRaisesRegex(gate.EvidenceError, "oversized"):
                gate._real_file(path)

    def test_reject_symlinked_or_non_json_report(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            actual = folder / "evidence.json"
            actual.write_text(json.dumps(self.case), encoding="utf-8")
            alias = folder / "alias.json"
            alias.symlink_to(actual)
            with self.assertRaisesRegex(gate.EvidenceError, "symlink"):
                gate._real_file(alias)
            actual.write_text('{"schema": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(gate.EvidenceError, "invalid report"):
                gate._real_file(actual)


if __name__ == "__main__":
    unittest.main()
