"""Contract tests for the trusted host-event source behind the Classic centre.

The adapter is pure in-process code: it consumes real ``HostEvent`` instances
from the existing ``canopy_core.host_events`` bus. These tests never fabricate
``HostEvent`` objects and never claim a desktop notification service exists.
"""
import ast
import json
import re
import unittest
from pathlib import Path

from canopy_core.host_events import (
    TOPICS as HOST_EVENT_TOPICS,
    HostEventError,
)

from canopy_features.notifications.host_event_source import (
    ALLOWED_TOPICS,
    MAX_ITEMS,
    SOURCE,
    NoticeRecordError,
    TrustedHostEventSource,
)

ROOT = Path(__file__).resolve().parents[1]
QML = (ROOT / "prototype" / "classic" / "NotificationCenter.qml").read_text(
    encoding="utf-8")


def _qml_topics():
    match = re.search(r"contractTopics:\s*\[(.*?)\]", QML, re.DOTALL)
    return json.loads("[" + match.group(1) + "]")


class TrustedSourceTests(unittest.TestCase):
    def test_real_host_event_produces_one_bounded_notice(self):
        source = TrustedHostEventSource()
        try:
            result = source.emit("app.catalog.changed", {"item_count": 3})
            self.assertEqual((result.delivered, result.callback_failures), (1, 0))
            snapshot = source.snapshot()
            self.assertEqual(len(snapshot), 1)
            record = snapshot[0]
            self.assertEqual(record["source"], "host-events")
            self.assertEqual(record["topic"], "app.catalog.changed")
            self.assertEqual(record["id"],
                             "host-events:app.catalog.changed:%d" % result.event.sequence)
            self.assertIn("item_count=3", record["body"])
            self.assertTrue(source.connected())
            self.assertEqual(source.source(), "host-events")
            self.assertEqual(set(source.allowedTopics()), set(HOST_EVENT_TOPICS))
        finally:
            source.close()

    def test_snapshot_is_bounded_and_newest_first(self):
        source = TrustedHostEventSource()
        try:
            for index in range(MAX_ITEMS + 2):
                source.emit("app.catalog.changed", {"item_count": index})
            snapshot = source.snapshot()
            sequences = [int(record["id"].rsplit(":", 1)[1])
                         for record in snapshot]
            self.assertEqual(len(snapshot), MAX_ITEMS)
            self.assertEqual(sequences, list(range(MAX_ITEMS + 2, 2, -1)))
            self.assertEqual(source.dropped_count, 2)
        finally:
            source.close()

    def test_event_without_a_projected_field_creates_no_row(self):
        source = TrustedHostEventSource()
        try:
            source.emit("session.state.changed", {"window_count": 2})
            source.emit("app.catalog.changed", {})
            self.assertEqual(source.snapshot(), [])
        finally:
            source.close()

    def test_snapshot_records_are_fresh_copies(self):
        source = TrustedHostEventSource()
        try:
            source.emit("session.state.changed", {"state": "active"})
            source.snapshot()[0]["body"] = "mutated"
            self.assertIn("state=active", source.snapshot()[0]["body"])
        finally:
            source.close()

    def test_close_fails_closed(self):
        source = TrustedHostEventSource()
        source.emit("session.state.changed", {"state": "active"})
        source.close()
        source.close()
        self.assertFalse(source.connected())
        self.assertEqual(source.snapshot(), [])
        with self.assertRaises(NoticeRecordError):
            source.emit("session.state.changed", {"state": "active"})

    def test_invalid_capacity_is_rejected(self):
        for capacity in (0, -1, MAX_ITEMS + 1, True, 2.0, "12", None):
            with self.subTest(capacity=capacity):
                with self.assertRaises(NoticeRecordError):
                    TrustedHostEventSource(max_items=capacity)


class HostilePayloadTests(unittest.TestCase):
    def setUp(self):
        self.source = TrustedHostEventSource()

    def tearDown(self):
        self.source.close()

    def test_unsafe_control_characters_are_not_projected(self):
        self.source.emit("session.state.changed", {"state": "active\nsystem"})
        self.assertEqual(self.source.snapshot(), [])

    def test_bidirectional_override_is_not_projected(self):
        self.source.emit("session.state.changed", {"state": "\u202eactive"})
        self.assertEqual(self.source.snapshot(), [])

    def test_oversized_value_is_not_projected(self):
        self.source.emit("session.state.changed", {"state": "x" * 300})
        self.assertEqual(self.source.snapshot(), [])

    def test_unsafe_event_object_is_not_projected(self):
        self.source._on_event(object())
        self.assertEqual(self.source.snapshot(), [])

    def test_bus_rejects_unbounded_payload_before_any_row(self):
        with self.assertRaises(HostEventError):
            self.source.emit("app.catalog.changed", {"item_count": 10 ** 13})
        self.assertEqual(self.source.snapshot(), [])

    def test_existing_rows_survive_a_rejected_event(self):
        self.source.emit("session.state.changed", {"state": "active"})
        self.source.emit("session.state.changed", {"state": "bad\u202e"})
        self.assertEqual(len(self.source.snapshot()), 1)
        self.assertIn("state=active", self.source.snapshot()[0]["body"])


class ContractAlignmentTests(unittest.TestCase):
    def test_adapter_topics_are_exactly_the_qml_and_host_contract(self):
        self.assertEqual(list(ALLOWED_TOPICS), sorted(HOST_EVENT_TOPICS))
        self.assertEqual(set(ALLOWED_TOPICS), set(_qml_topics()))
        self.assertEqual(SOURCE, "host-events")
        self.assertIn('readonly property string hostEventSource: "host-events"', QML)

    def test_records_fit_the_qml_validation_bounds(self):
        source = TrustedHostEventSource()
        try:
            source.emit("capabilities.report", {
                "status": "CAPABILITY_REPORT", "component_count": 8})
            source.emit("window.state.changed", {"window_count": 2})
            for record in source.snapshot():
                with self.subTest(record=record):
                    self.assertEqual(set(record), {
                        "id", "title", "body", "source", "topic"})
                    self.assertLessEqual(len(record["id"].encode("utf-8")), 64)
                    self.assertLessEqual(len(record["title"].encode("utf-8")), 120)
                    self.assertLessEqual(len(record["body"].encode("utf-8")), 280)
                    self.assertIn(record["topic"], HOST_EVENT_TOPICS)
                    self.assertEqual(record["source"], SOURCE)
                    for char in "".join(record.values()):
                        self.assertGreaterEqual(ord(char), 32)
                        self.assertNotEqual(ord(char), 127)
        finally:
            source.close()

    def test_adapter_imports_no_transport_or_execution_module(self):
        source_path = ROOT / "canopy_features" / "notifications" / "host_event_source.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported.issubset({"collections", "dataclasses",
                                           "unicodedata", "canopy_core"}), imported)
        for forbidden in ("subprocess", "socket", "threading", "asyncio",
                          "PySide6", "PyQt5", "dbus"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, imported)


if __name__ == "__main__":
    unittest.main()
