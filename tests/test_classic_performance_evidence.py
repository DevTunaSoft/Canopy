"""Offline tests for CI-host idle evidence classification.

All numbers below are synthetic test fixtures. No measurement is generated.
The real PR #151 CI artifact is cited only in the tool docstring.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.qa import classic_performance_evidence as evidence
from tools.qa import perf_evidence_gate as gate

SOURCE = "a" * 40
BINARY = "b" * 64
ROOT = Path(__file__).resolve().parents[1]


def synthetic_report():
    return {
        "schema": 1,
        "kind": "short-headless-baseline-not-mint-acceptance",
        "duration_seconds": 300.42,
        "cpu_percent_one_core": 0.004,
        "pss_kib_start": 58000,
        "pss_kib_end": 61000,
        "backend": "software",
    }


class ClassicPerformanceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.report = synthetic_report()

    def check(self, **kwargs):
        options = {"expected_source_sha": SOURCE,
                   "expected_binary_sha256": BINARY}
        options.update(kwargs)
        return evidence.validate(self.report, **options)

    def test_ci_host_report_is_labeled_not_mint_or_release(self):
        result = self.check()
        self.assertEqual(result["status"], "CI_HOST_EVIDENCE_ONLY")
        self.assertEqual(result["runner"], evidence.CI_HOST)
        self.assertFalse(result["linux_mint_acceptance"])
        self.assertFalse(result["release_approved"])
        self.assertFalse(result["visual_approval"])
        self.assertTrue(result["numeric_targets_met"])
        self.assertEqual(result["cpu_percent_one_core"], 0.004)
        self.assertEqual(result["pss_growth_kib"], 3000)
        self.assertEqual(result["source"],
                         "parsed local report only; no measurement generated")

    def test_reported_pr151_figures_parse_without_invention(self):
        self.report["duration_seconds"] = 300.0
        self.report["cpu_percent_one_core"] = 0.003
        self.report["pss_kib_start"] = 57372
        self.report["pss_kib_end"] = 60486
        result = self.check()
        self.assertEqual(result["cpu_percent_one_core"], 0.003)
        self.assertEqual(result["pss_kib_start"], 57372)
        self.assertEqual(result["pss_kib_end"], 60486)
        self.assertFalse(result["linux_mint_acceptance"])

    def test_short_or_unbounded_duration_rejected(self):
        for duration in (299.99, 5.0, 3600.01, -1):
            with self.subTest(duration=duration):
                self.report["duration_seconds"] = duration
                with self.assertRaisesRegex(gate.EvidenceError, "five-minute"):
                    self.check()
                self.report = synthetic_report()

    def test_incomplete_extra_or_wrong_schema_fields_rejected(self):
        for key in self.report:
            with self.subTest(missing=key):
                broken = copy.deepcopy(self.report)
                del broken[key]
                with self.assertRaises(gate.EvidenceError):
                    evidence.validate(
                        broken, expected_source_sha=SOURCE,
                        expected_binary_sha256=BINARY)
        for field, value in (("environment", "linuxmint"),
                             ("source_sha", SOURCE)):
            with self.subTest(extra=field):
                self.report[field] = value
                with self.assertRaises(gate.EvidenceError):
                    self.check()
                del self.report[field]
        for field, value in (("schema", 2), ("kind", "five-minute-idle-linux-qt")):
            with self.subTest(field=field):
                self.report[field] = value
                with self.assertRaises(gate.EvidenceError):
                    self.check()
                self.report = synthetic_report()

    def test_fabricated_or_nonfinite_values_rejected(self):
        for field, value in (
            ("duration_seconds", True),
            ("duration_seconds", float("nan")),
            ("cpu_percent_one_core", "0.003"),
            ("cpu_percent_one_core", -0.1),
            ("cpu_percent_one_core", float("inf")),
            ("pss_kib_start", 0),
            ("pss_kib_end", 10 ** 25),
            ("pss_kib_end", 1e4),
            ("backend", "fake-simulator"),
        ):
            with self.subTest(field=field, value=value):
                self.report[field] = value
                with self.assertRaises(gate.EvidenceError):
                    self.check()
                self.report = synthetic_report()

    def test_external_pins_required_and_mint_runner_refused(self):
        for source, binary in ((None, BINARY), ("short", BINARY),
                               (SOURCE, None), (SOURCE, "A" * 64)):
            with self.subTest(source=source, binary=binary):
                with self.assertRaises(gate.EvidenceError):
                    self.check(expected_source_sha=source,
                               expected_binary_sha256=binary)
        with self.assertRaisesRegex(gate.EvidenceError, "Mint"):
            self.check(runner="linuxmint")
        with self.assertRaises(gate.EvidenceError):
            self.check(runner="/tmp/arbitrary")

    def test_wrong_targets_still_label_ci_host_not_release(self):
        self.report["cpu_percent_one_core"] = 2.0
        result = self.check()
        self.assertFalse(result["numeric_targets_met"])
        self.assertEqual(result["status"], "CI_HOST_EVIDENCE_ONLY")
        self.assertFalse(result["release_approved"])

    def test_cli_parses_bounded_report_and_rejects_unsafe_input(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            path = folder / "qt-idle-300s.json"
            path.write_text(json.dumps(self.report), encoding="utf-8")
            cli = [sys.executable, str(ROOT / "tools" / "qa"
                                       / "classic_performance_evidence.py")]
            pin = ["--expected-source-sha", SOURCE,
                   "--expected-binary-sha256", BINARY]
            proc = subprocess.run(cli + [str(path)] + pin, cwd=ROOT,
                                  capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            body = json.loads(proc.stdout)
            self.assertEqual(body["status"], "CI_HOST_EVIDENCE_ONLY")
            self.assertFalse(body["linux_mint_acceptance"])

            alias = folder / "alias.json"
            alias.symlink_to(path)
            linked = subprocess.run(cli + [str(alias)] + pin, cwd=ROOT,
                                    capture_output=True, text=True,
                                    check=False)
            self.assertEqual(linked.returncode, 1)
            self.assertIn("CLASSIC_CI_EVIDENCE_FAIL", linked.stderr)

            no_pin = subprocess.run(cli + [str(path)], cwd=ROOT,
                                    capture_output=True, text=True,
                                    check=False)
            self.assertEqual(no_pin.returncode, 2)

    def test_tool_never_generates_or_runs_a_measurement(self):
        source = (ROOT / "tools" / "qa"
                  / "classic_performance_evidence.py").read_text(encoding="utf-8")
        for forbidden in ("Popen", "subprocess", "sleep", "random",
                          "time.time", "monotonic", "smaps", "/proc/"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
