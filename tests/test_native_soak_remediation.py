"""PR749 stability-sampler remediation regressions (unittest; no pytest needed).

Fixtures live in tests/fixtures/native_soak and are explicitly synthetic test
input. They are NOT presented as guest evidence; real read-only evidence lives
under scratch/pr749_incident/vm with SHA-256 provenance in the regenerated
report.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "native_soak"


def load_module(name, relative):
    path = REPO / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SAMPLER = load_module("native_soak_sampler_under_test", "tools/stability/native_soak_sampler.py")
REPORT = load_module("native_soak_report_under_test", "tools/stability/native_soak_report.py")


SYNTHETIC_TSV = """# schema=native-soak-sample/2
# label=TEST_FIXTURE
# start_utc=2026-11-28T06:53:00Z
# clk_tck=100
# guest=canopy-fixture
# kernel=7.0.0-test
# samples=2
# elapsed_s=200
# end_utc=2026-11-28T06:56:20Z
S 0 2026-11-28T06:53:00Z 100 canopy canopy-classic 1 0 0 100 100 0 0 NA 100 100 1 48 53
S 200 2026-11-28T06:56:20Z 100 canopy canopy-classic 1 5 0 100 100 0 0 NA 100 100 1 54 53
EVENT {"event":"unit_sample","t":0,"scope":"system","count":3,"units":["a.service","b.service"],"unit_cap":2,"truncated":true,"status":"OK"}
EVENT {"event":"journal_probe","t":200,"journal_system_errors":["2026-11-28T06:53:00+00:00 canopy-plasma6 systemd[1]: x"],"journal_system_errors_total":1,"coredumps":[]}
"""


class HostnameRegexRegression(unittest.TestCase):
    def test_hostname_cannot_inflate_error_total(self):
        text = (FIXTURES / "journal_err_hostname_fixture.txt").read_text(encoding="utf-8")
        matched, distinct = SAMPLER.matching_error_lines(text)
        self.assertEqual(len(matched), 3, matched)
        self.assertEqual(len(distinct), 3)
        for body in matched:
            self.assertNotIn("canopy-plasma6", body)

    def test_legacy_whole_line_match_is_the_defect(self):
        text = (FIXTURES / "journal_err_hostname_fixture.txt").read_text(encoding="utf-8")
        legacy = [ln for ln in text.splitlines() if SAMPLER.ERROR_PATTERN.search(ln)]
        self.assertEqual(len(legacy), 6)
        self.assertGreater(len(legacy), len(SAMPLER.matching_error_lines(text)[0]))

    def test_message_body_strips_timestamp_hostname_and_unit(self):
        body = SAMPLER.journal_message_body(
            "2026-11-28T06:53:31+00:00 canopy-plasma6 kernel: watchdog: BUG: soft lockup - CPU#0")
        self.assertEqual(body, "watchdog: BUG: soft lockup - CPU#0")


class BoundedUnitNames(unittest.TestCase):
    def test_unit_sample_event_caps_and_flags_truncation(self):
        names = ["u%02d.service" % i for i in range(10)]
        event = SAMPLER.unit_sample_event("system", 0, 10, names, cap=4)
        self.assertEqual(event["units"], names[:4])
        self.assertTrue(event["truncated"])
        self.assertEqual(event["unit_cap"], 4)
        unavailable = SAMPLER.unit_sample_event("system", 0, "NA", None, cap=4)
        self.assertEqual(unavailable["status"], "PROBE_UNAVAILABLE")
        self.assertFalse(unavailable["truncated"])


class GapClassifier(unittest.TestCase):
    gap = {"from_s": 1654, "to_s": 1833, "delta_s": 179}
    start = "2026-11-28T06:25:56Z"

    def test_readonly_evidence_proves_guest_stall(self):
        result = REPORT.classify_gaps([self.gap], self.start,
                                      str(FIXTURES / "gap_evidence"))[0]
        self.assertEqual(result["classification"], "GUEST_STALL_PROVEN")
        self.assertTrue(result["no_rows_synthesised"])
        self.assertTrue(result["guest_soft_lockup_lines"])
        self.assertTrue(result["vbox_stall_lines"])

    def test_missing_evidence_is_not_run_not_guess(self):
        with tempfile.TemporaryDirectory() as empty:
            result = REPORT.classify_gaps([self.gap], self.start, empty)[0]
        self.assertEqual(result["classification"], "NOT_RUN_NO_READONLY_EVIDENCE")
        self.assertEqual(result["vbox_stall_lines"], [])


class ReportIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name) / "synthetic.tsv"
        self.out = Path(self.tmp.name) / "report.json"
        self.raw.write_text(SYNTHETIC_TSV, encoding="utf-8")
        self.report = REPORT.build_report(str(self.raw), {
            "label": "TEST_FIXTURE", "start_utc": "2026-11-28T06:53:00Z",
            "end_utc": "2026-11-28T06:56:20Z", "elapsed_s": "200",
            "samples": "2", "clk_tck": "100", "guest": "canopy-fixture",
        }, REPORT.load_raw(str(self.raw))[1], REPORT.load_raw(str(self.raw))[2],
            str(FIXTURES / "gap_evidence"), "NOT_RUN fixture reason")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sample_count_is_int_and_guest_key_is_correct(self):
        self.assertEqual(self.report["sample_count"], 2)
        self.assertIsInstance(self.report["sample_count"], int)
        self.assertEqual(self.report["guest"], "canopy-fixture")

    def test_cpu_buckets_carry_coverage_caveats(self):
        self.assertTrue(self.report["canopy_cpu_5min_windows"])
        for win in self.report["canopy_cpu_5min_windows"]:
            self.assertIn("coverage_pct", win)
            self.assertIn("observed_span_s", win)
            self.assertIn("caveat", win)
        self.assertTrue(self.report["cpu_bucket_caveats"])

    def test_unit_membership_is_bounded_and_reported(self):
        system = self.report["unit_membership"]["system"]
        self.assertEqual(system["status"], "OK")
        self.assertEqual(system["distinct_units_observed"], 2)
        self.assertTrue(system["truncated_any"])
        self.assertEqual(self.report["unit_membership"]["user"]["status"], "NOT_RUN")

    def test_verdict_stays_warn_and_never_promotes_readiness(self):
        self.assertTrue(self.report["verdict"].startswith("SOAK_WARN_"))
        self.assertNotIn("READY", self.report["verdict"])
        self.assertNotIn("STABLE", self.report["verdict"])
        self.assertIn("SOAK_RERUN_EXCLUSIVE_QUIESCED_GUEST", self.report["not_run"])
        self.assertEqual(self.report["soak_rerun"]["status"], "NOT_RUN")

    def test_legacy_hostname_inflation_is_labelled_unreliable(self):
        self.assertTrue(self.report["journal_probe_quality"]["legacy_hostname_inflation"])
        self.assertIn("JOURNAL_ERROR_COUNT_UNRELIABLE_LEGACY_HOSTNAME_MATCH",
                      self.report["warnings"])

    def test_gap_is_proven_not_inferred_and_no_rows_added(self):
        gap = self.report["sample_gap_classification"][0]
        self.assertEqual(gap["classification"], "GUEST_STALL_PROVEN")
        self.assertTrue(gap["no_rows_synthesised"])
        self.assertEqual(len(self.report["sample_gaps_gt_120s"]), 1)


class RawBytesUnchanged(unittest.TestCase):
    def test_committed_raw_manifest_still_verifies(self):
        raw_dir = REPO / "scratch" / "native_stability" / "raw"
        manifest = raw_dir / "SHA256SUMS.txt"
        if not manifest.is_file():
            self.skipTest("no raw manifest in this checkout")
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, name = line.split(maxsplit=1)
            name = name.lstrip("*")
            actual = hashlib.sha256((raw_dir / name).read_bytes()).hexdigest()
            self.assertEqual(actual, digest, name)


if __name__ == "__main__":
    unittest.main()
