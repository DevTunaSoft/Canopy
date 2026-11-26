"""SYNTHETIC fail-closed tests for the trusted quick-controls status producer.

These are pure-Python contract checks. They never probe a live host, read
desktop state, compile Qt, inject a file into the compiled shell or claim
Mint/screen-reader/visual acceptance. Compiled wiring and real host readings
are NOT_RUN. Every fixture value below is an explicitly supplied, bounded fact.
"""
import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType
from unittest.mock import patch

from canopy_core.host_events import CAPABILITIES_TOPIC, TOPICS, HostEvents
from canopy_features.quick_controls import host_status_producer as producer
from canopy_features.quick_controls.host_state import HostStateController

SOURCE = Path(producer.__file__)

# The compiled controller's accepted keys, mirrored literally (no new topic or
# field is introduced by the producer). ``topic`` selects the existing bus
# topic; ``source`` is provenance required by the producer, not a new event key.
WIRE_KEYS = frozenset({
    "topic", "source", "network_connected", "volume_percent",
    "battery_charging",
})


def _compose(**overrides):
    kwargs = dict(source="host-status-file", network_connected=True,
                  volume_percent=42, battery_charging=False)
    kwargs.update(overrides)
    return producer.compose(**kwargs)


class TrustedWireTests(unittest.TestCase):
    def test_emits_exact_bounded_wire_keys_and_types(self):
        record = _compose()
        payload = json.loads(record.to_json_bytes().decode("utf-8"))
        self.assertEqual(frozenset(payload), WIRE_KEYS)
        self.assertEqual(payload["topic"], CAPABILITIES_TOPIC)
        self.assertIn(payload["topic"], TOPICS)
        self.assertIs(type(payload["topic"]), str)
        self.assertIs(type(payload["source"]), str)
        self.assertEqual(payload["source"], "host-status-file")
        self.assertIs(type(payload["network_connected"]), bool)
        self.assertIs(payload["network_connected"], True)
        self.assertIs(type(payload["volume_percent"]), int)
        self.assertEqual(payload["volume_percent"], 42)
        self.assertIs(type(payload["battery_charging"]), bool)
        self.assertIs(payload["battery_charging"], False)

    def test_omitted_facts_are_absent_not_null_or_fabricated(self):
        payload = json.loads(
            _compose(network_connected=None, battery_charging=None,
                     volume_percent=0).to_json_bytes().decode("utf-8"))
        self.assertEqual(frozenset(payload),
                         {"topic", "source", "volume_percent"})
        self.assertEqual(payload["volume_percent"], 0)
        self.assertNotIn(None, payload.values())

    def test_bytes_are_deterministic_bounded_and_ascii(self):
        first = _compose().to_json_bytes()
        self.assertIs(type(first), bytes)
        self.assertEqual(first, _compose().to_json_bytes())
        self.assertLessEqual(len(first), 16 * 1024)
        self.assertTrue(first.isascii())
        self.assertIn(b'"capabilities.report"', first)

    def test_record_is_frozen_and_view_is_fresh_read_only(self):
        record = _compose()
        with self.assertRaises(FrozenInstanceError):
            record.volume_percent = 7
        view = record.to_dict()
        again = record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        self.assertIsNot(view, again)
        with self.assertRaises(TypeError):
            view["source"] = "other"
        self.assertEqual(tuple(view), tuple(sorted(WIRE_KEYS)))

    def test_existing_controller_renders_only_supplied_facts(self):
        payload = dict(_compose().to_dict())
        payload.pop("topic")
        views = HostStateController.from_payload(payload).to_dict()
        self.assertEqual(views["network"]["status_label"], "Connected")
        # audio_muted is deliberately not emitted (out of scope), so the muted
        # status stays unknown; only the supplied volume detail is published.
        self.assertEqual(views["audio"]["status"], "unknown")
        self.assertEqual(views["audio"]["detail_kind"], "volume")
        self.assertEqual(views["audio"]["detail_value"], 42)
        self.assertEqual(views["power"]["status_label"], "On battery")
        self.assertEqual(views["session"]["status"], "unknown")

    def test_from_payload_projects_trusted_mapping_without_echo(self):
        record = producer.from_payload({
            "network_connected": True,
            "volume_percent": 100,
            "other_consumer_field": "not-echoed",
        }, source="host-status-file")
        payload = json.loads(record.to_json_bytes().decode("utf-8"))
        self.assertEqual(frozenset(payload), WIRE_KEYS - {"battery_charging"})
        self.assertEqual(payload["volume_percent"], 100)
        self.assertNotIn("other_consumer_field", payload)
        self.assertNotIn("not-echoed", json.dumps(payload))


class FailClosedTests(unittest.TestCase):
    def test_wrong_field_types_are_refused(self):
        bad_values = (1, 0, "true", 1.0, [], {}, (), b"true", bytearray(b"x"))
        for field in ("network_connected", "battery_charging"):
            for value in bad_values:
                with self.subTest(field=field, value=repr(value)):
                    with self.assertRaises(producer.ProducerError):
                        _compose(**{field: value})
        for value in (True, False, "42", 42.0, [], {}, (), b"42", 2**64):
            with self.subTest(field="volume_percent", value=repr(value)):
                with self.assertRaises(producer.ProducerError):
                    _compose(volume_percent=value)

    def test_volume_bounds_are_refused(self):
        for value in (-1, 101, -2**31, 2**31):
            with self.subTest(value=value):
                with self.assertRaises(producer.ProducerError):
                    _compose(volume_percent=value)
        self.assertEqual(_compose(volume_percent=0).volume_percent, 0)
        self.assertEqual(_compose(volume_percent=100).volume_percent, 100)

    def test_unknown_or_hostile_sources_are_refused(self):
        for source in ("", "untrusted", "wifi.scan.changed", "Host-Events",
                       "host-events ", " host-events", "hôst-events",
                       "host\nstatus", "a" * 65, None, 7, True, [],
                       {}, b"host-events", "host-event\ud800"):
            with self.subTest(source=repr(source)):
                with self.assertRaises(producer.ProducerError):
                    _compose(source=source)

    def test_no_facts_is_refused(self):
        with self.assertRaises(producer.ProducerError):
            producer.compose(source="host-status-file")

    def test_direct_construction_validates_too(self):
        with self.assertRaises(producer.ProducerError):
            producer.HostStatusSnapshot(source="host-status-file",
                                        volume_percent=999)
        with self.assertRaises(producer.ProducerError):
            producer.HostStatusSnapshot(source="untrusted",
                                        network_connected=False)

    def test_byte_cap_is_enforced_before_emission(self):
        record = _compose()
        with patch.object(producer, "MAX_FILE_BYTES", 16):
            with self.assertRaises(producer.ProducerError):
                record.to_json_bytes()

    def test_unsupported_topic_and_contradictory_source_are_refused(self):
        for payload, source in (
            ({"topic": "wifi.scan.changed"}, "host-status-file"),
            ({"source": "untrusted"}, "host-status-file"),
            ({"source": "host-events"}, "host-status-file"),
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(producer.ProducerError):
                    producer.from_payload(payload, source=source)


class ExpandedNegativeControlTests(unittest.TestCase):
    """Second-job expansion: hostile containers, provenance and boundaries."""

    def test_non_mapping_payloads_fail_closed(self):
        for bad in (None, [], (), "source", 7, {"a"}, (name for name in ("a",)),
                    b"payload", bytearray(b"payload")):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(producer.ProducerError):
                    producer.from_payload(bad, source="host-status-file")

    def test_inconsistent_custom_mapping_fails_closed(self):
        class Inconsistent(dict):
            def __contains__(self, key):
                return True

            def __getitem__(self, key):
                raise KeyError(key)

        class RaisingValues(dict):
            def __getitem__(self, key):
                if key == "volume_percent":
                    raise KeyError(key)
                return super().__getitem__(key)

        for bad in (Inconsistent(), RaisingValues(network_connected=True,
                                                  volume_percent=42)):
            with self.subTest(mapping=type(bad).__name__):
                with self.assertRaises(producer.ProducerError):
                    producer.from_payload(bad, source="host-status-file")

    def test_mixed_valid_and_hostile_facts_are_atomic(self):
        cases = (
            {"network_connected": True, "volume_percent": 999},
            {"battery_charging": False, "network_connected": "true"},
            {"volume_percent": 42, "battery_charging": []},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(producer.ProducerError):
                    producer.from_payload(payload, source="host-status-file")

    def test_numeric_and_string_subclasses_fail_closed(self):
        class IntSubclass(int):
            pass

        class StrSubclass(str):
            pass

        with self.assertRaises(producer.ProducerError):
            _compose(volume_percent=IntSubclass(42))
        with self.assertRaises(producer.ProducerError):
            _compose(network_connected=IntSubclass(1))
        with self.assertRaises(producer.ProducerError):
            _compose(source=StrSubclass("host-status-file"))
        with self.assertRaises(producer.ProducerError):
            _compose(volume_percent=float("nan"))
        with self.assertRaises(producer.ProducerError):
            _compose(volume_percent=float("inf"))

    def test_provenance_lookalikes_fail_closed(self):
        for source in ("Host-Status-File", "HOST-STATUS-FILE",
                       "host—status-file", "host-status-file\u200b",
                       "host-status-file\n", "host-status-file\t",
                       "host-status-file/", "host-status-file%00",
                       "host_status_file", "host-events:extra"):
            with self.subTest(source=repr(source)):
                with self.assertRaises(producer.ProducerError):
                    _compose(source=source)

    def test_topic_and_provenance_conflicts_fail_closed(self):
        for payload in (
            {"topic": None},
            {"topic": ["capabilities.report"]},
            {"topic": "session.state.changed"},
            {"source": ["host-status-file"]},
            {"source": "host-events", "network_connected": True},
            {"topic": CAPABILITIES_TOPIC, "source": "untrusted"},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(producer.ProducerError):
                    producer.from_payload(payload, source="host-status-file")

    def test_source_mapping_is_snapshotted_not_aliased(self):
        facts = {"network_connected": True, "volume_percent": 42}
        record = producer.from_payload(facts, source="host-status-file")
        before = record.to_json_bytes()
        facts["volume_percent"] = 999
        facts["battery_charging"] = True
        self.assertEqual(record.to_json_bytes(), before)
        self.assertEqual(record.to_dict()["volume_percent"], 42)
        self.assertNotIn("battery_charging", record.to_dict())

    def test_byte_cap_boundary_is_strict(self):
        size = len(_compose().to_json_bytes())
        with patch.object(producer, "MAX_FILE_BYTES", size):
            self.assertEqual(len(_compose().to_json_bytes()), size)
        with patch.object(producer, "MAX_FILE_BYTES", size - 1):
            with self.assertRaises(producer.ProducerError):
                _compose().to_json_bytes()

    def test_no_privileged_or_transport_text_in_source(self):
        code_only = "\n".join(
            line for line in SOURCE.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#"))
        for forbidden in ("open(", "os.environ", "subprocess", "pkexec",
                          "sudo ", "systemctl", "gdbus", "dbus-send",
                          "Popen", "QProcess", "socket.", "Timer(", "poll("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code_only)

    def test_emitted_payload_travels_existing_host_event_topic(self):
        payload = dict(_compose().to_dict())
        payload.pop("topic")
        callback = lambda event: None
        bus = HostEvents({CAPABILITIES_TOPIC: [callback]})
        try:
            bus.subscribe(CAPABILITIES_TOPIC, callback)
            result = bus.emit(CAPABILITIES_TOPIC, payload)
            self.assertEqual(result.delivered, 1)
            self.assertEqual(result.callback_failures, 0)
            views = HostStateController.from_host_event(result.event).to_dict()
            self.assertEqual(views["network"]["status_label"], "Connected")
            self.assertEqual(views["power"]["status_label"], "On battery")
            self.assertEqual(views["audio"]["detail_value"], 42)
        finally:
            bus.close()


class PurityTests(unittest.TestCase):
    def test_no_io_process_clock_or_transport_imports(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        forbidden = {"os", "sys", "subprocess", "socket", "pathlib", "time",
                     "datetime", "random", "threading", "multiprocessing",
                     "signal", "ctypes", "dbus", "gi", "PyQt5", "PySide6"}
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        self.assertFalse(found & forbidden,
                         "unexpected imports: %r" % (found & forbidden))

    def test_compose_and_serialize_open_no_files(self):
        with patch("builtins.open", side_effect=AssertionError("file I/O")):
            record = _compose()
            payload = record.to_dict()
            record.to_json_bytes()
        self.assertEqual(payload["volume_percent"], 42)


if __name__ == "__main__":
    unittest.main()
