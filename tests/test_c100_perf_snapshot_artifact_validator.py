"""Regression tests for the offline performance snapshot artifact validator.

Run: python -m unittest tests.test_c100_perf_snapshot_artifact_validator -v
"""
import ast
import json
from pathlib import Path
import tempfile
import unittest

from tools.qa import perf_snapshot_artifact_validator as validator


def _frame():
    return {
        "backend": "default",
        "backend_known": True,
        "refresh_hz": 60,
        "frame_budget_ms": 16.6667,
        "samples_total": 100,
        "samples_valid": 98,
        "samples_dropped": 2,
        "dropped_frames": 5,
        "dropped_frame_rate": 0.05,
        "min_ms": 8.0,
        "max_ms": 25.0,
        "mean_ms": 16.0,
        "p50_ms": 15.0,
        "p95_ms": 22.0,
        "p99_ms": 24.0,
        "measurement_source": "caller-supplied-frame-times-offline-parse",
        "real_gpu_measurement": False,
    }


def _memory():
    return {
        "start_kib": 100_000,
        "end_kib": 110_000,
        "delta_kib": 10_000,
        "interactions": 5,
        "sample_count": 20,
        "peak_kib": 115_000,
        "min_kib": 99_000,
        "delta_percent": 10.0,
        "mean_growth_per_interaction_kib": 2000.0,
        "status": "ok",
    }


def _stat():
    return {
        "count": 10,
        "min_ms": 100.0,
        "max_ms": 200.0,
        "mean_ms": 150.0,
        "median_ms": 148.0,
    }


def _launch():
    return {
        "schema": 1,
        "cold": _stat(),
        "warm": _stat(),
        "provenance": {
            "sample_count": 10,
            "included_count": 9,
            "excluded_count": 1,
            "clocks": ["monotonic"],
            "sources": ["offline-parse"],
            "source_sha256": ["a" * 64],
            "warnings": [],
            "excluded": [{
                "kind": "outlier", "reason": "slow", "source": "offline",
                "clock": "monotonic",
            }],
        },
    }


def _artifact():
    return {
        "schema": 1,
        "evidence_kinds": list(validator.EVIDENCE_KINDS),
        "evidence_count": 4,
        "frame_pacing": _frame(),
        "memory_growth": _memory(),
        "launch_latency": _launch(),
        "pss_kib": 150_000,
        "measurement_performed": False,
        "real_hardware_measured": False,
        "linux_mint_acceptance": validator.NOT_ESTABLISHED,
        "owner_visual_approval": validator.NOT_ESTABLISHED,
    }


def _empty_artifact():
    artifact = _artifact()
    for key in ("frame_pacing", "memory_growth", "launch_latency"):
        artifact[key] = None
    artifact["pss_kib"] = None
    artifact["evidence_count"] = 0
    return artifact


class ValidArtifactTests(unittest.TestCase):
    def test_full_artifact_valid(self):
        report = validator.validate(_artifact())
        self.assertEqual(report["status"], "VALID")
        self.assertEqual(report["evidence_count"], 4)

    def test_all_absent_evidence_valid(self):
        report = validator.validate(_empty_artifact())
        self.assertEqual(report["evidence_count"], 0)

    def test_report_has_fixed_negative_claims(self):
        report = validator.validate(_artifact())
        for key in ("release_approved", "linux_mint_acceptance_proven",
                    "real_hardware_measured", "owner_visual_approval",
                    "measurement_performed"):
            self.assertIs(report[key], False)

    def test_negative_int_delta_accepted(self):
        # memory_delta reports released memory as a bounded negative delta.
        artifact = _artifact()
        artifact["memory_growth"]["delta_kib"] = -5_000
        self.assertEqual(validator.validate(artifact)["status"], "VALID")

    def test_integer_mean_growth_accepted(self):
        # Zero interaction span yields int 0 from the parser (item 13 fix).
        artifact = _artifact()
        artifact["memory_growth"]["mean_growth_per_interaction_kib"] = 0
        self.assertEqual(validator.validate(artifact)["status"], "VALID")

    def test_json_text_roundtrip_valid(self):
        text = json.dumps(_artifact())
        self.assertEqual(validator.validate_json(text)["status"], "VALID")

    def test_json_bytes_roundtrip_valid(self):
        data = json.dumps(_artifact()).encode("utf-8")
        self.assertEqual(validator.validate_json(data)["status"], "VALID")

    def test_file_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text(json.dumps(_artifact()), encoding="utf-8")
            self.assertEqual(validator.validate_file(path)["status"], "VALID")

    def test_report_has_no_caller_keys(self):
        report = validator.validate(_artifact())
        expected = {
            "status", "schema", "evidence_count", "release_approved",
            "linux_mint_acceptance_proven", "real_hardware_measured",
            "owner_visual_approval", "measurement_performed",
        }
        self.assertEqual(set(report), expected)
        for evidence_key in ("frame_pacing", "memory_growth", "launch_latency",
                             "pss_kib", "evidence_kinds"):
            self.assertNotIn(evidence_key, report)


class SchemaAndKeyTests(unittest.TestCase):
    def test_wrong_schema_values_rejected(self):
        for bad in (2, 0, -1, "1", True, None, 1.0):
            with self.subTest(bad=bad):
                artifact = _artifact()
                artifact["schema"] = bad
                with self.assertRaises(validator.ArtifactError):
                    validator.validate(artifact)

    def test_extra_top_key_rejected(self):
        artifact = _artifact()
        artifact["owner_note_secrets"] = "SECRET_SENTINEL"
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)

    def test_missing_each_top_key_rejected(self):
        for key in validator.TOP_KEYS:
            with self.subTest(key=key):
                artifact = _artifact()
                del artifact[key]
                with self.assertRaises(validator.ArtifactError):
                    validator.validate(artifact)

    def test_wrong_top_container_rejected(self):
        for bad in (None, [], "text", 7, True):
            with self.subTest(bad=bad):
                with self.assertRaises(validator.ArtifactError):
                    validator.validate(bad)

    def test_no_raw_value_echo_in_error(self):
        artifact = _artifact()
        artifact["injected_secret_key_9f3a"] = "SUPER_SECRET_VALUE_XYZ"
        try:
            validator.validate(artifact)
            self.fail("expected ArtifactError")
        except validator.ArtifactError as exc:
            self.assertNotIn("SUPER_SECRET_VALUE_XYZ", str(exc))
            self.assertNotIn("injected_secret_key_9f3a", str(exc))

    def test_evidence_kinds_variants_rejected(self):
        variants = [
            list(reversed(validator.EVIDENCE_KINDS)),
            list(validator.EVIDENCE_KINDS) + ["extra"],
            ["frame_pacing", "memory_growth", "launch_latency"],
            [1, 2, 3, 4],
            tuple(validator.EVIDENCE_KINDS),
            None,
        ]
        for kinds in variants:
            with self.subTest(kinds=kinds):
                artifact = _artifact()
                artifact["evidence_kinds"] = kinds
                with self.assertRaises(validator.ArtifactError):
                    validator.validate(artifact)

    def test_evidence_count_mismatch_rejected(self):
        for count in (-1, 0, 3, 5, "4", True, None):
            with self.subTest(count=count):
                artifact = _artifact()
                artifact["evidence_count"] = count
                with self.assertRaises(validator.ArtifactError):
                    validator.validate(artifact)


class NegativeClaimTests(unittest.TestCase):
    def test_measurement_performed_flip_rejected(self):
        for bad in (True, 1, 0, None, "False"):
            with self.subTest(bad=bad):
                artifact = _artifact()
                artifact["measurement_performed"] = bad
                with self.assertRaises(validator.ArtifactError):
                    validator.validate(artifact)

    def test_real_hardware_flip_rejected(self):
        for bad in (True, 1, None):
            with self.subTest(bad=bad):
                artifact = _artifact()
                artifact["real_hardware_measured"] = bad
                with self.assertRaises(validator.ArtifactError):
                    validator.validate(artifact)

    def test_acceptance_claim_flip_rejected(self):
        for key in ("linux_mint_acceptance", "owner_visual_approval"):
            for bad in ("APPROVED", "PASSED", True, None, 1):
                with self.subTest(key=key, bad=bad):
                    artifact = _artifact()
                    artifact[key] = bad
                    with self.assertRaises(validator.ArtifactError):
                        validator.validate(artifact)

    def test_gpu_claim_flip_rejected(self):
        artifact = _artifact()
        artifact["frame_pacing"]["real_gpu_measurement"] = True
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)


class NestedShapeTests(unittest.TestCase):
    def test_frame_extra_key_rejected(self):
        artifact = _artifact()
        artifact["frame_pacing"]["surprise"] = 1
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)

    def test_frame_sample_inconsistency_rejected(self):
        artifact = _artifact()
        artifact["frame_pacing"]["samples_dropped"] = 7
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)

    def test_frame_percentile_order_rejected(self):
        artifact = _artifact()
        artifact["frame_pacing"]["p50_ms"] = 30.0
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)

    def test_frame_nonfinite_rejected(self):
        artifact = _artifact()
        artifact["frame_pacing"]["mean_ms"] = float("nan")
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)

    def test_memory_bad_delta_rejected(self):
        for bad in (2 ** 31, -(2 ** 31) - 1, True, 1.5, None):
            with self.subTest(bad=bad):
                artifact = _artifact()
                artifact["memory_growth"]["delta_kib"] = bad
                with self.assertRaises(validator.ArtifactError):
                    validator.validate(artifact)

    def test_memory_bad_status_rejected(self):
        artifact = _artifact()
        artifact["memory_growth"]["status"] = "FAILED"
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)

    def test_launch_schema_drift_rejected(self):
        artifact = _artifact()
        artifact["launch_latency"]["schema"] = 2
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)

    def test_launch_stat_extra_key_rejected(self):
        artifact = _artifact()
        artifact["launch_latency"]["cold"]["bonus"] = 1
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)

    def test_provenance_list_over_cap_rejected(self):
        artifact = _artifact()
        artifact["launch_latency"]["provenance"]["warnings"] = [
            "w" for _ in range(validator.MAX_PROVENANCE_VALUES + 1)
        ]
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)

    def test_excluded_over_cap_rejected(self):
        entry = {"kind": "k", "reason": "r", "source": "s", "clock": "c"}
        artifact = _artifact()
        artifact["launch_latency"]["provenance"]["excluded"] = [
            dict(entry) for _ in range(validator.MAX_EXCLUDED + 1)
        ]
        with self.assertRaises(validator.ArtifactError):
            validator.validate(artifact)

    def test_pss_bounds_rejected(self):
        for bad in (-1, 2 ** 31, True, 1.0, "150000"):
            with self.subTest(bad=bad):
                artifact = _artifact()
                artifact["pss_kib"] = bad
                with self.assertRaises(validator.ArtifactError):
                    validator.validate(artifact)


class JsonFileBoundaryTests(unittest.TestCase):
    def test_json_oversized_rejected(self):
        text = json.dumps(_artifact())
        padded = text + (" " * (validator.MAX_ARTIFACT_BYTES + 1))
        with self.assertRaises(validator.ArtifactError):
            validator.validate_json(padded)

    def test_json_empty_rejected(self):
        for bad in ("", b"", None, 7):
            with self.subTest(bad=bad):
                with self.assertRaises(validator.ArtifactError):
                    validator.validate_json(bad)

    def test_json_deep_nesting_rejected(self):
        deep = "[" * 20_000 + "0" + "]" * 20_000
        with self.assertRaises(validator.ArtifactError):
            validator.validate_json(deep)

    def test_json_nonfinite_constants_rejected(self):
        text = json.dumps(_artifact()).replace("16.6667", "NaN")
        with self.assertRaises(validator.ArtifactError):
            validator.validate_json(text)

    def test_json_malformed_rejected(self):
        with self.assertRaises(validator.ArtifactError):
            validator.validate_json("{not json")

    def test_surrogate_text_rejected(self):
        with self.assertRaises(validator.ArtifactError):
            validator.validate_json("\ud800")

    def test_file_relative_path_rejected(self):
        with self.assertRaises(validator.ArtifactError):
            validator.validate_file("snapshot.json")

    def test_file_missing_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(validator.ArtifactError):
                validator.validate_file(Path(tmp) / "missing.json")

    def test_file_oversized_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.json"
            path.write_bytes(b"x" * (validator.MAX_ARTIFACT_BYTES + 1))
            with self.assertRaises(validator.ArtifactError):
                validator.validate_file(path)

    def test_file_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.json"
            real.write_text(json.dumps(_artifact()), encoding="utf-8")
            link = Path(tmp) / "link.json"
            try:
                link.symlink_to(real)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this host")
            with self.assertRaises(validator.ArtifactError):
                validator.validate_file(link)


class CliTests(unittest.TestCase):
    def test_cli_valid_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ok.json"
            path.write_text(json.dumps(_artifact()), encoding="utf-8")
            self.assertEqual(validator.main([str(path)]), 0)

    def test_cli_invalid_marker_and_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{bad", encoding="utf-8")
            self.assertEqual(validator.main([str(path)]), 1)

    def test_cli_missing_file_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(validator.main([str(Path(tmp) / "none.json")]), 1)


class PurityTests(unittest.TestCase):
    def test_no_runtime_or_visual_imports(self):
        source = Path(validator.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {
            "subprocess", "socket", "threading", "multiprocessing", "time",
            "datetime", "random", "ctypes", "PyQt6", "PySide6", "requests",
            "urllib", "shutil", "resource",
        }
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & forbidden)


if __name__ == "__main__":
    unittest.main()
