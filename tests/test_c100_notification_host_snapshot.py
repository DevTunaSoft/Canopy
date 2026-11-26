"""Synthetic contract tests for the notification host snapshot producer.

The producer is pure in-process code: every row must come from a real
``HostEvent`` delivered by the trusted ``TrustedHostEventSource``. No test
fabricates a ``HostEvent``, opens a file, starts a daemon or claims a live
notification delivery. Run:

    python -m unittest tests.test_c100_notification_host_snapshot -v
"""
import json
import unittest
from collections.abc import Mapping
from dataclasses import FrozenInstanceError

from canopy_core.host_events import TOPICS as HOST_EVENT_TOPICS

from canopy_features.notifications.host_snapshot_producer import (
    ALLOWED_TOPICS,
    MAX_RECORDS,
    SOURCE,
    HostSnapshotProducer,
    SnapshotProducerError,
    compose,
)


class RealEventTests(unittest.TestCase):
    def setUp(self):
        self.producer = HostSnapshotProducer()
        self.addCleanup(self.producer.close)

    def test_default_snapshot_has_no_rows(self):
        snapshot = self.producer.snapshot()
        self.assertEqual(snapshot.as_dict(), {"source": SOURCE, "records": []})
        self.assertEqual(snapshot.records, ())
        self.assertEqual(self.producer.to_json_bytes(),
                         b'{"records":[],"source":"host-events"}')

    def test_real_host_event_produces_one_bounded_record(self):
        result = self.producer.publish("app.catalog.changed", {"item_count": 3})
        snapshot = self.producer.snapshot()
        self.assertEqual(len(snapshot.records), 1)
        record = snapshot.records[0].as_dict()
        self.assertEqual(set(record),
                         {"id", "title", "body", "source", "topic"})
        self.assertEqual(record["id"],
                         "host-events:app.catalog.changed:%d" % result.event.sequence)
        self.assertEqual(record["source"], SOURCE)
        self.assertEqual(record["topic"], "app.catalog.changed")
        self.assertIn("item_count=3", record["body"])

    def test_records_keep_newest_first_order(self):
        for index in range(3):
            self.producer.publish("session.state.changed", {"state": "s%d" % index})
        bodies = [record.body for record in self.producer.snapshot().records]
        self.assertEqual(bodies, ["state=s2", "state=s1", "state=s0"])

    def test_snapshot_is_frozen_and_json_round_trips(self):
        self.producer.publish("window.state.changed", {"window_count": 2})
        snapshot = self.producer.snapshot()
        with self.assertRaises(FrozenInstanceError):
            snapshot.source = "other"
        with self.assertRaises(FrozenInstanceError):
            snapshot.records[0].body = "changed"
        wire = json.loads(snapshot.to_json_bytes())
        self.assertEqual(wire, snapshot.as_dict())
        wire["records"][0]["body"] = "changed"
        self.assertEqual(snapshot.records[0].body, "window_count=2")

    def test_contract_surface_matches_the_four_approved_topics(self):
        self.assertEqual(ALLOWED_TOPICS, tuple(sorted(HOST_EVENT_TOPICS)))
        self.assertEqual(len(ALLOWED_TOPICS), 4)
        self.assertEqual(self.producer.source(), SOURCE)
        self.assertEqual(self.producer.allowedTopics(), list(ALLOWED_TOPICS))
        self.assertTrue(self.producer.connected())

    def test_compose_accepts_synthetic_records_from_the_trusted_shape(self):
        records = [{"id": "host-events:capabilities.report:1",
                    "title": "Host capability report", "body": "status=ok",
                    "source": SOURCE, "topic": "capabilities.report"}]
        snapshot = compose(records)
        self.assertEqual(snapshot.records[0].as_dict(), records[0])
        self.assertEqual(len(snapshot.records), 1)


def _record(**overrides):
    """Synthetic snapshot record in the trusted source's projected shape."""
    base = {"id": "host-events:capabilities.report:1",
            "title": "Host capability report", "body": "status=ok",
            "source": SOURCE, "topic": "capabilities.report"}
    base.update(overrides)
    return base


class _UnhashableKeyMapping(Mapping):
    """Synthetic Mapping that iterates one unhashable key during key-set checks."""

    def __init__(self, values):
        self._values = values

    def __iter__(self):
        yield []
        yield from self._values

    def __len__(self):
        return len(self._values) + 1

    def __getitem__(self, key):
        return self._values[key]


class _RaisingMapping(Mapping):
    """Synthetic Mapping whose lookup raises a secret-bearing built-in error."""

    def __init__(self, values):
        self._values = values

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __getitem__(self, key):
        raise RuntimeError("hostile lookup SECRET_MARKER")


class HostileRecordTests(unittest.TestCase):
    def test_unapproved_topic_is_rejected(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record(topic="wifi.scan.changed")])

    def test_foreign_source_is_rejected(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record(source="dbus")])

    def test_control_character_in_body_is_rejected(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record(body="status=ok\nhidden")])

    def test_bidirectional_override_in_title_is_rejected(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record(title="\u202ereport")])

    def test_non_string_record_field_is_rejected(self):
        for bad in (7, True, None, [], {}):
            with self.subTest(bad=bad), self.assertRaises(SnapshotProducerError):
                compose([_record(body=bad)])

    def test_extra_record_key_is_rejected(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record(extra="unapproved")])

    def test_unhashable_mapping_key_is_rejected_with_domain_error(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_UnhashableKeyMapping(_record())])

    def test_hostile_mapping_lookup_leaks_no_builtin_or_secret(self):
        with self.assertRaises(SnapshotProducerError) as caught:
            compose([_RaisingMapping(_record())])
        self.assertNotIn("SECRET_MARKER", str(caught.exception))

    def test_surrogate_in_record_field_is_rejected_with_domain_error(self):
        with self.assertRaises(SnapshotProducerError) as caught:
            compose([_record(title="\ud800hidden")])
        self.assertNotIn("hidden", str(caught.exception))

    def test_missing_record_key_is_rejected(self):
        record = _record()
        del record["topic"]
        with self.assertRaises(SnapshotProducerError):
            compose([record])

    def test_unexpected_record_collection_type_is_rejected(self):
        for bad in (None, 7, "x", b"x", {"id": "x"}, frozenset({"x"}), True):
            with self.subTest(bad=bad), self.assertRaises(SnapshotProducerError):
                compose(bad)

    def test_non_mapping_record_entry_is_rejected(self):
        for bad in (None, "x", 7, ["x"], True):
            with self.subTest(bad=bad), self.assertRaises(SnapshotProducerError):
                compose([bad])

    def test_bad_later_record_rejects_the_whole_input(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record(), _record(id="other", source="dbus")])


class OversizedRecordTests(unittest.TestCase):
    def test_thirteenth_record_is_rejected(self):
        records = [_record(id="id-%02d" % index)
                   for index in range(MAX_RECORDS + 1)]
        with self.assertRaises(SnapshotProducerError):
            compose(records)

    def test_id_over_64_bytes_is_rejected(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record(id="x" * 65)])

    def test_title_over_120_bytes_is_rejected(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record(title="x" * 121)])

    def test_body_over_280_bytes_is_rejected(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record(body="x" * 281)])

    def test_field_bounds_count_utf8_bytes(self):
        self.assertEqual(len(compose([_record(title="\u00e9" * 60)]).records), 1)
        with self.assertRaises(SnapshotProducerError):
            compose([_record(title="\u00e9" * 61)])

    def test_json_byte_cap_is_rejected(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record()], max_bytes=1)

    def test_invalid_capacity_argument_is_rejected(self):
        for bad in (0, -1, MAX_RECORDS + 1, True, 2.0, "2", None):
            with self.subTest(bad=bad), self.assertRaises(SnapshotProducerError):
                compose([], max_records=bad)


class DuplicateEventTests(unittest.TestCase):
    def test_duplicate_ids_reject_the_whole_snapshot(self):
        with self.assertRaises(SnapshotProducerError):
            compose([_record(), _record()])

    def test_repeated_real_events_keep_distinct_sequence_ids(self):
        producer = HostSnapshotProducer()
        try:
            for _ in range(2):
                producer.publish("session.state.changed", {"state": "same"})
            ids = [record.id for record in producer.snapshot().records]
            self.assertEqual(len(ids), 2)
            self.assertNotEqual(ids[0], ids[1])
        finally:
            producer.close()


class FailClosedTests(unittest.TestCase):
    def test_corrupted_source_snapshot_yields_empty_rows(self):
        from unittest.mock import patch

        producer = HostSnapshotProducer()
        try:
            producer.publish("session.state.changed", {"state": "valid"})
            self.assertEqual(len(producer.snapshot().records), 1)
            with patch.object(producer._source, "snapshot",
                              return_value=[_record(topic="unknown.topic")]):
                self.assertEqual(producer.snapshot().records, ())
                self.assertEqual(producer.as_dict(),
                                 {"source": SOURCE, "records": []})
            self.assertIsNotNone(producer.refusal)
            self.assertEqual(len(producer.snapshot().records), 1)
            self.assertIsNone(producer.refusal)
        finally:
            producer.close()

    def test_unhashable_mapping_key_snapshot_fails_closed(self):
        from unittest.mock import patch

        producer = HostSnapshotProducer()
        try:
            producer.publish("session.state.changed", {"state": "valid"})
            self.assertEqual(len(producer.snapshot().records), 1)
            with patch.object(producer._source, "snapshot",
                              return_value=[_UnhashableKeyMapping(_record())]):
                self.assertEqual(producer.snapshot().records, ())
                self.assertEqual(producer.refusal, "INVALID_SNAPSHOT_RECORD")
            self.assertEqual(len(producer.snapshot().records), 1)
            self.assertIsNone(producer.refusal)
        finally:
            producer.close()

    def test_source_exception_snapshot_fails_closed_without_echo(self):
        from unittest.mock import patch

        producer = HostSnapshotProducer()
        try:
            producer.publish("session.state.changed", {"state": "valid"})
            self.assertEqual(len(producer.snapshot().records), 1)
            with patch.object(producer._source, "snapshot",
                              side_effect=RuntimeError("SECRET_MARKER")):
                self.assertEqual(producer.snapshot().records, ())
                self.assertEqual(producer.refusal, "INVALID_SNAPSHOT_RECORD")
            self.assertEqual(len(producer.snapshot().records), 1)
            self.assertIsNone(producer.refusal)
        finally:
            producer.close()


class BoundaryTests(unittest.TestCase):
    def test_publish_translates_host_bus_rejection_to_domain_error(self):
        producer = HostSnapshotProducer()
        try:
            with self.assertRaises(SnapshotProducerError):
                producer.publish("wifi.scan.changed", {"state": "x"})
            with self.assertRaises(SnapshotProducerError):
                producer.publish("app.catalog.changed", {"item_count": 10 ** 13})
            self.assertEqual(producer.snapshot().records, ())
            producer.publish("session.state.changed", {"state": "valid"})
            self.assertEqual(len(producer.snapshot().records), 1)
        finally:
            producer.close()

    def test_exported_bounds_are_part_of_the_public_contract(self):
        module = __import__("canopy_features.notifications.host_snapshot_producer",
                            fromlist=["__all__"])
        for name in ("MAX_RECORDS", "MAX_JSON_BYTES", "MAX_ID_BYTES",
                     "MAX_TITLE_BYTES", "MAX_BODY_BYTES", "RECORD_KEYS"):
            with self.subTest(name=name):
                self.assertIn(name, module.__all__)
        self.assertEqual(module.MAX_JSON_BYTES, 65_536)
        self.assertEqual(module.MAX_RECORDS, 12)

    def test_invalid_constructor_arguments_are_rejected(self):
        for kwargs in ({"max_records": 0}, {"max_records": 13},
                       {"max_records": True}, {"max_records": "3"},
                       {"max_bytes": 0}, {"max_bytes": 65_537},
                       {"max_bytes": 1.0}, {"source": object()},
                       {"source": {"connected": lambda: True}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SnapshotProducerError):
                HostSnapshotProducer(**kwargs)

    def test_injected_source_is_not_closed_by_the_producer(self):
        from canopy_features.notifications.host_event_source import (
            TrustedHostEventSource,
        )

        source = TrustedHostEventSource()
        try:
            producer = HostSnapshotProducer(source=source)
            producer.close()
            self.assertTrue(source.connected())
        finally:
            source.close()

    def test_close_fails_closed(self):
        producer = HostSnapshotProducer()
        producer.publish("session.state.changed", {"state": "valid"})
        producer.close()
        producer.close()
        self.assertFalse(producer.connected())
        self.assertEqual(producer.snapshot().records, ())
        with self.assertRaises(SnapshotProducerError):
            producer.publish("session.state.changed", {"state": "valid"})

    def test_source_module_imports_no_transport_or_execution_module(self):
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        path = root / "canopy_features" / "notifications" / "host_snapshot_producer.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported.issubset({"collections", "dataclasses", "json",
                                           "unicodedata", "canopy_core",
                                           "canopy_features"}), imported)
        for forbidden in ("subprocess", "socket", "threading", "asyncio",
                          "PySide6", "PyQt5", "dbus", "os", "pathlib", "time"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, imported)

    def test_no_new_topic_literal_and_no_io_in_source(self):
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        path = root / "canopy_features" / "notifications" / "host_snapshot_producer.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        literals = {node.value for node in ast.walk(tree)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        topic_literals = {value for value in literals
                          if value.count(".") >= 2 and value.replace(".", "").isalnum()}
        self.assertTrue(topic_literals.issubset(set(ALLOWED_TOPICS)), topic_literals)
        called = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertFalse(called & {"open", "exec", "eval", "compile", "input"})

    def test_record_bounds_match_the_classic_notification_centre(self):
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        qml = (root / "prototype" / "classic" / "NotificationCenter.qml").read_text(
            encoding="utf-8")
        topics = re.search(r"contractTopics:\s*\[(.*?)\]", qml, re.DOTALL)
        self.assertIsNotNone(topics)
        self.assertEqual(set(json.loads("[" + topics.group(1) + "]")),
                         set(ALLOWED_TOPICS))
        self.assertEqual(ALLOWED_TOPICS, tuple(sorted(ALLOWED_TOPICS)))
        self.assertIn("record.id.length > 64", qml)
        self.assertIn("record.title.length > 120", qml)
        self.assertIn("record.body.length > 280", qml)


if __name__ == "__main__":
    unittest.main()
