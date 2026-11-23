"""Contract tests for the bounded offline performance evidence snapshot."""
import ast
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType

from canopy_features.performance.frame_pacing import parse_frame_times
from canopy_features.performance.launch_latency import (
    LaunchSample, SCHEMA as LAUNCH_SCHEMA, summarize,
)
from canopy_features.performance.memory_delta import MemorySample, report_growth
from canopy_features.performance.performance_snapshot import (
    EVIDENCE_KINDS, MAX_PROVENANCE_VALUES, NOT_ESTABLISHED, SCHEMA,
    SnapshotError, compose_snapshot,
)


def frame():
    return parse_frame_times([16.7, 16.8, 33.4], refresh_hz=60)


def memory():
    return report_growth([
        MemorySample(0, 100_000),
        MemorySample(1, 102_000),
        MemorySample(2, 101_000),
    ])


def launch(with_excluded=False):
    samples = [
        LaunchSample("cold", 0, 20_000_000, "measure_qt:READY"),
        LaunchSample("warm", 0, 10_000_000, "measure_qt:READY"),
    ]
    if with_excluded:
        samples.append(LaunchSample("cold", None, None, "measure_qt:READY"))
    return summarize(samples)


class PerformanceSnapshotTests(unittest.TestCase):
    def test_empty_record_defaults_and_negative_claims(self):
        snap = compose_snapshot()
        self.assertEqual(snap.schema, SCHEMA)
        self.assertEqual(snap.evidence_kinds, EVIDENCE_KINDS)
        self.assertEqual(snap.evidence_count, 0)
        for field in ("frame_pacing", "memory_growth", "launch_latency",
                      "pss_kib"):
            self.assertIsNone(getattr(snap, field))
        self.assertIs(snap.measurement_performed, False)
        self.assertIs(snap.real_hardware_measured, False)
        self.assertEqual(snap.linux_mint_acceptance, NOT_ESTABLISHED)
        self.assertEqual(snap.owner_visual_approval, NOT_ESTABLISHED)

    def test_record_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            compose_snapshot().schema = 99

    def test_schema_constants_stable(self):
        self.assertEqual(SCHEMA, 1)
        self.assertEqual(EVIDENCE_KINDS,
                         ("frame_pacing", "memory_growth",
                          "launch_latency", "pss"))
        self.assertIsInstance(EVIDENCE_KINDS, tuple)

    def test_frame_pacing_embedded(self):
        report = frame()
        snap = compose_snapshot(frame_pacing=report)
        self.assertIs(snap.frame_pacing, report)
        self.assertEqual(snap.evidence_count, 1)
        self.assertEqual(snap.as_dict()["frame_pacing"]["backend"], "default")
        self.assertIs(snap.as_dict()["frame_pacing"]["real_gpu_measurement"],
                      False)

    def test_frame_pacing_wrong_type_fails_closed(self):
        for bad in ({}, [], "report", 7, True):
            with self.subTest(bad=bad), self.assertRaises(SnapshotError):
                compose_snapshot(frame_pacing=bad)

    def test_memory_projection_exact_keys_and_immutable(self):
        snap = compose_snapshot(memory_growth=memory())
        projected = snap.memory_growth
        self.assertIsInstance(projected, MappingProxyType)
        self.assertEqual(set(projected), {
            "start_kib", "end_kib", "delta_kib", "interactions",
            "sample_count", "peak_kib", "min_kib", "delta_percent",
            "mean_growth_per_interaction_kib", "status",
        })
        self.assertEqual(projected["delta_kib"], 1000)
        self.assertEqual(projected["status"], "ok")
        with self.assertRaises(TypeError):
            projected["delta_kib"] = 0

    def test_memory_unknown_keys_are_not_injected(self):
        source = memory()
        source["schema"] = 999
        source["measurement_performed"] = True
        source["__class__"] = "injected"
        snap = compose_snapshot(memory_growth=source)
        self.assertEqual(set(snap.memory_growth),
                         set(memory()))
        self.assertEqual(snap.as_dict()["schema"], SCHEMA)
        self.assertIs(snap.as_dict()["measurement_performed"], False)

    def test_memory_bool_and_wrong_types_fail_closed(self):
        for key in ("start_kib", "delta_kib", "interactions", "sample_count",
                    "peak_kib", "min_kib", "end_kib"):
            source = memory()
            source[key] = True
            with self.subTest(key=key), self.assertRaises(SnapshotError):
                compose_snapshot(memory_growth=source)
        source = memory()
        source["delta_percent"] = "1.0"
        with self.assertRaises(SnapshotError):
            compose_snapshot(memory_growth=source)

    def test_memory_missing_key_fails_closed(self):
        for key in memory():
            source = memory()
            del source[key]
            with self.subTest(key=key), self.assertRaises(SnapshotError):
                compose_snapshot(memory_growth=source)

    def test_memory_wrong_status_fails_closed(self):
        source = memory()
        source["status"] = "PASSED"
        with self.assertRaises(SnapshotError):
            compose_snapshot(memory_growth=source)

    def test_launch_projection_exact_schema_and_immutable(self):
        snap = compose_snapshot(launch_latency=launch())
        projected = snap.launch_latency
        self.assertIsInstance(projected, MappingProxyType)
        self.assertEqual(set(projected), {"schema", "cold", "warm",
                                          "provenance"})
        self.assertEqual(projected["schema"], LAUNCH_SCHEMA)
        self.assertIsInstance(projected["cold"], MappingProxyType)
        self.assertEqual(projected["warm"]["count"], 1)
        self.assertEqual(projected["provenance"]["sample_count"], 2)
        with self.assertRaises(TypeError):
            projected["schema"] = 99
        self.assertEqual(json.dumps(snap.as_dict(), sort_keys=True),
                         json.dumps(compose_snapshot(
                             launch_latency=launch()).as_dict(),
                             sort_keys=True))

    def test_launch_wrong_schema_fails_closed(self):
        source = launch()
        source["schema"] = 999
        with self.assertRaises(SnapshotError):
            compose_snapshot(launch_latency=source)

    def test_launch_provenance_is_bounded(self):
        source = launch()
        source["provenance"]["sources"] = [
            "s%d" % i for i in range(MAX_PROVENANCE_VALUES + 1)
        ]
        with self.assertRaises(SnapshotError):
            compose_snapshot(launch_latency=source)

    def test_launch_excluded_entries_are_immutable(self):
        snap = compose_snapshot(launch_latency=launch(with_excluded=True))
        excluded = snap.launch_latency["provenance"]["excluded"]
        self.assertIsInstance(excluded, tuple)
        self.assertEqual(len(excluded), 1)
        self.assertIsInstance(excluded[0], MappingProxyType)
        self.assertEqual(set(excluded[0]), {"kind", "reason", "source",
                                            "clock"})
        self.assertEqual(excluded[0]["reason"], "missing_timestamp")
        with self.assertRaises(TypeError):
            excluded[0]["reason"] = "PASSED"

    def test_launch_unknown_keys_are_not_injected(self):
        source = launch()
        source["owner_visual_approval"] = "APPROVED"
        source["cold"]["fake"] = True
        source["provenance"]["fake"] = True
        snap = compose_snapshot(launch_latency=source)
        self.assertEqual(set(snap.launch_latency), {"schema", "cold", "warm",
                                                    "provenance"})
        self.assertEqual(set(snap.launch_latency["cold"]),
                         {"count", "min_ms", "max_ms", "mean_ms",
                          "median_ms"})
        self.assertEqual(snap.owner_visual_approval, NOT_ESTABLISHED)

    def test_pss_validation(self):
        self.assertEqual(compose_snapshot(pss_kib=2048).pss_kib, 2048)
        for bad in (True, -1, "2048", 2 ** 31, 1.5, []):
            with self.subTest(bad=bad), self.assertRaises(SnapshotError):
                compose_snapshot(pss_kib=bad)

    def test_as_dict_is_fresh_and_json_serializable(self):
        snap = compose_snapshot(frame_pacing=frame(), memory_growth=memory(),
                                launch_latency=launch(with_excluded=True),
                                pss_kib=4096)
        self.assertEqual(snap.evidence_count, 4)
        blob = json.dumps(snap.as_dict(), sort_keys=True)
        self.assertEqual(json.loads(blob)["pss_kib"], 4096)
        first = snap.as_dict()
        first["measurement_performed"] = True
        first["memory_growth"]["delta_kib"] = 0
        self.assertIs(snap.measurement_performed, False)
        self.assertEqual(snap.memory_growth["delta_kib"], 1000)

    def test_no_live_alias_to_caller_containers(self):
        mem_source, launch_source = memory(), launch()
        snap = compose_snapshot(memory_growth=mem_source,
                                launch_latency=launch_source)
        mem_source["delta_kib"] = 999
        launch_source["provenance"]["clocks"].append("realtime")
        self.assertEqual(snap.memory_growth["delta_kib"], 1000)
        self.assertEqual(snap.launch_latency["provenance"]["clocks"],
                         ("monotonic",))

    def test_negative_claims_cannot_be_supplied(self):
        for field in ("measurement_performed", "real_hardware_measured",
                      "linux_mint_acceptance", "owner_visual_approval",
                      "schema", "evidence_kinds"):
            with self.subTest(field=field), self.assertRaises(TypeError):
                compose_snapshot(**{field: "forged"})

    def test_valid_negative_growth_is_preserved(self):
        # memory_delta documents that released memory is reported as-is.
        released = report_growth([
            MemorySample(0, 200_000), MemorySample(1, 150_000),
        ])
        self.assertEqual(released["delta_kib"], -50_000)
        snap = compose_snapshot(memory_growth=released)
        self.assertEqual(snap.memory_growth["delta_kib"], -50_000)
        self.assertEqual(snap.memory_growth["delta_percent"], -25.0)

    def test_valid_zero_span_integer_mean_is_preserved(self):
        # report_growth returns an int mean when interactions span zero.
        same_span = report_growth([
            MemorySample(5, 120_000), MemorySample(5, 130_000),
        ])
        self.assertEqual(type(same_span["mean_growth_per_interaction_kib"]),
                         int)
        snap = compose_snapshot(memory_growth=same_span)
        self.assertEqual(snap.memory_growth["interactions"], 0)
        self.assertEqual(snap.memory_growth["mean_growth_per_interaction_kib"],
                         10_000)

    def test_delta_kib_remains_bounded_after_signed_support(self):
        source = memory()
        source["delta_kib"] = -(2 ** 31)
        with self.assertRaises(SnapshotError):
            compose_snapshot(memory_growth=source)
        source["delta_kib"] = True
        with self.assertRaises(SnapshotError):
            compose_snapshot(memory_growth=source)

    def test_no_measurement_or_visual_imports(self):
        source = Path(__file__).resolve().parents[1] / (
            "canopy_features/performance/performance_snapshot.py")
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & {
            "subprocess", "socket", "threading", "time", "datetime",
            "pathlib", "os", "PyQt5", "PySide6", "shutil",
        })


if __name__ == "__main__":
    unittest.main()
