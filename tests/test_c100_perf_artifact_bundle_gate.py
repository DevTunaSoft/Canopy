"""Regression tests for the bounded offline performance artifact bundle gate.

Run: python -m unittest tests.test_c100_perf_artifact_bundle_gate -v
"""
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError

from tools.qa import perf_artifact_bundle_gate as gate
from canopy_features.performance.frame_pacing import parse_frame_times
from canopy_features.performance.performance_snapshot import compose_snapshot

SOURCE = "f" * 40
BINARY = "e" * 64
CLAIM_KEYS = (
    "release_approved", "linux_mint_acceptance_proven",
    "real_hardware_measured", "owner_visual_approval",
    "measurement_performed",
)
REPORT_KEYS = (
    "status", "schema", "snapshot_count", "snapshot_evidence_counts",
    "baseline_count", "baseline_statuses",
) + CLAIM_KEYS


def _snapshot():
    """A real artifact produced by the already-tested producer."""
    return compose_snapshot(frame_pacing=parse_frame_times([8.0])).as_dict()


def _short():
    return {
        "schema": 1,
        "kind": "short-headless-baseline-not-mint-acceptance",
        "duration_seconds": 5.0,
        "cpu_percent_one_core": 0.5,
        "pss_kib_start": 60_000,
        "pss_kib_end": 61_000,
        "backend": "software",
    }


def _long():
    return {
        "schema": 2, "kind": "five-minute-idle-linux-qt",
        "environment": "linuxmint",
        "measurement_method": "proc-smaps-rollup-and-stat",
        "source_sha": SOURCE, "binary_sha256": BINARY,
        "backend": "software", "duration_seconds": 305,
        "sample_count": 62, "cpu_ticks_start": 12_340,
        "cpu_ticks_end": 12_500, "clock_ticks_per_second": 100,
        "pss_kib_start": 55_000, "pss_kib_end": 62_000,
        "pss_kib_peak": 65_000,
    }


def _bundle(snapshots=None, baselines=None, source_sha=None,
            binary_sha256=None):
    return {
        "schema": 1,
        "snapshots": [_snapshot()] if snapshots is None else snapshots,
        "baselines": [] if baselines is None else baselines,
        "source_sha": source_sha,
        "binary_sha256": binary_sha256,
    }


class RealCompositionTests(unittest.TestCase):
    def test_real_snapshot_with_short_baseline(self):
        report = gate.evaluate_bundle(_bundle(baselines=[_short()])).as_dict()
        self.assertEqual(report["snapshot_count"], 1)
        self.assertEqual(report["snapshot_evidence_counts"], [1])
        self.assertEqual(report["baseline_statuses"], ["INSUFFICIENT_EVIDENCE"])
        self.assertEqual(report["status"], "VALID")
        for key in CLAIM_KEYS:
            self.assertIs(report[key], False)

    def test_long_baseline_with_matching_pins(self):
        report = gate.evaluate_bundle(_bundle(
            baselines=[_long()], source_sha=SOURCE,
            binary_sha256=BINARY)).as_dict()
        self.assertEqual(report["baseline_statuses"], ["PASS"])

    def test_multiple_members_preserve_order(self):
        report = gate.evaluate_bundle(_bundle(
            snapshots=[_snapshot(), compose_snapshot(
                frame_pacing=parse_frame_times([9.0, 10.0])).as_dict()],
            baselines=[_short(), _short(), _long()],
            source_sha=SOURCE, binary_sha256=BINARY,
        )).as_dict()
        self.assertEqual(report["snapshot_count"], 2)
        self.assertEqual(report["snapshot_evidence_counts"], [1, 1])
        self.assertEqual(report["baseline_statuses"],
                         ["INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE", "PASS"])
        self.assertEqual(report["baseline_count"], 3)

    def test_no_baselines_is_valid(self):
        report = gate.evaluate_bundle(_bundle()).as_dict()
        self.assertEqual(report["baseline_count"], 0)
        self.assertEqual(report["baseline_statuses"], [])

    def test_report_is_frozen(self):
        record = gate.evaluate_bundle(_bundle())
        with self.assertRaises(FrozenInstanceError):
            record.snapshot_count = 99

    def test_as_dict_is_fresh(self):
        record = gate.evaluate_bundle(_bundle(baselines=[_short()]))
        first = record.as_dict()
        first["baseline_statuses"].append("PASS")
        first["release_approved"] = True
        second = record.as_dict()
        self.assertEqual(second["baseline_statuses"], ["INSUFFICIENT_EVIDENCE"])
        self.assertIs(second["release_approved"], False)

    def test_as_dict_fixed_key_order(self):
        record = gate.evaluate_bundle(_bundle())
        self.assertEqual(tuple(record.as_dict()), REPORT_KEYS)

    def test_deterministic_serialization(self):
        record = gate.evaluate_bundle(_bundle(baselines=[_short()]))
        left = json.dumps(record.as_dict(), sort_keys=True)
        right = json.dumps(record.as_dict(), sort_keys=True)
        self.assertEqual(left, right)

    def test_forged_record_cannot_emit_approval(self):
        forged = gate.BundleReport(
            snapshot_count=8, snapshot_evidence_counts=(4, 4),
            baseline_count=8, baseline_statuses=("PASS",) * 8,
        )
        report = forged.as_dict()
        self.assertEqual(report["status"], "VALID")
        for key in CLAIM_KEYS:
            self.assertIs(report[key], False)


class ShapeBoundaryTests(unittest.TestCase):
    def test_bundle_must_be_dict(self):
        for value in (None, [], "bundle", 7, True, (), set()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(gate.BundleError):
                    gate.evaluate_bundle(value)

    def test_missing_key_rejected(self):
        bundle = _bundle()
        for key in gate.TOP_KEYS:
            with self.subTest(key=key):
                bad = dict(bundle)
                del bad[key]
                with self.assertRaises(gate.BundleError):
                    gate.evaluate_bundle(bad)

    def test_extra_key_rejected(self):
        bundle = _bundle()
        bundle["approved"] = True
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(bundle)

    def test_schema_boundary(self):
        for value in (None, True, "1", 0, 2, 1.0):
            with self.subTest(value=repr(value)):
                bundle = _bundle()
                bundle["schema"] = value
                with self.assertRaises(gate.BundleError):
                    gate.evaluate_bundle(bundle)

    def test_snapshots_must_be_nonempty_list(self):
        for value in (None, [], (), "x", 7, {}, True):
            with self.subTest(value=repr(value)):
                bundle = _bundle()
                bundle["snapshots"] = value
                with self.assertRaises(gate.BundleError):
                    gate.evaluate_bundle(bundle)

    def test_baselines_must_be_list(self):
        for value in (None, (), "x", 7, {}, True):
            with self.subTest(value=repr(value)):
                bundle = _bundle()
                bundle["baselines"] = value
                with self.assertRaises(gate.BundleError):
                    gate.evaluate_bundle(bundle)

    def test_snapshot_entry_wrong_type(self):
        for value in (None, [], "x", 7, True, {}):
            with self.subTest(value=repr(value)):
                with self.assertRaises(gate.BundleError):
                    gate.evaluate_bundle(_bundle(snapshots=[value]))

    def test_baseline_entry_wrong_type(self):
        for value in (None, [], "x", 7, True, {}):
            with self.subTest(value=repr(value)):
                with self.assertRaises(gate.BundleError):
                    gate.evaluate_bundle(_bundle(baselines=[value]))


class CapacityTests(unittest.TestCase):
    def test_max_snapshots_accepted(self):
        record = gate.evaluate_bundle(_bundle(snapshots=[_snapshot()] * gate.MAX_SNAPSHOTS))
        self.assertEqual(record.snapshot_count, gate.MAX_SNAPSHOTS)

    def test_snapshots_n_plus_one_rejected(self):
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(
                snapshots=[_snapshot()] * (gate.MAX_SNAPSHOTS + 1)))

    def test_max_baselines_accepted(self):
        record = gate.evaluate_bundle(_bundle(
            baselines=[_short()] * gate.MAX_BASELINES))
        self.assertEqual(record.baseline_count, gate.MAX_BASELINES)

    def test_baselines_n_plus_one_rejected(self):
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(
                baselines=[_short()] * (gate.MAX_BASELINES + 1)))


class PinTests(unittest.TestCase):
    def test_none_pins_accepted(self):
        gate.evaluate_bundle(_bundle())

    def test_valid_pins_accepted(self):
        gate.evaluate_bundle(_bundle(source_sha=SOURCE, binary_sha256=BINARY))

    def test_wrong_pin_types_rejected(self):
        for value in (7, True, b"f" * 40, [], {}, 1.0):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(gate.BundleError):
                    gate.evaluate_bundle(_bundle(source_sha=value))

    def test_wrong_pin_lengths_rejected(self):
        for value in ("f" * 39, "f" * 41, "e" * 63, "e" * 65, ""):
            with self.subTest(length=len(value)):
                with self.assertRaises(gate.BundleError):
                    gate.evaluate_bundle(_bundle(source_sha=value))

    def test_uppercase_and_nonhex_pins_rejected(self):
        for value in ("F" * 40, "z" * 40, "-" * 40):
            with self.subTest(value=value[:3]):
                with self.assertRaises(gate.BundleError):
                    gate.evaluate_bundle(_bundle(source_sha=value))

    def test_binary_pin_shape_enforced(self):
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(source_sha=SOURCE, binary_sha256="e" * 40))

    def test_long_baseline_without_pins_rejected(self):
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(baselines=[_long()]))

    def test_long_baseline_with_mismatched_pins_rejected(self):
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(
                baselines=[_long()], source_sha="a" * 40,
                binary_sha256=BINARY))


class SubValidatorTests(unittest.TestCase):
    def test_claim_flipped_snapshot_rejected(self):
        artifact = _snapshot()
        artifact["measurement_performed"] = True
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(snapshots=[artifact]))

    def test_hardware_claim_flip_rejected(self):
        artifact = _snapshot()
        artifact["real_hardware_measured"] = True
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(snapshots=[artifact]))

    def test_schema_drifted_snapshot_rejected(self):
        artifact = _snapshot()
        artifact["schema"] = 2
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(snapshots=[artifact]))

    def test_injected_snapshot_key_rejected(self):
        artifact = _snapshot()
        artifact["approved"] = True
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(snapshots=[artifact]))

    def test_out_of_range_baseline_rejected(self):
        evidence = _short()
        evidence["cpu_percent_one_core"] = 5000.0
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(baselines=[evidence]))

    def test_drifted_baseline_schema_rejected(self):
        evidence = _short()
        evidence["schema"] = 2
        with self.assertRaises(gate.BundleError):
            gate.evaluate_bundle(_bundle(baselines=[evidence]))

    def test_fixed_errors_never_echo_caller_values(self):
        sentinel = "LEAK_THIS_SENTINEL"
        artifact = _snapshot()
        artifact["measurement_source"] = sentinel
        artifact["owner_visual_approval"] = "APPROVED"
        evidence = _short()
        evidence["cpu_percent_one_core"] = sentinel
        for bundle in (_bundle(snapshots=[artifact]),
                       _bundle(baselines=[evidence])):
            with self.subTest(member=type(bundle).__name__):
                with self.assertRaises(gate.BundleError) as ctx:
                    gate.evaluate_bundle(bundle)
                self.assertNotIn(sentinel, str(ctx.exception))
                self.assertNotIn("APPROVED", str(ctx.exception))


class JsonFileBoundaryTests(unittest.TestCase):
    def test_json_text_and_bytes(self):
        payload = json.dumps(_bundle(baselines=[_short()])).encode("utf-8")
        for value in (payload, payload.decode("utf-8")):
            with self.subTest(value=type(value).__name__):
                report = gate.validate_bundle_json(value).as_dict()
                self.assertEqual(report["baseline_count"], 1)

    def test_json_wrong_type_rejected(self):
        for value in (None, 7, True, [], {}, object()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(gate.BundleError):
                    gate.validate_bundle_json(value)

    def test_empty_and_oversized_json_rejected(self):
        for value in (b"", b" " * gate.MAX_BUNDLE_BYTES + b"x"):
            with self.subTest(length=len(value)):
                with self.assertRaises(gate.BundleError):
                    gate.validate_bundle_json(value)

    def test_malformed_json_rejected(self):
        with self.assertRaises(gate.BundleError):
            gate.validate_bundle_json(b"{not json")

    def test_nonfinite_constant_rejected(self):
        with self.assertRaises(gate.BundleError):
            gate.validate_bundle_json(b'{"x": NaN}')

    def test_deeply_nested_json_translated(self):
        depth = 15_000
        payload = b"[" * depth + b"]" * depth
        self.assertLessEqual(len(payload), gate.MAX_BUNDLE_BYTES)
        with self.assertRaises(gate.BundleError):
            gate.validate_bundle_json(payload)

    def test_file_happy_path(self):
        payload = json.dumps(_bundle(baselines=[_short()])).encode("utf-8")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bundle.json"
            path.write_bytes(payload)
            report = gate.validate_bundle_file(path).as_dict()
            self.assertEqual(report["snapshot_count"], 1)

    def test_relative_and_missing_paths_rejected(self):
        with self.assertRaises(gate.BundleError):
            gate.validate_bundle_file("relative.json")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(gate.BundleError):
                gate.validate_bundle_file(Path(td) / "missing.json")

    def test_directory_path_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(gate.BundleError):
                gate.validate_bundle_file(Path(td))

    def test_symlink_path_rejected(self):
        payload = json.dumps(_bundle()).encode("utf-8")
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real.json"
            link = Path(td) / "link.json"
            real.write_bytes(payload)
            try:
                link.symlink_to(real)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this host")
            with self.assertRaises(gate.BundleError):
                gate.validate_bundle_file(link)


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = Path(gate.__file__).resolve()
        cls.repo = cls.module.parents[2]

    def _run(self, payload):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bundle.json"
            path.write_bytes(payload)
            return subprocess.run(
                [sys.executable, str(self.module), str(path)],
                cwd=str(self.repo), capture_output=True, text=True, timeout=60,
            )

    def test_cli_success(self):
        payload = json.dumps(_bundle(baselines=[_short()])).encode("utf-8")
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        for key in CLAIM_KEYS:
            self.assertIs(report[key], False)

    def test_cli_failure_marker(self):
        artifact = _snapshot()
        artifact["measurement_performed"] = True
        payload = json.dumps(_bundle(snapshots=[artifact])).encode("utf-8")
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("QT_PERF_BUNDLE_FAIL:", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_cli_malformed_json_has_no_traceback(self):
        proc = self._run(b"{not json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("QT_PERF_BUNDLE_FAIL:", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


class PurityTests(unittest.TestCase):
    def test_no_forbidden_imports(self):
        forbidden = {
            "subprocess", "socket", "threading", "time", "random",
            "PyQt6", "PySide6", "shutil", "asyncio", "multiprocessing",
        }
        tree = ast.parse(Path(gate.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], forbidden)
            elif isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotIn(node.module.split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
