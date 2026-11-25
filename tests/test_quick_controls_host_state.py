"""Regression tests for read-only quick-controls host-state wiring.

Pure-Python contract tests plus QML source contracts. No Qt is instantiated,
no host is probed and no action is executed. Compiled/visual evidence is
recorded in docs/classic-quick-controls-host-state.md.
"""
import ast
import json
import unittest
from pathlib import Path

from canopy_core.host_events import CAPABILITIES_TOPIC, TOPICS, HostEvents
from canopy_features.quick_controls import (
    ALLOWED_FIELDS,
    DEFAULT_SOURCE,
    HostStateController,
    HostStateError,
    HostStateSnapshot,
    empty_snapshot,
)
from canopy_features.reliability.lock_session_events import SessionState
from canopy_features.system.quick_controls_state import DOMAINS

ROOT = Path(__file__).resolve().parents[1]
QML = (ROOT / "prototype" / "classic" / "QuickControlsOverlay.qml").read_text(
    encoding="utf-8")
MODULE_SOURCE = (ROOT / "canopy_features" / "quick_controls"
                 / "host_state.py").read_text(encoding="utf-8")


class EmptySnapshotTests(unittest.TestCase):
    def test_empty_snapshot_is_honest_and_bounded(self):
        snapshot = empty_snapshot()
        self.assertEqual(snapshot.source, DEFAULT_SOURCE)
        self.assertEqual(snapshot.observations(), ())
        payload = snapshot.to_dict()
        self.assertEqual(set(payload), set(DOMAINS))
        self.assertLess(len(json.dumps(payload, ensure_ascii=True)), 8192)
        for domain, view in payload.items():
            with self.subTest(domain=domain):
                self.assertEqual(view["status"], "unknown")
                self.assertEqual(view["status_label"], "Unknown — no host status")
                self.assertFalse(view["observed"])
                self.assertEqual(view["source"], "none")
                self.assertEqual(view["availability"], "UNAVAILABLE")
                self.assertFalse(view["control"]["allowed"])
                self.assertFalse(view["settings"]["allowed"])
                self.assertIn("Unavailable — ", view["control"]["disclosure"])
                self.assertEqual(view["detail_kind"], "")
                self.assertEqual(view["detail_value"], -1)

    def test_unknown_domain_view_is_fail_closed_without_details(self):
        view = empty_snapshot().view("bluetooth")
        self.assertEqual(view["domain"], "unknown")
        self.assertNotIn("detail_kind", view)
        self.assertNotIn("detail_value", view)

    def test_controller_exposes_only_the_view_contract(self):
        controller = HostStateController.empty()
        self.assertEqual(controller.domains, DOMAINS)
        self.assertEqual(controller.view("audio"), controller.to_dict()["audio"])
        self.assertTrue(callable(controller.view))
        self.assertFalse(hasattr(controller, "request"))
        for method in ("launch", "exec", "write", "subscribe", "emit"):
            self.assertFalse(hasattr(controller, method))
        with self.assertRaises(HostStateError):
            HostStateController("not-a-snapshot")


class HostStateMappingTests(unittest.TestCase):
    def test_payload_maps_real_network_volume_brightness_and_session(self):
        snapshot = HostStateSnapshot.from_payload({
            "network_connected": True,
            "audio_muted": False,
            "volume_percent": 42,
            "brightness_percent": 68,
            "battery_charging": False,
            "settings_bridge": True,
        })
        payload = snapshot.to_dict()
        self.assertEqual(payload["network"]["status_label"], "Connected")
        self.assertEqual(payload["audio"]["status_label"], "Sound on")
        self.assertEqual(payload["power"]["status_label"], "On battery")
        self.assertEqual(payload["audio"]["detail_kind"], "volume")
        self.assertEqual(payload["audio"]["detail_value"], 42)
        self.assertEqual(payload["power"]["detail_kind"], "brightness")
        self.assertEqual(payload["power"]["detail_value"], 68)
        self.assertTrue(payload["network"]["observed"])
        self.assertTrue(payload["network"]["settings"]["allowed"])
        self.assertFalse(payload["network"]["control"]["allowed"])

    def test_session_uses_existing_reconciled_contract(self):
        snapshot = HostStateSnapshot(
            session=SessionState(False, True), source="host-reconciler")
        view = snapshot.view("session")
        self.assertEqual(view["status"], "locked")
        self.assertEqual(view["status_label"], "Locked")
        self.assertEqual(view["source"], "host-reconciler")
        self.assertTrue(view["observed"])

    def test_suspended_session_cannot_report_unlocked(self):
        view = HostStateSnapshot(
            session=SessionState(True, True)).view("session")
        self.assertEqual(view["status"], "suspended")

    def test_delivered_host_event_is_accepted(self):
        delivered = []
        callback = delivered.append
        bus = HostEvents({CAPABILITIES_TOPIC: [callback]})
        bus.subscribe(CAPABILITIES_TOPIC, callback)
        result = bus.emit(CAPABILITIES_TOPIC, {
            "network_connected": False,
            "audio_muted": True,
            "volume_percent": 0,
            "brightness_percent": 100,
        })
        self.assertEqual(result.delivered, 1)
        self.assertEqual(len(delivered), 1)
        controller = HostStateController.from_host_event(result.event)
        payload = controller.to_dict()
        self.assertEqual(payload["network"]["status_label"], "Not connected")
        self.assertEqual(payload["audio"]["status_label"], "Muted")
        self.assertEqual(payload["audio"]["detail_value"], 0)
        self.assertEqual(payload["power"]["detail_value"], 100)
        bus.close()

    def test_host_event_on_any_allowlisted_topic_is_read_only(self):
        for topic in TOPICS:
            with self.subTest(topic=topic):
                bus = HostEvents({topic: [lambda event: None]})
                result = bus.emit(topic, {"network_connected": True})
                self.assertTrue(
                    HostStateController.from_host_event(result.event)
                    .view("network")["observed"])
                bus.close()

    def test_unknown_payload_keys_are_ignored_not_echoed(self):
        snapshot = HostStateSnapshot.from_payload({
            "network_connected": True,
            "unrelated_consumer_field": "sensitive-value",
            "source": "host-events",
        })
        text = json.dumps(snapshot.to_dict(), ensure_ascii=True)
        self.assertNotIn("sensitive-value", text)
        self.assertNotIn("unrelated_consumer_field", text)
        self.assertEqual(set(ALLOWED_FIELDS), {
            "network_connected", "audio_muted", "battery_charging",
            "volume_percent", "brightness_percent", "settings_bridge"})


class FailClosedValidationTests(unittest.TestCase):
    def test_missing_fields_never_become_false_or_zero(self):
        views = HostStateSnapshot(volume_percent=0).to_dict()
        self.assertEqual(views["network"]["status"], "unknown")
        self.assertEqual(views["audio"]["status"], "unknown")
        self.assertEqual(views["power"]["status"], "unknown")
        self.assertEqual(views["audio"]["detail_kind"], "volume")
        self.assertEqual(views["network"]["detail_kind"], "")

    def test_bool_fields_require_exact_bool_or_none(self):
        for name in ("network_connected", "audio_muted", "battery_charging"):
            for value in (1, 0, "true", None):
                with self.subTest(name=name, value=value):
                    if value is None:
                        HostStateSnapshot(**{name: None})
                    else:
                        with self.assertRaises(HostStateError):
                            HostStateSnapshot(**{name: value})

    def test_percent_fields_are_bounded_ints_not_bools(self):
        for value in (-1, 101, True, False, 1.0, "40", None):
            with self.subTest(value=value):
                if value is None:
                    HostStateSnapshot(volume_percent=None,
                                      brightness_percent=None)
                else:
                    with self.assertRaises(HostStateError):
                        HostStateSnapshot(volume_percent=value)
                    with self.assertRaises(HostStateError):
                        HostStateSnapshot(brightness_percent=value)
        self.assertEqual(
            HostStateSnapshot(volume_percent=0, brightness_percent=100)
            .view("audio")["detail_value"], 0)

    def test_settings_bridge_requires_exact_bool(self):
        for value in (1, "true", None):
            with self.subTest(value=value):
                with self.assertRaises(HostStateError):
                    HostStateSnapshot(settings_bridge=value)

    def test_session_field_rejects_lookalike_objects(self):
        for value in ({"suspended": False, "locked": False}, 7, "locked"):
            with self.subTest(value=value):
                with self.assertRaises(HostStateError):
                    HostStateSnapshot(session=value)

    def test_source_is_bounded_and_ascii(self):
        for value in ("a" * 65, "host with space", "hôst", 7, "\ud800"):
            with self.subTest(value=value):
                with self.assertRaises(HostStateError):
                    HostStateSnapshot(source=value)

    def test_non_mapping_payload_and_non_event_are_refused(self):
        for payload in (None, [], (), "payload", 7):
            with self.subTest(payload=payload):
                with self.assertRaises(HostStateError):
                    HostStateSnapshot.from_payload(payload)
        with self.assertRaises(HostStateError):
            HostStateSnapshot.from_host_event({"topic": "capabilities.report"})
        with self.assertRaises(HostStateError):
            HostStateSnapshot.from_host_event("event")

    def test_observations_are_bounded_and_unique(self):
        snapshot = HostStateSnapshot(
            network_connected=True, audio_muted=True, battery_charging=True,
            session=SessionState(False, False))
        observations = snapshot.observations()
        self.assertEqual(len(observations), 4)
        self.assertEqual(len({item.domain for item in observations}), 4)


class NoPrivilegedWriteTests(unittest.TestCase):
    def test_module_imports_no_io_or_process_api(self):
        tree = ast.parse(MODULE_SOURCE)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0]
                                for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in ("subprocess", "socket", "os", "shutil", "asyncio",
                          "threading", "multiprocessing", "signal", "ctypes",
                          "dbus", "gi"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, imported)

    def test_no_process_socket_dbus_or_daemon_calls_in_source(self):
        code_only = "\n".join(
            line for line in MODULE_SOURCE.splitlines()
            if not line.lstrip().startswith("#"))
        for forbidden in ("QProcess", "subprocess", "socket", "pkexec",
                          "sudo ", "systemctl", "gdbus", "dbus-send",
                          "Popen", "os.system"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code_only)

    def test_docstring_states_read_only_boundary(self):
        self.assertIn("no I/O", MODULE_SOURCE)


class QmlContractTests(unittest.TestCase):
    def test_overlay_consumes_host_state_adapter(self):
        self.assertIn("property var hostState: null", QML)
        self.assertIn("function trustedView(domain, adapter)", QML)
        self.assertIn("var supplied = trustedView(domain, hostState)", QML)
        self.assertIn('kind !== "volume"', QML)
        self.assertIn('kind !== "brightness"', QML)

    def test_detail_label_is_composed_from_fixed_tokens_only(self):
        self.assertIn('kind === "volume" ? " · Volume " : " · Brightness "',
                      QML)
        self.assertIn("Math.floor(value) === value", QML)
        self.assertIn('label.length > 64', QML)
        self.assertIn("return label + prefix + value + \"%\"", QML)

    def test_no_new_io_or_process_path_in_qml(self):
        for forbidden in ("Qt.createQmlObject", "Process {", "QProcess",
                          "NetworkRequest", "Timer {", "XmlHttp",
                          "Qt.openUrlExternally", "LocalStorage"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, QML)

    def test_previous_fail_closed_contract_is_preserved(self):
        self.assertIn('readonly property var domains: ["network", "audio", '
                      '"power", "session"]', QML)
        self.assertIn("property var controller: null", QML)
        self.assertIn("property var actionBridge: null", QML)
        self.assertIn('objectName: "canopyQuickControlsOverlay"', QML)
        self.assertIn("Unknown — no host status", QML)
        self.assertIn("Unavailable — no host control interface", QML)
        self.assertIn("Keys.onEscapePressed: quickControls.closeControls()", QML)


if __name__ == "__main__":
    unittest.main()
