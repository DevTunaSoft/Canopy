"""Contract tests for the Classic fail-closed notification centre.

These are source-contract checks only. They do not compile Qt, open a window,
read OS notifications, or claim a host notification bridge exists. The real
compiled-shell proof is the C++ ``--self-test-notification-center`` fixture and
the screenshot self-test, which inspect the live QML scene.
"""
import json
import re
import unittest
from pathlib import Path

from canopy_core.host_events import TOPICS as HOST_EVENT_TOPICS

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
QML = (CLASSIC / "NotificationCenter.qml").read_text(encoding="utf-8")
MAIN_QML = (CLASSIC / "Main.qml").read_text(encoding="utf-8")
CMAKE = (CLASSIC / "CMakeLists.txt").read_text(encoding="utf-8")
MAIN_CPP = (CLASSIC / "main.cpp").read_text(encoding="utf-8")


class EventContractTests(unittest.TestCase):
    def test_topic_allowlist_is_exactly_the_existing_host_contract(self):
        match = re.search(r"contractTopics:\s*\[(.*?)\]", QML, re.DOTALL)
        self.assertIsNotNone(match, "QML must declare its accepted topic list")
        topics = json.loads("[" + match.group(1) + "]")
        self.assertEqual(len(topics), len(set(topics)))
        self.assertEqual(set(topics), set(HOST_EVENT_TOPICS))
        self.assertIn("capabilities.report", topics)

    def test_no_new_topic_or_event_emission(self):
        for forbidden in ("signal notificationArrived", "emit(",
                          "notification.received", "notification.changed",
                          "Qt.createComponent", "WebSockets", "DBus"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, QML)

    def test_host_bridge_must_match_the_contract_before_any_read(self):
        self.assertIn("function contractMatchesController()", QML)
        self.assertIn("function connectedFromController()", QML)
        self.assertIn("typeof controller.allowedTopics !== \"function\"", QML)
        self.assertIn("contractTopics.indexOf(allowed[i]) < 0", QML)
        self.assertIn("if (!connectedFromController() || !contractMatchesController())", QML)

    def test_records_are_bounded_and_wholly_rejected_on_bad_input(self):
        self.assertIn("readonly property int maxItems: 12", QML)
        self.assertIn("supplied.length > maxItems", QML)
        self.assertIn("function validRecord(record)", QML)
        self.assertIn("contractTopics.indexOf(record.topic) < 0", QML)
        self.assertIn("record.source !== hostEventSource", QML)
        self.assertIn("code < 32 || code === 127", QML)
        # A malformed entry must clear the entire snapshot, not skip one row.
        self.assertGreaterEqual(QML.count("reason = \"invalid-host-notification-source\""), 2)

    def test_no_fake_notifications_are_generated(self):
        for forbidden in ("Math.random", "Demo notification", "Sample notification",
                          "title: \"", "body: \"", "setTimeout", "Timer {"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, QML)
        self.assertIn("No host notification source — nothing is shown", QML)
        self.assertIn("Unavailable — no host notification source", QML)


class FailClosedPresentationTests(unittest.TestCase):
    def test_refresh_is_disabled_without_a_connected_source(self):
        self.assertIn("enabled: notificationCenter.sourceConnected", QML)
        self.assertIn("objectName: \"canopyNotificationRefreshButton\"", QML)
        self.assertIn("notificationCenter.noSourceDisclosure", QML)
        self.assertIn("onClicked: notificationCenter.reload()", QML)

    def test_close_and_escape_are_real_actions(self):
        self.assertIn("function closeCenter()", QML)
        self.assertIn("objectName: \"canopyNotificationCloseButton\"", QML)
        self.assertIn("onClicked: notificationCenter.closeCenter()", QML)
        self.assertIn("Keys.onEscapePressed: notificationCenter.closeCenter()", QML)

    def test_panel_is_hidden_until_opened_and_has_empty_state(self):
        self.assertIn("visible: opened", QML)
        self.assertIn("objectName: \"canopyNotificationEmptyState\"", QML)
        self.assertIn("objectName: \"canopyNotificationDisclosure\"", QML)
        self.assertIn("objectName: \"canopyNotificationRow\"", QML)

    def test_no_privileged_host_action_in_the_panel(self):
        for forbidden in ("suspend", "lock", "toggle_wifi", "toggle_mute",
                          "QProcess", "launch("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, QML)


class CompiledShellWiringTests(unittest.TestCase):
    def test_qml_module_registers_the_component(self):
        self.assertIn("NotificationCenter.qml", CMAKE)
        self.assertRegex(CMAKE, r"QML_FILES[^\n]*NotificationCenter\.qml")

    def test_main_qml_instantiates_hidden_overlay_and_local_shortcut(self):
        self.assertIn("NotificationCenter {", MAIN_QML)
        self.assertIn("controller: typeof canopyNotificationSource", MAIN_QML)
        self.assertIn("sequence: \"Ctrl+Alt+N\"", MAIN_QML)
        self.assertIn("onActivated: notificationCenter.toggleCenter()", MAIN_QML)

    def test_host_boundary_is_registered_but_disconnected_and_empty(self):
        self.assertIn("class NotificationHostSource final : public QObject", MAIN_CPP)
        self.assertIn("Q_INVOKABLE bool connected() const { return false; }", MAIN_CPP)
        self.assertIn("Q_INVOKABLE QVariantList snapshot() const { return QVariantList(); }",
                      MAIN_CPP)
        self.assertIn("setContextProperty(\n        QStringLiteral(\"canopyNotificationSource\")",
                      MAIN_CPP)

    def test_compiled_scene_self_test_exists(self):
        self.assertIn("static bool verifyNotificationCenterScene(", MAIN_CPP)
        self.assertIn("--self-test-notification-center", MAIN_CPP)
        self.assertIn("NOTIFICATION_CENTER_FIXTURE_PASS", MAIN_CPP)
        self.assertIn("SELF_TEST_PASS: notification centre registered and fail closed",
                      MAIN_CPP)
        self.assertIn("notification rows were fabricated without a host source", MAIN_CPP)
        self.assertIn("refresh control enabled without a connected host source", MAIN_CPP)

    def test_existing_visual_contract_is_not_redefined(self):
        self.assertEqual(MAIN_CPP.count("Ctrl+Alt+N"), 0)
        self.assertNotIn("notificationCenter.visible = true", MAIN_CPP)


if __name__ == "__main__":
    unittest.main()
