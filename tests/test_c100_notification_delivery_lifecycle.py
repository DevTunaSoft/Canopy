"""Synthetic contract tests for notification delivery/lifecycle at the source boundary.

Every positive case uses a real ``HostEvent`` delivered by the trusted
in-process bus. No test opens a socket, starts a daemon, touches Qt or claims
a live desktop notification. Run:

    python -m unittest tests.test_c100_notification_delivery_lifecycle -v
"""
import ast
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from canopy_features.notifications.delivery_lifecycle import (
    AVAILABLE,
    CLOSED,
    DUPLICATE,
    INVALID_PAYLOAD,
    INVALID_QUEUE_RECORD,
    MAX_CAPACITY,
    NONE,
    QUEUED,
    REJECTED,
    SOURCE_LOST,
    UNAVAILABLE,
    NotificationLifecycleError,
    NotificationDeliveryLifecycle,
)
from canopy_features.notifications.host_event_source import TrustedHostEventSource
from canopy_features.notifications.host_snapshot_producer import (
    HostSnapshot,
    HostSnapshotProducer,
)

MODULE_PATH = (Path(__file__).resolve().parents[1] /
               "canopy_features" / "notifications" / "delivery_lifecycle.py")


class ConstructionTests(unittest.TestCase):
    def test_default_starts_available_with_no_rows(self):
        lifecycle = NotificationDeliveryLifecycle()
        self.addCleanup(lifecycle.close)
        status = lifecycle.status()
        self.assertEqual((status.status, status.reason, status.refusal),
                         (AVAILABLE, NONE, None))
        self.assertEqual(status.pending_count, 0)
        self.assertEqual(lifecycle.snapshot(), ())
        self.assertIsNone(lifecycle.take())

    def test_invalid_capacity_fails_closed(self):
        for bad in (0, MAX_CAPACITY + 1, True, 1.0, "3", None, [], {}):
            with self.subTest(capacity=bad):
                with self.assertRaises(NotificationLifecycleError):
                    NotificationDeliveryLifecycle(capacity=bad)

    def test_invalid_producer_fails_closed(self):
        source = TrustedHostEventSource()
        self.addCleanup(source.close)
        for bad in (object(), source, "host-events", 7, [], {}):
            with self.subTest(producer=bad):
                with self.assertRaises(NotificationLifecycleError):
                    NotificationDeliveryLifecycle(producer=bad)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.lifecycle = NotificationDeliveryLifecycle(capacity=3)
        self.addCleanup(self.lifecycle.close)

    def test_real_event_is_queued_once_and_take_is_fifo(self):
        first = self.lifecycle.deliver(
            "app.catalog.changed", {"item_count": 1})
        second = self.lifecycle.deliver(
            "app.catalog.changed", {"item_count": 2})
        self.assertEqual((first.status, second.status), (QUEUED, QUEUED))
        self.assertEqual(self.lifecycle.status().pending_count, 2)
        taken = self.lifecycle.take()
        self.assertEqual(taken["body"], "item_count=1")
        self.assertEqual(self.lifecycle.take()["body"], "item_count=2")
        self.assertIsNone(self.lifecycle.take())
        self.assertEqual(self.lifecycle.status().delivered_count, 2)

    def test_bounded_queue_drops_oldest_and_counts_it(self):
        for count in range(1, 6):
            outcome = self.lifecycle.deliver(
                "app.catalog.changed", {"item_count": count})
            self.assertEqual(outcome.status, QUEUED)
        state = self.lifecycle.status()
        self.assertEqual(state.pending_count, 3)
        self.assertEqual(state.dropped_count, 2)
        self.assertEqual(state.queued_count, 5)
        bodies = [row["body"] for row in self.lifecycle.snapshot()]
        self.assertEqual(bodies, ["item_count=5", "item_count=4",
                                  "item_count=3"])

    def test_repeated_real_events_keep_distinct_ids(self):
        self.lifecycle.deliver("app.catalog.changed", {"item_count": 7})
        self.lifecycle.deliver("app.catalog.changed", {"item_count": 7})
        ids = [row["id"] for row in self.lifecycle.snapshot()]
        self.assertEqual(len(ids), 2)
        self.assertNotEqual(ids[0], ids[1])
        self.assertEqual(self.lifecycle.status().duplicate_count, 0)

    def test_payload_without_projected_field_is_rejected(self):
        outcome = self.lifecycle.deliver(
            "session.state.changed", {"unrelated": "SECRET_MARKER"})
        self.assertEqual(outcome.status, REJECTED)
        self.assertEqual(outcome.refusal, INVALID_PAYLOAD)
        self.assertEqual(self.lifecycle.snapshot(), ())
        state = self.lifecycle.status()
        self.assertEqual(state.rejected_count, 1)
        self.assertEqual(state.pending_count, 0)
        self.assertNotIn("SECRET_MARKER", json.dumps(state.as_dict()))

    def test_malformed_payloads_fail_closed_without_leaking_text(self):
        cases = (
            ("window.state.changed", None),
            ("window.state.changed", ["window_count=SECRET_MARKER"]),
            ("window.state.changed", "window_count=4"),
            ("wifi.scan.changed", {"state": "active"}),
            ("session.state.changed", {"nested": {"value": 1}}),
            ("session.state.changed", {"access_token": "SECRET_MARKER"}),
        )
        for topic, payload in cases:
            with self.subTest(topic=topic, payload=type(payload).__name__):
                outcome = self.lifecycle.deliver(topic, payload)
                self.assertEqual(outcome.status, REJECTED)
                self.assertEqual(outcome.refusal, INVALID_PAYLOAD)
                self.assertEqual(self.lifecycle.snapshot(), ())
                self.assertNotIn(
                    "SECRET_MARKER",
                    json.dumps(self.lifecycle.status().as_dict()))
        self.assertEqual(self.lifecycle.status().rejected_count, len(cases))

    def test_rejection_does_not_mutate_queue_and_recovers(self):
        self.lifecycle.deliver("session.state.changed", {"state": "idle"})
        before = self.lifecycle.snapshot()
        self.lifecycle.deliver("capabilities.report", {"unrelated": 1})
        self.assertEqual(self.lifecycle.snapshot(), before)
        state = self.lifecycle.status()
        self.assertEqual((state.pending_count, state.rejected_count), (1, 1))
        good = self.lifecycle.deliver(
            "session.state.changed", {"state": "active"})
        self.assertEqual(good.status, QUEUED)
        self.assertEqual(self.lifecycle.status().refusal, None)
        self.assertEqual(len(self.lifecycle.snapshot()), 2)

    def test_hostile_snapshot_record_is_rejected_without_partial_rows(self):
        self.lifecycle.deliver("session.state.changed", {"state": "idle"})
        hostile = {
            "id": "host-events:session.state.changed:99",
            "title": "Session state updated",
            "body": "state=ok\nhidden SECRET_MARKER",
            "source": "host-events",
            "topic": "session.state.changed",
        }
        with patch.object(
                self.lifecycle._producer, "snapshot",
                side_effect=[HostSnapshot("host-events", ()),
                             HostSnapshot("host-events", (hostile,))]):
            outcome = self.lifecycle.deliver(
                "session.state.changed", {"state": "active"})
        self.assertEqual(outcome.status, REJECTED)
        self.assertEqual(outcome.refusal, INVALID_QUEUE_RECORD)
        self.assertEqual(self.lifecycle.status().reason, "invalid_snapshot")
        self.assertEqual(self.lifecycle.snapshot(), ())
        self.assertNotIn(
            "SECRET_MARKER", json.dumps(self.lifecycle.status().as_dict()))

    def test_replayed_snapshot_ids_are_not_enqueued_twice(self):
        first = self.lifecycle.deliver(
            "session.state.changed", {"state": "idle"})
        previous = HostSnapshot("host-events", ({
            "id": first.id,
            "title": "Session state updated",
            "body": "state=idle",
            "source": "host-events",
            "topic": "session.state.changed",
        },))
        with patch.object(self.lifecycle._producer, "snapshot",
                          return_value=previous):
            replay = self.lifecycle.deliver(
                "session.state.changed", {"state": "active"})
        self.assertEqual(replay.status, REJECTED)
        self.assertEqual(replay.refusal, INVALID_PAYLOAD)
        rows = self.lifecycle.snapshot()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["body"], "state=idle")
        self.assertEqual(self.lifecycle.status().queued_count, 1)

    def test_duplicate_id_is_counted_without_a_second_row(self):
        self.lifecycle.deliver("session.state.changed", {"state": "idle"})
        known_id = "host-events:session.state.changed:99"
        self.lifecycle._seen_set.add(known_id)
        record = HostSnapshot("host-events", ({
            "id": known_id,
            "title": "Session state updated",
            "body": "state=replayed",
            "source": "host-events",
            "topic": "session.state.changed",
        },)).records[0]
        outcome = self.lifecycle._enqueue(record)
        self.assertEqual(outcome, DUPLICATE)
        self.assertEqual(self.lifecycle.status().duplicate_count, 1)
        rows = self.lifecycle.snapshot()
        self.assertEqual(len(rows), 1)
        self.assertNotIn(known_id, [row["id"] for row in rows])

    def test_snapshot_is_newest_first_and_cannot_mutate_queue(self):
        self.lifecycle.deliver("app.catalog.changed", {"item_count": 1})
        self.lifecycle.deliver("app.catalog.changed", {"item_count": 2})
        rows = self.lifecycle.snapshot()
        self.assertEqual([row["body"] for row in rows],
                         ["item_count=2", "item_count=1"])
        rows[0]["body"] = "tampered"
        self.assertEqual([row["body"] for row in self.lifecycle.snapshot()],
                         ["item_count=2", "item_count=1"])


class LifecycleTests(unittest.TestCase):
    def test_close_is_explicit_unavailable_and_idempotent(self):
        lifecycle = NotificationDeliveryLifecycle()
        lifecycle.deliver("session.state.changed", {"state": "idle"})
        lifecycle.close()
        lifecycle.close()
        state = lifecycle.status()
        self.assertEqual((state.status, state.reason, state.pending_count),
                         (UNAVAILABLE, CLOSED, 0))
        self.assertEqual(lifecycle.snapshot(), ())
        self.assertIsNone(lifecycle.take())
        with self.assertRaises(NotificationLifecycleError):
            lifecycle.deliver("session.state.changed", {"state": "active"})
        self.assertEqual(state.rejected_count, 0)

    def test_injected_producer_is_not_closed_by_the_lifecycle(self):
        producer = HostSnapshotProducer()
        self.addCleanup(producer.close)
        lifecycle = NotificationDeliveryLifecycle(producer=producer)
        lifecycle.close()
        self.assertTrue(producer.connected())

    def test_source_loss_is_unavailable_with_zero_rows(self):
        producer = HostSnapshotProducer()
        lifecycle = NotificationDeliveryLifecycle(producer=producer)
        self.addCleanup(lifecycle.close)
        lifecycle.deliver("session.state.changed", {"state": "idle"})
        producer.close()
        state = lifecycle.status()
        self.assertEqual((state.status, state.reason, state.pending_count),
                         (UNAVAILABLE, SOURCE_LOST, 0))
        self.assertEqual(lifecycle.snapshot(), ())
        self.assertIsNone(lifecycle.take())

    def test_status_is_frozen(self):
        lifecycle = NotificationDeliveryLifecycle()
        self.addCleanup(lifecycle.close)
        state = lifecycle.status()
        with self.assertRaises(FrozenInstanceError):
            state.status = UNAVAILABLE


class SourceIntegrityTests(unittest.TestCase):
    def test_no_transport_or_execution_imports(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        forbidden = {"os", "sys", "socket", "subprocess", "threading", "time",
                     "pathlib", "shutil", "tempfile", "asyncio", "dbus", "gi"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & forbidden)
        self.assertTrue({"collections", "dataclasses"} <= imported)

    def test_no_new_topic_or_side_effect_literals(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for banned in ("app.catalog.changed", "window.state.changed",
                       "session.state.changed", "capabilities.report",
                       ".notify-send", "gdbus", "notify_send"):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
