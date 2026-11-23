"""Contract tests for the bounded offline performance snapshot compare gate."""
import ast
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from unittest import mock

from canopy_features.performance.frame_pacing import parse_frame_times
from canopy_features.performance.launch_latency import LaunchSample, summarize
from canopy_features.performance.memory_delta import MemorySample, report_growth
from canopy_features.performance.performance_snapshot import compose_snapshot
from tools.qa import perf_snapshot_compare_gate as gate


def artifact(frame_times=(16.7, 16.8, 33.4),
             mem_values=(100_000, 102_000, 101_000),
             cold_ms=(20.0,), warm_ms=(10.0,), pss_kib=150_000,
             include_frame=True, include_memory=True, include_launch=True):
    """Build a real snapshot artifact through the merged producer."""
    frame = None
    if include_frame:
        frame = parse_frame_times(list(frame_times), refresh_hz=60)
    memory = None
    if include_memory:
        memory = report_growth(
            [MemorySample(i, v) for i, v in enumerate(mem_values)])
    launch = None
    if include_launch:
        samples = []
        for ms in cold_ms:
            samples.append(
                LaunchSample("cold", 0, int(ms * 1_000_000), "measure_qt:READY"))
        for ms in warm_ms:
            samples.append(
                LaunchSample("warm", 0, int(ms * 1_000_000), "measure_qt:READY"))
        launch = summarize(samples)
    return compose_snapshot(
        frame_pacing=frame, memory_growth=memory, launch_latency=launch,
        pss_kib=pss_kib if pss_kib is not None else None,
    ).as_dict()


def comparison(base=None, cand=None):
    return {
        "schema": gate.SCHEMA,
        "baseline": base if base is not None else artifact(),
        "candidate": cand if cand is not None else artifact(),
    }


def run_compare(payload):
    """validate -> evaluate -> serialize through the public path."""
    return gate.evaluate_compare(payload).as_dict()


class RealArtifactCompositionTests(unittest.TestCase):
    def test_compare_two_real_artifacts_is_valid(self):
        report = run_compare(comparison())
        self.assertEqual(report["status"], "VALID")
        self.assertEqual(report["schema"], gate.SCHEMA)
        self.assertEqual(report["baseline_evidence_count"], 4)
        self.assertEqual(report["candidate_evidence_count"], 4)

    def test_directions_are_fixed_tokens_over_the_fixed_allowlist(self):
        report = run_compare(comparison())
        self.assertEqual(set(report["directions"]),
                         {name for name, _ in gate.METRICS})
        for token in report["directions"].values():
            self.assertIn(token, gate.DIRECTIONS)

    def test_higher_and_lower_directions(self):
        base = artifact(frame_times=(16.0, 17.0, 18.0), pss_kib=150_000)
        cand = artifact(frame_times=(30.0, 31.0, 32.0), pss_kib=100_000)
        report = run_compare(comparison(base, cand))["directions"]
        self.assertEqual(report["frame_mean_ms"], "higher")
        self.assertEqual(report["frame_p95_ms"], "higher")
        self.assertEqual(report["pss_kib"], "lower")
        self.assertEqual(report["memory_peak_kib"], "equal")

    def test_identical_artifacts_are_equal(self):
        snap = artifact()
        report = run_compare(comparison(snap, snap))["directions"]
        self.assertEqual(set(report.values()), {"equal"})

    def test_absent_section_is_not_available(self):
        base = artifact(include_frame=True)
        cand = artifact(include_frame=False)
        report = run_compare(comparison(base, cand))["directions"]
        for name in ("frame_mean_ms", "frame_p95_ms", "frame_p99_ms",
                     "frame_dropped_rate"):
            self.assertEqual(report[name], "not_available")
        self.assertEqual(report["pss_kib"], "equal")

    def test_negative_claims_are_hardcoded(self):
        report = run_compare(comparison())
        for key in ("release_approved", "linux_mint_acceptance_proven",
                    "real_hardware_measured", "owner_visual_approval",
                    "measurement_performed"):
            self.assertIs(report[key], False)

    def test_report_is_frozen(self):
        rec = gate.evaluate_compare(comparison())
        with self.assertRaises(FrozenInstanceError):
            rec.schema = 99

    def test_as_dict_returns_fresh_container(self):
        rec = gate.evaluate_compare(comparison())
        first = rec.as_dict()
        first["directions"]["pss_kib"] = "higher"
        self.assertEqual(rec.as_dict()["directions"]["pss_kib"], "equal")

    def test_deterministic_bytes(self):
        payload = comparison()
        a = json.dumps(run_compare(payload), sort_keys=True)
        b = json.dumps(run_compare(payload), sort_keys=True)
        self.assertEqual(a, b)

    def test_forged_record_cannot_emit_approval(self):
        forged = gate.CompareReport(
            baseline_evidence_count=4, candidate_evidence_count=4,
            directions=("higher",) * len(gate.METRICS))
        report = forged.as_dict()
        self.assertIs(report["release_approved"], False)
        self.assertEqual(report["directions"]["pss_kib"], "higher")

    def test_forged_bad_directions_fail_closed(self):
        forged = gate.CompareReport(4, 4, ("bogus",) * len(gate.METRICS))
        with self.assertRaises(gate.CompareError):
            forged.as_dict()
        short = gate.CompareReport(4, 4, ("equal",))
        with self.assertRaises(gate.CompareError):
            short.as_dict()


class InputValidationTests(unittest.TestCase):
    def test_bad_wrapper_key_set(self):
        for bad in ({}, {"schema": 1, "baseline": artifact()},
                    {"schema": 1, "baseline": artifact(),
                     "candidate": artifact(), "extra": 1}):
            with self.subTest(bad=sorted(map(str, bad))):
                with self.assertRaises(gate.CompareError):
                    gate.evaluate_compare(bad)

    def test_wrong_schema_fails_closed(self):
        for bad in ("1", True, 2, 1.0, None):
            payload = comparison()
            payload["schema"] = bad
            with self.subTest(bad=bad), self.assertRaises(gate.CompareError):
                gate.evaluate_compare(payload)

    def test_non_mapping_members_fail_closed(self):
        for side in ("baseline", "candidate"):
            for bad in ([], 7, "x", True, None):
                payload = comparison()
                payload[side] = bad
                with self.subTest(side=side, bad=bad):
                    with self.assertRaises(gate.CompareError):
                        gate.evaluate_compare(payload)

    def test_forged_claim_member_rejected_with_fixed_token(self):
        for side, token in (("baseline", "baseline"), ("candidate", "candidate")):
            payload = comparison()
            payload[side]["measurement_performed"] = True
            with self.subTest(side=side):
                with self.assertRaises(gate.CompareError) as ctx:
                    gate.evaluate_compare(payload)
                self.assertIn("comparison " + token + " artifact rejected",
                              str(ctx.exception))

    def test_error_does_not_echo_caller_value(self):
        sentinel = "SENTINEL_DO_NOT_ECHO_42"
        payload = comparison()
        payload["candidate"]["frame_pacing"]["backend"] = ["x", sentinel]
        with self.assertRaises(gate.CompareError) as ctx:
            gate.evaluate_compare(payload)
        self.assertNotIn(sentinel, str(ctx.exception))

    def test_compare_json_wrong_types(self):
        for bad in (None, 7, ["x"], {"x": 1}):
            with self.subTest(bad=bad), self.assertRaises(gate.CompareError):
                gate.compare_json(bad)

    def test_compare_json_oversized_and_empty(self):
        with self.assertRaises(gate.CompareError):
            gate.compare_json("")
        with self.assertRaises(gate.CompareError):
            gate.compare_json("x" * (gate.MAX_COMPARE_BYTES + 1))

    def test_compare_json_accepts_bytes_and_str(self):
        text = json.dumps(comparison())
        self.assertIsInstance(gate.compare_json(text), gate.CompareReport)
        self.assertIsInstance(
            gate.compare_json(text.encode("utf-8")), gate.CompareReport)

    def test_compare_json_rejects_nonfinite_constant(self):
        text = json.dumps(comparison()).replace(
            '"schema": 1', '"schema": NaN', 1)
        with self.assertRaises(gate.CompareError):
            gate.compare_json(text)

    def test_compare_json_rejects_deep_nesting(self):
        text = "[" * 4000 + "]" * 4000
        with self.assertRaises(gate.CompareError):
            gate.compare_json(text)

    def test_direct_record_wrong_count_fails_closed(self):
        for count in (-1, 99, True, "4"):
            forged = gate.CompareReport(count, 4, ("equal",) * len(gate.METRICS))
            with self.subTest(count=count), self.assertRaises(gate.CompareError):
                forged.as_dict()


class FileBoundaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, payload, name="comparison.json"):
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_file(self):
        path = self._write(comparison())
        self.assertIsInstance(gate.compare_file(path), gate.CompareReport)

    def test_relative_path_rejected(self):
        with self.assertRaises(gate.CompareError):
            gate.compare_file(Path("relative.json"))

    def test_missing_file_rejected(self):
        with self.assertRaises(gate.CompareError):
            gate.compare_file(self.root / "nope.json")

    def test_directory_rejected(self):
        with self.assertRaises(gate.CompareError):
            gate.compare_file(self.root)

    def test_symlink_final_rejected(self):
        target = self._write(comparison(), "target.json")
        link = self.root / "link.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this host")
        with self.assertRaises(gate.CompareError):
            gate.compare_file(link)

    def test_oversized_file_rejected(self):
        path = self.root / "big.json"
        path.write_text("x" * (gate.MAX_COMPARE_BYTES + 1), encoding="utf-8")
        with self.assertRaises(gate.CompareError):
            gate.compare_file(path)

    def test_posix_fdopen_failure_translated(self):
        # On POSIX os.open() accepts a directory; the failure can surface at
        # fdopen()/read(). Reproduce that ordering on every host.
        with mock.patch.object(gate.os, "open", return_value=999), \
                mock.patch.object(gate.os, "fdopen",
                                  side_effect=IsADirectoryError("is a dir")):
            with self.assertRaises(gate.CompareError) as ctx:
                gate.compare_file(self.root / "anything.json")
        self.assertNotIn("is a dir", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, IsADirectoryError)

    def test_main_success(self):
        path = self._write(comparison())
        out = io.StringIO()
        with redirect_stdout(out):
            code = gate.main([str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "VALID")

    def test_main_failure_has_marker_and_no_echo(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = gate.main([str(self.root / "missing.json")])
        self.assertEqual(code, 1)
        self.assertIn("QT_PERF_COMPARE_FAIL:", err.getvalue())


class PurityTests(unittest.TestCase):
    def test_no_forbidden_imports_or_exec(self):
        source = (Path(gate.__file__).resolve()).read_text(encoding="utf-8")
        tree = ast.parse(source)
        allowed = {"argparse", "dataclasses", "json", "math", "os",
                   "pathlib", "stat", "sys", "tools"}
        forbidden = {"time", "random", "subprocess", "socket", "threading",
                     "datetime", "multiprocessing", "ctypes"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    self.assertNotIn(top, forbidden)
                    self.assertIn(top, allowed)
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                self.assertNotIn(top, forbidden)
                self.assertIn(top, allowed)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, {"system", "popen", "Popen"})


if __name__ == "__main__":
    unittest.main()
