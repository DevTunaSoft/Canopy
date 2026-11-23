"""Nested/malformed evidence JSON must fail closed in the offline perf gate."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools.qa import perf_evidence_gate as gate


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


class NestedJsonEvidenceTests(unittest.TestCase):
    def test_decoder_recursion_error_translates_to_evidence_error(self):
        """A decoder recursion overflow must not escape the reader boundary."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "metrics.json"
            path.write_bytes(json.dumps(short_case()).encode("utf-8"))
            with mock.patch.object(gate.json, "loads",
                                   side_effect=RecursionError("Stack overflow")):
                with self.assertRaises(gate.EvidenceError):
                    gate._real_file(path)

    def test_cli_deeply_nested_report_has_no_traceback(self):
        """A bounded-size hostile report keeps the CLI's fail-closed marker."""
        depth = 15_000
        payload = b"[" * depth + b"]" * depth
        self.assertLessEqual(len(payload), gate.MAX_REPORT_BYTES)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "metrics.json"
            path.write_bytes(payload)
            proc = subprocess.run(
                [sys.executable, str(Path(gate.__file__).resolve()), str(path)],
                capture_output=True, text=True,
            )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("QT_PERF_GATE_FAIL:", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_parsable_nested_array_still_hits_schema_boundary(self):
        depth = 600
        payload = b"[" * depth + b"]" * depth
        self.assertLessEqual(len(payload), gate.MAX_REPORT_BYTES)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "metrics.json"
            path.write_bytes(payload)
            with self.assertRaisesRegex(gate.EvidenceError, "object"):
                gate._real_file(path)

    def test_non_finite_json_constant_still_translated(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "metrics.json"
            path.write_bytes(b'{"schema": NaN}')
            with self.assertRaisesRegex(gate.EvidenceError, "invalid report JSON"):
                gate._real_file(path)

    def test_valid_short_report_still_read_unchanged(self):
        case = short_case()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "metrics.json"
            path.write_bytes(json.dumps(case).encode("utf-8"))
            self.assertEqual(gate._real_file(path), case)


if __name__ == "__main__":
    unittest.main()
