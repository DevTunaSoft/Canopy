"""Contract tests for the explicit, bounded capabilities.report host event.

Run: python -m unittest tests.test_core_shell_host_capabilities_event -v
"""
import ast
from types import MappingProxyType
from pathlib import Path
import unittest

from canopy_core.host_events import (
    CAPABILITIES_TOPIC, HostEventError, HostEvents, HostEventsClosed,
    PROTOCOL_VERSION, TOPICS,
)
from canopy_core.shell_host import (
    CapabilityReportError, capability_event_payload,
)
from tests.test_core_shell_host_capability_report import host, records

PAYLOAD_KEYS = frozenset({
    "status", "schema", "component_count", "component_codes",
    "has_active_pack", "needs_recovery", "negative_claims",
})


def bus_with(*callbacks):
    return HostEvents({CAPABILITIES_TOPIC: list(callbacks)})


def observed():
    events = []

    def callback(event):
        events.append(event)

    return bus_with(callback), events


class CapabilityEventTests(unittest.TestCase):
    def test_topic_is_allowlisted(self):
        self.assertIn(CAPABILITIES_TOPIC, TOPICS)
        self.assertEqual(CAPABILITIES_TOPIC, "capabilities.report")

    def test_explicit_publish_delivers_once(self):
        bus, events = observed()
        token = bus.subscribe(CAPABILITIES_TOPIC,
                              bus._trusted[CAPABILITIES_TOPIC][0])
        result = host().publish_capability_report(records(), bus)
        self.assertEqual(result.delivered, 1)
        self.assertEqual(result.callback_failures, 0)
        self.assertEqual(result.event.topic, CAPABILITIES_TOPIC)
        self.assertEqual(result.event.version, PROTOCOL_VERSION)
        self.assertEqual(result.event.sequence, 1)
        self.assertEqual(len(events), 1)
        self.assertIs(events[0], result.event)
        bus.unsubscribe(token)

    def test_only_explicit_calls_emit(self):
        bus, events = observed()
        bus.subscribe(CAPABILITIES_TOPIC, bus._trusted[CAPABILITIES_TOPIC][0])
        h = host()
        self.assertEqual(bus._sequence, 0)
        h.publish_capability_report(records(), bus)
        self.assertEqual(bus._sequence, 1)
        h.publish_capability_report(records(), bus)
        self.assertEqual(bus._sequence, 2)
        self.assertEqual(len(events), 2)

    def test_no_subscription_or_host_state_retained(self):
        bus, _ = observed()
        bus.subscribe(CAPABILITIES_TOPIC, bus._trusted[CAPABILITIES_TOPIC][0])
        before = bus.subscription_count
        h = host()
        state = dict(h.__dict__)
        h.publish_capability_report(records(), bus)
        self.assertEqual(bus.subscription_count, before)
        self.assertEqual(h.__dict__.keys(), state.keys())

    def test_event_payload_is_frozen(self):
        bus, events = observed()
        bus.subscribe(CAPABILITIES_TOPIC, bus._trusted[CAPABILITIES_TOPIC][0])
        host().publish_capability_report(records(), bus)
        payload = events[0].payload
        self.assertIsInstance(payload, MappingProxyType)
        with self.assertRaises(TypeError):
            payload["status"] = "APPROVED"
        self.assertEqual(events[0].payload["status"], "CAPABILITY_REPORT")

    def test_payload_fields_are_bounded_and_fixed(self):
        bus, events = observed()
        bus.subscribe(CAPABILITIES_TOPIC, bus._trusted[CAPABILITIES_TOPIC][0])
        host().publish_capability_report(records(), bus)
        payload = events[0].payload
        self.assertEqual(frozenset(payload), PAYLOAD_KEYS)
        self.assertEqual(payload["status"], "CAPABILITY_REPORT")
        self.assertEqual(payload["schema"], 1)
        self.assertEqual(payload["component_count"], 8)
        self.assertEqual(payload["component_codes"].split("|"), [
            "OK", "READINESS_SNAPSHOT", "SNAPSHOT", "SUCCEEDED",
            "OK", "OK", "OK", "READY"])
        self.assertIs(type(payload["has_active_pack"]), bool)
        self.assertIs(type(payload["needs_recovery"]), bool)
        self.assertIn("release=not_approved", payload["negative_claims"])
        self.assertIn("process=not_launched", payload["negative_claims"])
        self.assertIn("io=none", payload["negative_claims"])

    def test_no_raw_value_echo_in_event(self):
        bus, events = observed()
        bus.subscribe(CAPABILITIES_TOPIC, bus._trusted[CAPABILITIES_TOPIC][0])
        h = host()
        recs = records()
        recs["recovery"]["startup"]["reason"] = "SECRET_EVENT_MARKER"
        recs["focus"]["focus"]["target_apps"] = ("secret.app",)
        h.publish_capability_report(recs, bus)
        rendered = repr(events[0].fields)
        for marker in ("SECRET_EVENT_MARKER", "secret.app", "SECRET_STARTUP_MARKER"):
            self.assertNotIn(marker, rendered)

    def test_cleanup_on_close_is_deterministic(self):
        bus, _ = observed()
        token = bus.subscribe(CAPABILITIES_TOPIC, bus._trusted[CAPABILITIES_TOPIC][0])
        host().publish_capability_report(records(), bus)
        bus.close()
        self.assertTrue(bus.closed)
        self.assertEqual(bus.subscription_count, 0)
        self.assertEqual(bus._trusted, {})
        with self.assertRaises(HostEventsClosed):
            bus.unsubscribe(token)
        with self.assertRaises(HostEventsClosed):
            host().publish_capability_report(records(), bus)

    def test_unknown_topic_fails_closed(self):
        bus = bus_with(lambda event: None)
        with self.assertRaises(HostEventError):
            bus.emit("capabilities.report.echo", {"status": "CAPABILITY_REPORT"})

    def test_invalid_records_do_not_emit(self):
        bus, events = observed()
        recs = records()
        del recs["desktop"]
        with self.assertRaises(CapabilityReportError):
            host().publish_capability_report(recs, bus)
        self.assertEqual(bus._sequence, 0)
        self.assertEqual(events, [])

    def test_bad_bus_or_report_fails_closed(self):
        with self.assertRaises(CapabilityReportError):
            host().publish_capability_report(records(), None)
        self.assertIsInstance(
            capability_event_payload(host().capability_report(records())), dict)
        with self.assertRaises(CapabilityReportError):
            capability_event_payload({"status": "CAPABILITY_REPORT"})

    def test_no_periodic_or_lifecycle_machinery(self):
        module = Path(__import__("canopy_core.shell_host").__file__)
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0],
                                     {"time", "asyncio", "sched", "signal"})
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0],
                                 {"time", "asyncio", "sched", "signal"})
            elif isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
                self.assertNotIn(name, {"Timer", "sleep", "subscribe",
                                        "popen", "Popen"})


if __name__ == "__main__":
    unittest.main()
