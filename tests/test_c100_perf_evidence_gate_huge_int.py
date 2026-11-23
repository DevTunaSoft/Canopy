"""Huge finite JSON integers must fail closed as EvidenceError in the perf gate."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.qa import perf_evidence_gate as gate

SOURCE = "f" * 40
BINARY = "e" * 64


def short_case():
    return {
        "schema": 1,
        "kind": "short-headless-baseline-not-mint-acceptance",
        "duration_seconds": 5.0,
        "cpu_percent_one_core": 0.5,
        "pss_kib_start": 60000,
        "pss_kib_end": 61000,
        "backend": "software",
    }


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


class HugeIntegerEvidenceTests(unittest.TestCase):
    def test_short_baseline_huge_duration_fails_closed(self):
        case = short_case()
        case["duration_seconds"] = 10 ** 400
        with self.assertRaises(gate.EvidenceError):
            gate.assess(case)

    def test_short_baseline_huge_cpu_percent_fails_closed(self):
        case = short_case()
        case["cpu_percent_one_core"] = 10 ** 400
        with self.assertRaises(gate.EvidenceError):
            gate.assess(case)

    def test_long_idle_huge_duration_fails_closed(self):
        case = long_case()
        case["duration_seconds"] = 10 ** 400
        with self.assertRaises(gate.EvidenceError):
            gate.assess(case, expected_source_sha=SOURCE,
                        expected_binary_sha256=BINARY)

    def test_real_json_cli_fails_closed_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "metrics.json"
            case = short_case()
            case["duration_seconds"] = 10 ** 400
            path.write_text(json.dumps(case), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(Path(gate.__file__).resolve()), str(path)],
                capture_output=True, text=True,
            )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("QT_PERF_GATE_FAIL:", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_merely_large_integer_still_respects_numeric_bounds(self):
        case = short_case()
        case["duration_seconds"] = 10 ** 30
        with self.assertRaises(gate.EvidenceError):
            gate.assess(case)

    def test_valid_short_and_long_baselines_unchanged(self):
        self.assertEqual(gate.assess(short_case())["status"],
                         "INSUFFICIENT_EVIDENCE")
        self.assertEqual(
            gate.assess(long_case(), expected_source_sha=SOURCE,
                        expected_binary_sha256=BINARY)["status"],
            "PASS",
        )


if __name__ == "__main__":
    unittest.main()
