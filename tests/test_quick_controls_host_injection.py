"""Regression contracts for compiled quick-controls host-state injection.

These tests guard the compiled-shell wiring in ``prototype/classic/main.cpp``:
the in-process controller, its Python-mirrored host-event allowlist, fail-closed
view contract, lifetime/rebinding and the absence of privileged transports.
They do not instantiate Qt and do not claim compiled behaviour on their own:
the compiled self-test, three captures and full-suite delta are recorded in
``docs/classic-quick-controls-host-state.md``.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from canopy_core.host_events import CAPABILITIES_TOPIC, TOPICS, HostEvents
from canopy_features.quick_controls import (
    ALLOWED_FIELDS,
    HostStateController,
    HostStateError,
)
from canopy_features.system.quick_controls_state import DOMAINS, STATUS_LABELS

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "prototype" / "classic" / "main.cpp"
CMAKE = ROOT / "prototype" / "classic" / "CMakeLists.txt"
QML = ROOT / "prototype" / "classic" / "QuickControlsOverlay.qml"
DOC = ROOT / "docs" / "classic-quick-controls-host-state.md"

# Fixed tokens the compiled C++ renderer is allowed to emit; every one is an
# existing token from the pure model, never caller text.
COMPILED_LABELS = frozenset({
    "Connected", "Not connected", "Muted", "Sound on", "Charging",
    "On battery", "Unknown — no host status",
})


class CompiledInjectionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = MAIN.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.qml = QML.read_text(encoding="utf-8")
        cls.doc = DOC.read_text(encoding="utf-8")
        start = cls.cpp.index("class QuickControlsHostStateController final")
        end = cls.cpp.index("\n};", start)
        cls.controller = cls.cpp[start:end]
        cls.literals = set(re.findall(
            r'QStringLiteral\("([^"]+)"\)', cls.controller))

    def test_controller_is_in_process_read_only_view(self):
        for marker in (
                "class QuickControlsHostStateController final : public QObject",
                "Q_OBJECT",
                "Q_INVOKABLE bool applyHostEvent(",
                "Q_INVOKABLE QVariantMap view(",
                "The single read-only view() surface",
                "signals:",
                "void viewChanged();",
                "emit viewChanged();",
                "The single read-only view() surface",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.controller)
        for forbidden in ("QProcess", "QTcpSocket", "QUdpSocket", "QLocalSocket",
                          "QDBus", "QNetworkAccessManager", "QFile", "QSaveFile",
                          "std::system", "pkexec", "sudo "):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.controller)

    def test_topics_and_fields_mirror_existing_host_event_contract(self):
        block = re.search(
            r"static const QSet<QString> allowedTopics = \{(.*?)\};",
            self.controller, re.S)
        self.assertIsNotNone(block)
        topics = set(re.findall(r'QStringLiteral\("([^"]+)"\)', block.group(1)))
        self.assertEqual(topics, set(TOPICS))
        self.assertIn(CAPABILITIES_TOPIC, topics)
        for field in set(ALLOWED_FIELDS) | {"source"}:
            with self.subTest(field=field):
                self.assertIn(field, self.literals)
        for literal in self.literals:
            self.assertNotIn("token", literal)
            self.assertNotIn("password", literal)

    def test_labels_are_existing_fixed_tokens_only(self):
        self.assertTrue(COMPILED_LABELS.issubset(set(STATUS_LABELS.values())))
        for label in COMPILED_LABELS:
            with self.subTest(label=label):
                self.assertIn(label, self.literals)
        for reason in ("ok", "bridge-disabled", "privileged-host-change",
                       "invalid-domain", "no-host-interface"):
            self.assertIn(reason, self.literals)

    def test_fail_closed_validation_matches_python_mirror(self):
        for marker in (
                "if (!allowedTopics.contains(topic))",
                "QMetaType(QMetaType::Bool)",
                "QMetaType(QMetaType::Int)",
                "QMetaType(QMetaType::QString)",
                "percent < 0 || percent > 100",
                "source.size() > 64",
                "Commit only after every field passed validation.",
                "Unknown — no host status",
                "privileged-host-change",
                "no-host-interface",
                "detail_kind",
                "detail_value",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.controller)
        self.assertGreaterEqual(self.controller.count("return false;"), 6)
        # A bool is an int in Qt variants; the C++ mirror must reject it.
        self.assertIn("A bool is an int", self.controller)

    def test_session_stays_unknown_without_a_reconciled_source(self):
        self.assertIn("Session stays unknown", self.controller)
        self.assertNotIn('QStringLiteral("Locked")', self.controller)
        self.assertNotIn('QStringLiteral("Active")', self.controller)

    def test_lifetime_and_rebinding_are_scoped_to_the_overlay(self):
        cpp = self.cpp
        controller_index = cpp.index(
            "QuickControlsHostStateController hostStateController;")
        engine_index = cpp.index("QQmlApplicationEngine engine;")
        self.assertLess(controller_index, engine_index)
        for marker in (
                'setContextProperty(\n        QStringLiteral("canopyHostState"), '
                '&hostStateController)',
                'initial.insert(QStringLiteral("hostState")',
                "QObject::connect(&hostStateController,",
                "&QuickControlsHostStateController::viewChanged,",
                'setProperty("hostState", QVariant())',
                'setProperty("hostState",\n                QVariant::fromValue('
                'static_cast<QObject *>(&hostStateController)))',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)
        # A rejected event must not trigger rebinding: emit is only after commit.
        self.assertLess(self.controller.index("emit viewChanged();"),
                        self.controller.index("return true;"))

    def test_compiled_self_test_covers_live_render_and_hostile_rejection(self):
        for marker in (
                '--self-test-quick-controls-host',
                "QUICK_CONTROLS_HOST_FIXTURE_FAIL: controller not wired",
                'QUICK_CONTROLS_HOST_FIXTURE_FAIL: bounded event rejected',
                'QStringLiteral("Sound on · Volume 42%")',
                'QStringLiteral("On battery · Brightness 68%")',
                "QUICK_CONTROLS_HOST_FIXTURE_FAIL: privileged/direct control enabled",
                "QUICK_CONTROLS_HOST_FIXTURE_FAIL: hostile event accepted",
                "QUICK_CONTROLS_HOST_FIXTURE_FAIL: hostile event mutated view",
                "QUICK_CONTROLS_HOST_SELF_TEST_PASS",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.cpp)

    def test_no_visual_or_cmake_source_change_is_needed(self):
        # The controller lives entirely in main.cpp, so no new source file is
        # registered and no visual QML or approved asset is touched.
        self.assertIn(
            "qt_add_executable(canopy-classic-spike main.cpp "
            "WindowActivationState.cpp", self.cmake)
        self.assertNotIn("QuickControlsHostState", self.cmake)
        for marker in ("property var hostState: null", "function trustedView(",
                       'objectName: "canopyQuickControlsOverlay"'):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.qml)

    def test_evidence_documents_real_commands_and_honest_limits(self):
        for marker in ("Current head", "SYNTHETIC", "NOT_RUN", "screen-reader",
                       "1920x1080", "1200x750", "760x500",
                       "QUICK_CONTROLS_HOST_SELF_TEST_PASS"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.doc)


class HostEventMirrorTests(unittest.TestCase):
    def test_delivered_event_drives_the_same_view_contract(self):
        delivered = []
        def on_event(event):
            delivered.append(event)
        bus = HostEvents({CAPABILITIES_TOPIC: [on_event]})
        bus.subscribe(CAPABILITIES_TOPIC, on_event)
        result = bus.emit(CAPABILITIES_TOPIC, {
            "network_connected": True,
            "audio_muted": False,
            "battery_charging": False,
            "volume_percent": 42,
            "brightness_percent": 68,
            "source": "host-events",
        })
        self.assertEqual(result.delivered, 1)
        self.assertEqual(len(delivered), 1)
        controller = HostStateController.from_host_event(result.event)
        payload = controller.to_dict()
        self.assertEqual(set(payload), set(DOMAINS))
        self.assertEqual(payload["network"]["status_label"], "Connected")
        self.assertEqual(payload["audio"]["status_label"], "Sound on")
        self.assertEqual(payload["power"]["status_label"], "On battery")
        self.assertEqual(payload["audio"]["detail_kind"], "volume")
        self.assertEqual(payload["audio"]["detail_value"], 42)
        self.assertEqual(payload["power"]["detail_kind"], "brightness")
        self.assertEqual(payload["power"]["detail_value"], 68)
        self.assertEqual(payload["session"]["status"], "unknown")
        self.assertFalse(payload["network"]["control"]["allowed"])
        bus.close()

    def test_hostile_bounded_shaped_payload_is_refused(self):
        for payload in (
                {"volume_percent": 999},
                {"network_connected": "true"},
                {"brightness_percent": True},
                {"source": "bad source"},
                {"audio_muted": 1},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(HostStateError):
                    HostStateController.from_payload(payload)

    def test_unlisted_topic_is_refused(self):
        bus = HostEvents({"capabilities.report": [lambda event: None]})
        result = bus.emit("capabilities.report", {"network_connected": True})
        event = result.event
        # The delivered event contract itself allowlists TOPICS; a fabricated
        # topic is refused by the adapter before any view can be produced.
        forged = type(event)(event.version, "wifi.scan.changed",
                             event.sequence, event.fields)
        with self.assertRaises(HostStateError):
            HostStateController.from_host_event(forged)
        bus.close()


if __name__ == "__main__":
    unittest.main()
