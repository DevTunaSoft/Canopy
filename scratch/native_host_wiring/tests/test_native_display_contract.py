"""Offline tests for the native display wire contract (SYNTHETIC only)."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from canopy_features.dock.display_change_response import (
    KIND_HOLD, KIND_NO_OP, KIND_RELAYOUT, KIND_SUSPEND,
)
from canopy_features.quick_controls.native_display_contract import (
    WIRE_VERSION,
    NativeDisplayContractError,
    NativeDisplayProducer,
    ScreenObservation,
    plan_from_wire,
    plan_to_wire,
)

HERE = Path(__file__).resolve().parent


class ScreenObservationTests(unittest.TestCase):
    def test_sorted_deduplicated_connectors(self):
        obs = ScreenObservation(("DP-1", "HDMI-1"), "HDMI-1", 1920, 1080)
        self.assertEqual(obs.connectors, ("DP-1", "HDMI-1"))

    def test_hostile_payload_fails_closed_in_producer(self):
        producer = NativeDisplayProducer()
        plan = producer.apply_recovery({
            "connectors": ["bad|connector"], "primary": "bad|connector",
            "width": 1920, "height": 1080, "source": "qt.screen",
        })
        self.assertEqual(plan["kind"], KIND_HOLD)
        self.assertEqual(plan["reason"], "invalid_event")
        self.assertEqual((plan["width"], plan["height"]), (1200, 750))

    def test_constructor_rejects_missing_primary_and_duplicates(self):
        with self.assertRaises(NativeDisplayContractError):
            ScreenObservation(("HDMI-1", "HDMI-1"), "HDMI-1", 1920, 1080)
        with self.assertRaises(NativeDisplayContractError):
            ScreenObservation(("HDMI-1",), "DP-1", 1920, 1080)
        with self.assertRaises(NativeDisplayContractError):
            ScreenObservation(("HDMI-1",), "HDMI-1", True, 1080)


class ProducerTests(unittest.TestCase):
    def test_recovery_initial_and_last_monitor_removed(self):
        producer = NativeDisplayProducer()
        first = producer.apply_recovery({
            "connectors": ["HDMI-1"], "primary": "HDMI-1",
            "width": 1920, "height": 1080, "source": "qt.screen",
        })
        self.assertEqual((first["kind"], first["reason"]),
                         (KIND_RELAYOUT, "connect"))
        self.assertEqual((first["width"], first["height"]), (1200, 750))
        gone = producer.apply_recovery({
            "connectors": [], "primary": None, "width": None,
            "height": None, "source": "qt.screen",
        })
        self.assertEqual((gone["kind"], gone["reason"]),
                         (KIND_SUSPEND, "no_display"))
        self.assertEqual((gone["width"], gone["height"]), (1200, 750))

    def test_logical_dpi_150_trap_and_duplicate(self):
        producer = NativeDisplayProducer()
        first = producer.apply_logical_dpi(1920, 1080, 1.5, "HDMI-1")
        self.assertEqual((first["width"], first["height"]), (1200, 720))
        self.assertEqual(first["reason"], "logical_dpi_changed")
        duplicate = producer.apply_logical_dpi(1920, 1080, 1.5, "HDMI-1")
        self.assertEqual((duplicate["kind"], duplicate["reason"]),
                         (KIND_NO_OP, "unchanged"))
        self.assertEqual((duplicate["width"], duplicate["height"]), (1200, 720))

    def test_hostile_scale_and_connector(self):
        producer = NativeDisplayProducer()
        for scale, connector in ((5.0, "HDMI-1"), (1.5, "bad|connector")):
            plan = producer.apply_logical_dpi(1920, 1080, scale, connector)
            self.assertEqual(plan["kind"], KIND_HOLD)
            self.assertEqual(plan["reason"], "invalid_event")
            self.assertEqual((plan["width"], plan["height"]), (1200, 750))

    def test_no_new_topic_and_bounded_history(self):
        producer = NativeDisplayProducer()
        self.assertIn("capabilities.report", producer.topics)
        for index in range(80):
            producer.apply_logical_dpi(1920 + index, 1080, 1.5, "HDMI-1")
        self.assertLessEqual(len(producer.history), 64)


class WireTests(unittest.TestCase):
    def test_roundtrip(self):
        payload = {
            "version": WIRE_VERSION, "sequence": 3, "kind": KIND_RELAYOUT,
            "width": 1200, "height": 720, "reason": "logical_dpi_changed",
            "source": "qt.screen",
        }
        self.assertEqual(plan_from_wire(payload), payload)
        self.assertEqual(plan_to_wire(type("P", (), {
            "sequence": 3, "kind": KIND_RELAYOUT, "size": (1200, 720),
            "reason": "logical_dpi_changed",
        })()), payload)

    def test_untrusted_wire_fails_closed(self):
        for hostile in (
            {"version": 99, "kind": KIND_RELAYOUT, "reason": "connect",
             "sequence": 1, "width": 1200, "height": 750, "source": "qt.screen"},
            {"version": WIRE_VERSION, "kind": "resize-everything",
             "reason": "connect", "sequence": 1, "width": 1200, "height": 750,
             "source": "qt.screen"},
            {"version": WIRE_VERSION, "kind": KIND_RELAYOUT,
             "reason": "connect", "sequence": True, "width": 1200,
             "height": 750, "source": "qt.screen"},
        ):
            with self.subTest(hostile=hostile):
                with self.assertRaises(NativeDisplayContractError):
                    plan_from_wire(hostile)

    def test_canonical_vectors_match_generator(self):
        data = json.loads((HERE.parent / "canonical_vectors.json").read_text(
            encoding="utf-8"))
        self.assertEqual(len(data["cases"]), 13)
        for case in data["cases"]:
            with self.subTest(case=case["id"]):
                self.assertIn(case["expected"]["reason"], (
                    "connect", "resolution_changed", "primary_changed",
                    "no_display", "logical_dpi_changed",
                    "logical_size_unchanged", "below_minimum", "unchanged",
                    "invalid_event"))


class SourceBoundaryTests(unittest.TestCase):
    def test_pure_module_has_no_runtime_boundary(self):
        source = (HERE.parents[2] /
                  "canopy_features/quick_controls/native_display_contract.py"
                  ).read_text(encoding="utf-8")
        for token in ("import Qt", "QTimer", "import socket", "socket.socket",
                      "import subprocess", "import threading", "open(",
                      "QProcess", "while True:"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
