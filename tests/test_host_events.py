"""Inert host-owned callbacks only; no real Qt/OS event claims."""
import math
from pathlib import Path
from threading import Thread
import unittest

from canopy_core.host_events import (
    DispatchResult, HostEventError, HostEvents, HostEventsBusy, HostEventsClosed,
    PROTOCOL_VERSION, TOPICS, _encode_fields,
)


class HostEventTests(unittest.TestCase):
    def test_order_sequence_immutable_fields_and_no_mutable_payload(self):
        received = []
        first = lambda e: received.append(("a", e.sequence, e.payload))
        second = lambda e: received.append(("b", e.sequence, e.payload))
        bus = HostEvents({"app.catalog.changed": [first, second]})
        bus.subscribe("app.catalog.changed", first)
        bus.subscribe("app.catalog.changed", second)
        a = bus.emit("app.catalog.changed", {"item_count": 4, "available": True})
        b = bus.emit("app.catalog.changed", {"item_count": 5})
        self.assertEqual(a.delivered, 2)
        self.assertEqual(a.callback_failures, 0)
        self.assertEqual([x[:2] for x in received],
                         [("a", 1), ("b", 1), ("a", 2), ("b", 2)])
        self.assertEqual((a.event.version, b.event.sequence),
                         (PROTOCOL_VERSION, 2))
        with self.assertRaises(TypeError):
            a.event.payload["item_count"] = 10
        self.assertEqual(a.event.payload["item_count"], 4)

    def test_no_thread_poll_or_network_imports(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_core/host_events.py").read_text()
        self.assertNotIn("QTimer", code)
        self.assertNotIn("asyncio", code)
        self.assertNotIn("subprocess", code)
        self.assertNotIn("import socket", code)
        self.assertNotIn("Thread(", code)
        self.assertNotIn("importlib", code)
        self.assertNotIn("time.sleep", code)

    def test_refuse_unsupported_version_and_bool_version(self):
        for version in (0, True, 1, 100, "2"):
            with self.subTest(version=version):
                with self.assertRaises(HostEventError):
                    HostEvents({}, version=version)

    def test_only_explicitly_trusted_callbacks_can_subscribe(self):
        seen = []
        known = lambda e: seen.append(e)
        unknown = lambda e: seen.append("untrusted")
        bus = HostEvents({"window.state.changed": [known]})
        with self.assertRaises(HostEventError):
            bus.subscribe("window.state.changed", unknown)
        with self.assertRaises(HostEventError):
            bus.subscribe("unknown.topic", known)
        token = bus.subscribe("window.state.changed", known)
        with self.assertRaisesRegex(HostEventError, "duplicate"):
            bus.subscribe("window.state.changed", known)
        bus.emit("window.state.changed", {"window_count": 2})
        self.assertEqual(len(seen), 1)
        self.assertTrue(bus.unsubscribe(token))
        self.assertFalse(bus.unsubscribe(token))
        bus.emit("window.state.changed", {"window_count": 3})
        self.assertEqual(len(seen), 1)

    def test_reject_duplicate_or_noncallable_trusted_map(self):
        fn = lambda e: None
        for approved in ({"app.catalog.changed": [fn, fn]},
                         {"window.state.changed": [42]},
                         {"unknown": [fn]},
                         {"session.state.changed": "fn"}):
            with self.subTest(approved=repr(approved)):
                with self.assertRaises(HostEventError):
                    HostEvents(approved)

    def test_callback_exceptions_do_not_expose_secrets_or_abort_delivery(self):
        events = []
        def bad(e):
            raise RuntimeError("SECRET=do-not-log")
        def good(e):
            events.append(e.sequence)
        bus = HostEvents({"session.state.changed": [bad, good]})
        bus.subscribe("session.state.changed", bad)
        bus.subscribe("session.state.changed", good)
        result = bus.emit("session.state.changed", {"state": "active"})
        self.assertEqual(result.callback_failures, 1)
        self.assertEqual(result.delivered, 1)
        self.assertEqual(events, [1])
        self.assertNotIn("SECRET", repr(result))

    def test_reentrancy_unsubscribe_and_close_are_blocked_in_callback(self):
        marks = []
        bus = None
        def reenter(event):
            for do in (lambda: bus.emit("app.catalog.changed", {}),
                       lambda: bus.unsubscribe(token), bus.close):
                with self.assertRaises(HostEventsBusy):
                    do()
            marks.append(event.sequence)
        bus = HostEvents({"app.catalog.changed": [reenter]})
        token = bus.subscribe("app.catalog.changed", reenter)
        self.assertEqual(bus.emit("app.catalog.changed", {}).delivered, 1)
        self.assertEqual(bus.emit("app.catalog.changed", {}).delivered, 1)
        self.assertEqual(marks, [1, 2])
        self.assertEqual(bus.subscription_count, 1)

    def test_payload_validates_unicode_fields_bounds_and_nested_inputs(self):
        legal = _encode_fields({"title": "Café", "count": 12, "ready": True,
                               "rate": 0.75, "nothing": None})
        self.assertEqual(dict(legal)["title"], "Café")
        malicious = [
            {"__proto__": 1}, {"constructor": "x"}, {"token": "x"},
            {"secret": "x"}, {"A": 1}, {"nested": []}, {"nested": {}},
            {"value": b"bytes"}, {"value": float("nan")},
            {"value": float("inf")}, {"value": 10**30},
            {"title": "🦊" * 400}, {"title": "\ud800"}, {"long_" + "a"*70: 5},
            {str(i): i for i in range(9)},
        ]
        for payload in malicious:
            with self.subTest(payload=list(payload)[:2]):
                with self.assertRaises(HostEventError):
                    _encode_fields(payload)

    def test_unknown_event_does_not_advance_sequence(self):
        seen = []
        receive = lambda e: seen.append(e.sequence)
        bus = HostEvents({"app.catalog.changed": [receive]})
        bus.subscribe("app.catalog.changed", receive)
        with self.assertRaises(HostEventError):
            bus.emit("window.invalid", {"foo": 1})
        with self.assertRaises(HostEventError):
            bus.emit("app.catalog.changed", {"__proto__": 1})
        self.assertEqual(bus.emit("app.catalog.changed", {}).event.sequence, 1)

    def test_cleanup_and_closed_bus_release_all_references(self):
        fn = lambda e: None
        bus = HostEvents({"session.state.changed": [fn]})
        t = bus.subscribe("session.state.changed", fn)
        bus.close()
        bus.close()  # idempotent cleanup
        self.assertEqual(bus.subscription_count, 0)
        self.assertTrue(bus.closed)
        for operation in (lambda: bus.emit("session.state.changed", {}),
                          lambda: bus.unsubscribe(t),
                          lambda: bus.subscribe("session.state.changed", fn)):
            with self.assertRaises(HostEventsClosed):
                operation()

    def test_subscriber_cap_is_hard_bounded(self):
        a = lambda e: None
        b = lambda e: None
        bus = HostEvents({"app.catalog.changed": [a, b]}, max_subscribers=1)
        bus.subscribe("app.catalog.changed", a)
        with self.assertRaisesRegex(HostEventError, "limit"):
            bus.subscribe("app.catalog.changed", b)
        with self.assertRaises(HostEventError):
            HostEvents({}, max_subscribers=999)
        with self.assertRaises(HostEventError):
            HostEvents({}, max_subscribers=True)

    def test_different_thread_is_rejected_without_mutation(self):
        seen = []
        fn = lambda e: seen.append(e)
        bus = HostEvents({"app.catalog.changed": [fn]})
        bus.subscribe("app.catalog.changed", fn)
        errors = []
        def other_thread():
            for action in (lambda: bus.emit("app.catalog.changed", {}),
                           bus.close):
                try:
                    action()
                except Exception as exc:
                    errors.append(type(exc))
        worker = Thread(target=other_thread)
        worker.start()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [HostEventError, HostEventError])
        self.assertFalse(bus.closed)
        self.assertEqual(bus.emit("app.catalog.changed", {}).delivered, 1)
        bus.close()


if __name__ == "__main__":
    unittest.main()
