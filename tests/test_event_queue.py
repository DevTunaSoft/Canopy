"""Inert bounded-queue unit tests; no live compositor or desktop claims."""
from pathlib import Path
import unittest

from canopy_core.event_queue import (
    DEFAULT_CAPACITY, DEFAULT_OVERFLOW, MAX_CAPACITY, MAX_SEQUENCE,
    OVERFLOW_POLICIES, PROTOCOL_VERSION, TOPICS, PublishResult, QueueClosed,
    QueueError, QueueOverflow, ShellEvent, ShellEventQueue, _encode_fields,
    validate_event,
)


class ShellEventQueueTests(unittest.TestCase):
    def test_fifo_order_monotonic_sequence_and_immutable_payload(self):
        q = ShellEventQueue()
        a = q.publish("app.catalog.changed", {"count": 4, "ready": True})
        b = q.publish("app.catalog.changed", {"count": 5})
        self.assertIsInstance(a, PublishResult)
        self.assertEqual((a.queued, a.evicted, b.event.sequence), (True, 0, 2))
        self.assertEqual([e.sequence for e in q.drain()], [1, 2])
        self.assertEqual(a.event.version, PROTOCOL_VERSION)
        with self.assertRaises(TypeError):
            a.event.payload["count"] = 10
        self.assertEqual(a.event.payload["count"], 4)
        self.assertTrue(q.is_empty)

    def test_no_thread_poll_timer_network_or_process_imports(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_core/event_queue.py").read_text()
        for banned in ("QTimer", "asyncio", "subprocess", "import socket",
                       "Thread(", "importlib", "time.sleep", "while True",
                       "multiprocessing", "import threading"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, code)

    def test_reject_overflow_preserves_oldest_and_does_not_advance_sequence(self):
        q = ShellEventQueue(capacity=2, overflow="reject")
        q.publish("window.state.changed", {"n": 1})
        q.publish("window.state.changed", {"n": 2})
        with self.assertRaises(QueueOverflow):
            q.publish("window.state.changed", {"n": 3})
        self.assertEqual(q.size, 2)
        self.assertEqual(q.sequence, 2)
        self.assertEqual(q.dropped, 0)
        self.assertEqual([e.payload["n"] for e in q.drain()], [1, 2])
        q.publish("window.state.changed", {"n": 4})
        self.assertEqual(q.peek().sequence, 3)

    def test_reject_overflow_with_full_queue_keeps_queued_events(self):
        q = ShellEventQueue(capacity=2, overflow="reject")
        q.publish("window.state.changed", {"n": 1})
        q.publish("window.state.changed", {"n": 2})
        with self.assertRaises(QueueOverflow):
            q.publish("window.state.changed", {"n": 3})
        self.assertEqual([e.payload["n"] for e in q.drain()], [1, 2])
        self.assertEqual(q.sequence, 2)

    def test_drop_oldest_evicts_oldest_and_counts_drops(self):
        q = ShellEventQueue(capacity=2, overflow="drop_oldest")
        q.publish("session.state.changed", {"n": 1})
        q.publish("session.state.changed", {"n": 2})
        third = q.publish("session.state.changed", {"n": 3})
        self.assertEqual((third.queued, third.evicted), (True, 1))
        self.assertEqual(q.size, 2)
        self.assertEqual(q.dropped, 1)
        self.assertEqual([e.payload["n"] for e in q.drain()], [2, 3])

    def test_drop_newest_refuses_incoming_and_counts_drops(self):
        q = ShellEventQueue(capacity=1, overflow="drop_newest")
        q.publish("session.state.changed", {"n": 1})
        rejected = q.publish("session.state.changed", {"n": 2})
        self.assertEqual((rejected.queued, rejected.evicted, rejected.event.sequence),
                         (False, 0, 0))
        self.assertEqual(q.size, 1)
        self.assertEqual(q.dropped, 1)
        self.assertEqual(q.sequence, 1)
        self.assertEqual([e.payload["n"] for e in q.drain()], [1])

    def test_invalid_events_do_not_mutate_queue_or_sequence(self):
        q = ShellEventQueue()
        bad = [
            ("unknown.topic", {}), ("", {}), (None, {}),
            ("app.catalog.changed", {"__proto__": 1}),
            ("app.catalog.changed", {"token": "x"}),
            ("app.catalog.changed", {"nested": []}),
            ("app.catalog.changed", {str(i): i for i in range(9)}),
            ("app.catalog.changed", {"x": float("nan")}),
        ]
        for topic, payload in bad:
            with self.subTest(topic=topic, payload=list(payload)[:1]):
                with self.assertRaises(QueueError):
                    q.publish(topic, payload)
        self.assertTrue(q.is_empty)
        self.assertEqual(q.sequence, 0)
        self.assertEqual(q.dropped, 0)

    def test_version_and_configuration_validation(self):
        for version in (0, True, 2, 100, "1", None):
            with self.subTest(version=version):
                with self.assertRaises(QueueError):
                    ShellEventQueue(version=version)
        for capacity in (0, -1, True, 1.5, MAX_CAPACITY + 1, "8"):
            with self.subTest(capacity=capacity):
                with self.assertRaises(QueueError):
                    ShellEventQueue(capacity=capacity)
        for overflow in ("drop", " newest", None, 1, [], "DROP_OLDEST"):
            with self.subTest(overflow=overflow):
                with self.assertRaises(QueueError):
                    ShellEventQueue(overflow=overflow)
        self.assertEqual(OVERFLOW_POLICIES,
                         frozenset({"reject", "drop_oldest", "drop_newest"}))
        self.assertEqual((DEFAULT_CAPACITY, DEFAULT_OVERFLOW), (64, "reject"))

    def test_publish_event_validates_prebuilt_event(self):
        q = ShellEventQueue()
        good = ShellEvent(PROTOCOL_VERSION, "app.catalog.changed", 99,
                          (("count", 7),))
        result = q.publish_event(good)
        self.assertTrue(result.queued)
        self.assertEqual(result.event.sequence, 1)
        bad_events = [
            ShellEvent(2, "app.catalog.changed", 1, ()),
            ShellEvent(PROTOCOL_VERSION, "unknown.topic", 1, ()),
            ShellEvent(PROTOCOL_VERSION, "app.catalog.changed", 0, ()),
            ShellEvent(PROTOCOL_VERSION, "app.catalog.changed", MAX_SEQUENCE + 1, ()),
            ShellEvent(PROTOCOL_VERSION, "app.catalog.changed", 1, (("bad key", 1),)),
            {"version": 1, "topic": "app.catalog.changed", "sequence": 1, "fields": ()},
            None,
        ]
        for event in bad_events:
            with self.subTest(event=repr(event)[:40]):
                with self.assertRaises(QueueError):
                    q.publish_event(event)
        self.assertEqual(q.size, 1)
        self.assertEqual(q.sequence, 1)

    def test_validate_event_and_encode_fields_accept_scalars(self):
        fields = _encode_fields({"title": "Caf\u00e9", "count": 12, "ready": True,
                                 "rate": 0.75, "nothing": None})
        self.assertEqual(dict(fields)["title"], "Caf\u00e9")
        self.assertEqual(fields, tuple(sorted(fields)))
        event = ShellEvent(PROTOCOL_VERSION, "window.state.changed", 5, fields)
        self.assertEqual(validate_event(event), fields)
        for value in (b"bytes", [], {}, object(), float("inf"), float("-inf"),
                      10 ** 30, "\ud800", "x" * 513):
            with self.subTest(value=repr(value)[:20]):
                with self.assertRaises(QueueError):
                    _encode_fields({"value": value})
        for name in ("cookie", "Password", "PRIVATE_KEY", "A", "a" * 49,
                     "1bad", "", "has-dash"):
            with self.subTest(name=name):
                with self.assertRaises(QueueError):
                    _encode_fields({name: 1})

    def test_drain_limit_pop_peek_and_clear(self):
        q = ShellEventQueue(capacity=4)
        for n in range(4):
            q.publish("session.state.changed", {"n": n})
        self.assertEqual([e.payload["n"] for e in q.drain(2)], [0, 1])
        self.assertEqual(q.size, 2)
        self.assertEqual(q.peek().payload["n"], 2)
        self.assertEqual(q.pop().payload["n"], 2)
        self.assertEqual(q.pop().payload["n"], 3)
        self.assertIsNone(q.pop())
        self.assertIsNone(q.peek())
        for n in range(2):
            q.publish("session.state.changed", {"n": n})
        q.clear()
        self.assertTrue(q.is_empty)
        self.assertEqual(q.sequence, 6)
        for limit in (-1, 1.5, True, "2"):
            with self.subTest(limit=limit):
                with self.assertRaises(QueueError):
                    q.drain(limit)

    def test_large_input_is_bounded_and_deterministic(self):
        total = 10000
        q = ShellEventQueue(capacity=16, overflow="drop_oldest")
        for n in range(total):
            q.publish("app.catalog.changed", {"n": n, "label": "item-%d" % n})
        self.assertEqual(q.size, 16)
        self.assertEqual(q.dropped, total - 16)
        self.assertEqual(q.sequence, total)
        drained = q.drain()
        self.assertEqual([e.payload["n"] for e in drained],
                         list(range(total - 16, total)))
        self.assertEqual([e.sequence for e in drained],
                         list(range(total - 16 + 1, total + 1)))

    def test_large_single_payload_at_bound_and_oversize_rejected(self):
        q = ShellEventQueue(capacity=1)
        value = "\u00e9" * 256
        self.assertTrue(q.publish("app.catalog.changed",
                                  {"title": value}).queued)
        self.assertEqual(q.pop().payload["title"], value)
        with self.assertRaises(QueueError):
            q.publish("app.catalog.changed", {"title": "\u00e9" * 257})
        self.assertTrue(q.is_empty)

    def test_reject_full_queue_does_not_accept_large_burst(self):
        q = ShellEventQueue(capacity=5, overflow="reject")
        accepted = 0
        for n in range(500):
            try:
                q.publish("window.state.changed", {"n": n})
                accepted += 1
            except QueueOverflow:
                pass
        self.assertEqual(accepted, 5)
        self.assertEqual(q.size, 5)
        self.assertEqual(q.dropped, 0)
        self.assertEqual(q.sequence, 5)

    def test_close_is_idempotent_and_releases_references(self):
        q = ShellEventQueue(capacity=2)
        q.publish("session.state.changed", {"n": 1})
        q.close()
        q.close()
        self.assertTrue(q.closed)
        self.assertTrue(q.is_empty)
        for action in (lambda: q.publish("session.state.changed", {}),
                       lambda: q.publish_event(ShellEvent(
                           PROTOCOL_VERSION, "session.state.changed", 1, ())),
                       q.drain, q.pop, q.peek, q.clear):
            with self.subTest(action=action):
                with self.assertRaises(QueueClosed):
                    action()

    def test_distinct_queues_have_independent_counters(self):
        first = ShellEventQueue(capacity=1, overflow="drop_oldest")
        second = ShellEventQueue(capacity=1, overflow="reject")
        first.publish("app.catalog.changed", {"n": 1})
        first.publish("app.catalog.changed", {"n": 2})
        second.publish("app.catalog.changed", {"n": 1})
        with self.assertRaises(QueueOverflow):
            second.publish("app.catalog.changed", {"n": 2})
        self.assertEqual((first.size, first.dropped, first.sequence), (1, 1, 2))
        self.assertEqual((second.size, second.dropped, second.sequence), (1, 0, 1))
        self.assertEqual(TOPICS, frozenset({
            "app.catalog.changed", "window.state.changed",
            "session.state.changed",
        }))


if __name__ == "__main__":
    unittest.main()
