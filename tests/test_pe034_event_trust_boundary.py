"""PE-034: untrusted and oversized host events stop before shell state.

These are pure, in-process negative-control tests. They do not claim a Qt
bridge, live desktop events, Mint acceptance or owner visual approval.
"""
import math
import unittest

from canopy_core.event_trust import (
    MAX_BATCH,
    MAX_EVENT_BYTES,
    MAX_PENDING,
    EventTrustBoundary,
    EventTrustError,
    SourceGrant,
)
from canopy_core.host_events import PROTOCOL_VERSION, TOPICS


class _AlwaysEqual:
    """Hostile source object: equality/hash must never be consulted."""

    def __eq__(self, other):
        raise AssertionError("source equality must not be called")

    def __hash__(self):
        raise AssertionError("source hashing must not be called")


class EventTrustBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.host = object()
        self.helper = object()
        self.grants = (
            SourceGrant(self.host, frozenset({
                "app.catalog.changed", "session.state.changed"})),
            SourceGrant(self.helper, frozenset({"window.state.changed"})),
        )

    def test_accepted_events_queue_once_and_drain_in_sequence_order(self):
        boundary = EventTrustBoundary(self.grants)
        first = boundary.ingest(self.host, "app.catalog.changed",
                                {"item_count": 4, "available": True})
        second = boundary.ingest(self.helper, "window.state.changed",
                                 {"window_count": 2})
        self.assertEqual((first, second), (1, 2))
        self.assertEqual(boundary.pending, 2)
        drained = boundary.drain()
        self.assertEqual([e.sequence for e in drained], [1, 2])
        self.assertEqual([e.topic for e in drained],
                         ["app.catalog.changed", "window.state.changed"])
        self.assertTrue(all(e.version == PROTOCOL_VERSION for e in drained))
        self.assertEqual(dict(drained[0].payload),
                         {"available": True, "item_count": 4})
        with self.assertRaises(TypeError):
            drained[0].payload["item_count"] = 99
        self.assertEqual(boundary.pending, 0)
        self.assertEqual(boundary.drain(), ())
        self.assertEqual(boundary.rejection_count, 0)

    def test_untrusted_source_identity_is_refused_without_state_change(self):
        boundary = EventTrustBoundary(self.grants)
        for index, hostile in enumerate(
                (object(), _AlwaysEqual(), "host", None, True), start=1):
            with self.subTest(hostile=type(hostile).__name__):
                with self.assertRaises(EventTrustError):
                    boundary.ingest(hostile, "app.catalog.changed",
                                    {"item_count": 1})
                self.assertEqual(boundary.last_rejection, "UNTRUSTED_SOURCE")
                self.assertEqual((boundary.pending, boundary.rejection_count),
                                 (0, index))

    def test_topic_outside_grant_is_refused_without_state_change(self):
        boundary = EventTrustBoundary(self.grants)
        for topic in ("capabilities.report", "window.state.changed",
                      "app.catalog.changed.echo", "", None, 7):
            with self.subTest(topic=topic):
                with self.assertRaises(EventTrustError):
                    boundary.ingest(self.host, topic, {"count": 1})
                self.assertEqual(boundary.last_rejection, "UNSUPPORTED_TOPIC")
                self.assertEqual(boundary.pending, 0)
        self.assertEqual(boundary.rejection_count, 6)

    def test_oversized_payloads_are_refused_before_queueing(self):
        boundary = EventTrustBoundary(self.grants)
        oversized = (
            {str(i): i for i in range(9)},
            {"title": "x" * 513},
            {("long_" + "a" * 70): 1},
            {("field_" + str(i)): "x" * 500 for i in range(8)},
        )
        for index, payload in enumerate(oversized, start=1):
            with self.subTest(fields=len(payload)):
                with self.assertRaises(EventTrustError):
                    boundary.ingest(self.host, "session.state.changed", payload)
                self.assertEqual((boundary.pending, boundary.rejection_count),
                                 (0, index))
        self.assertIn(boundary.last_rejection,
                      ("INVALID_PAYLOAD", "OVERSIZED_EVENT"))
        self.assertEqual(boundary.drain(), ())
        boundary = EventTrustBoundary(self.grants)
        with self.assertRaises(EventTrustError):
            boundary.ingest(self.host, "session.state.changed",
                            {("field_" + str(i)): "x" * 500 for i in range(8)})
        self.assertEqual(boundary.last_rejection, "OVERSIZED_EVENT")

    def test_hostile_values_fail_closed_with_fixed_reason_codes(self):
        boundary = EventTrustBoundary(self.grants)
        hostile = (
            {"token": "x"}, {"user_password": "x"}, {"__proto__": 1},
            {"nested": {"a": 1}}, {"items": [1]}, {"blob": b"bytes"},
            {"rate": float("nan")}, {"rate": math.inf}, {"title": "\ud800"},
        )
        for payload in hostile:
            with self.subTest(payload=tuple(payload)):
                with self.assertRaises(EventTrustError):
                    boundary.ingest(self.host, "session.state.changed", payload)
                self.assertEqual(boundary.last_rejection, "INVALID_PAYLOAD")
                self.assertEqual(boundary.pending, 0)
        for payload in (None, [], "text", 7, True):
            with self.subTest(payload=repr(payload)):
                with self.assertRaises(EventTrustError):
                    boundary.ingest(self.host, "session.state.changed", payload)
                self.assertEqual(boundary.last_rejection, "INVALID_PAYLOAD")
        self.assertEqual(boundary.rejection_count, len(hostile) + 5)

    def test_queue_capacity_refuses_overflow_without_evicting(self):
        boundary = EventTrustBoundary(self.grants, max_pending=3)
        for sequence in range(1, 4):
            boundary.ingest(self.host, "session.state.changed",
                            {"sequence": sequence})
        with self.assertRaises(EventTrustError):
            boundary.ingest(self.host, "session.state.changed",
                            {"sequence": 4})
        self.assertEqual(boundary.last_rejection, "QUEUE_FULL")
        self.assertEqual(boundary.pending, 3)
        drained = boundary.drain()
        self.assertEqual([e.fields[0][1] for e in drained], [1, 2, 3])
        self.assertEqual(boundary.drain(), ())

    def test_drain_limit_is_bounded_and_wrong_types_are_refused(self):
        boundary = EventTrustBoundary(self.grants, max_batch=2)
        for sequence in range(1, 5):
            boundary.ingest(self.host, "session.state.changed",
                            {"sequence": sequence})
        for limit in (0, -1, True, 3, 2.0, "2", _AlwaysEqual()):
            with self.subTest(limit=type(limit).__name__):
                with self.assertRaises(EventTrustError):
                    boundary.drain(limit)
                self.assertEqual(boundary.pending, 4)
        self.assertEqual([e.sequence for e in boundary.drain(2)], [1, 2])
        self.assertEqual([e.sequence for e in boundary.drain()], [3, 4])

    def test_close_clears_pending_events_and_refuses_every_operation(self):
        boundary = EventTrustBoundary(self.grants)
        boundary.ingest(self.host, "session.state.changed", {"count": 1})
        boundary.close()
        boundary.close()
        self.assertEqual(boundary.pending, 0)
        with self.assertRaises(EventTrustError):
            boundary.drain()
        self.assertEqual(boundary.last_rejection, "CLOSED")
        with self.assertRaises(EventTrustError):
            boundary.ingest(self.host, "session.state.changed", {"count": 2})
        self.assertEqual(boundary.last_rejection, "CLOSED")

    def test_rejected_events_never_reach_shell_state(self):
        shell_state = []
        boundary = EventTrustBoundary(self.grants)
        hostile = (
            (object(), "session.state.changed", {"state": "active"}),
            (self.host, "capabilities.report", {"status": "APPROVED"}),
            (self.host, "session.state.changed", {"token": "secret"}),
            (self.host, "session.state.changed", {"state": "x" * 600}),
        )
        for source, topic, payload in hostile:
            with self.assertRaises(EventTrustError):
                boundary.ingest(source, topic, payload)
        boundary.ingest(self.host, "session.state.changed",
                        {"state": "active"})
        for event in boundary.drain():
            shell_state.append(dict(event.payload))
        self.assertEqual(shell_state, [{"state": "active"}])
        self.assertEqual(boundary.rejection_count, len(hostile))

    def test_grants_cannot_extend_the_documented_v2_contract(self):
        boundary = EventTrustBoundary(self.grants)
        self.assertEqual(PROTOCOL_VERSION, 2)
        self.assertEqual(len(TOPICS), 4)
        with self.assertRaises(EventTrustError):
            EventTrustBoundary((SourceGrant(self.host, frozenset(
                {"session.state.changed.echo"})),))
        with self.assertRaises(EventTrustError):
            EventTrustBoundary((SourceGrant(self.host, frozenset())),)
        with self.assertRaises(EventTrustError):
            EventTrustBoundary((self.host,))
        boundary.ingest(self.host, "session.state.changed", {"count": 1})
        self.assertEqual(boundary.pending, 1)

    def test_module_bounds_stay_within_the_host_event_contract(self):
        self.assertTrue(1 <= MAX_PENDING <= 64)
        self.assertTrue(1 <= MAX_BATCH <= MAX_PENDING)
        self.assertTrue(1 <= MAX_EVENT_BYTES <= 8 * 512 + 8 * 48)


if __name__ == "__main__":
    unittest.main()
