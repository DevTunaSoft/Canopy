"""Fail-closed quick-controls regression tests.

These are pure-Python policy tests plus QML source contracts. They do not
compile Qt, instantiate a window, observe a real network/audio/power/session,
or perform any host action. See docs/classic-quick-controls-workstream.md.
"""
import ast
import json
import unittest
from pathlib import Path

from canopy_features.reliability.lock_session_events import SessionState
from canopy_features.system.quick_controls_state import (
    ACTIONS,
    AVAILABLE,
    DISCLOSURES,
    DOMAINS,
    REASON_BRIDGE_DISABLED,
    REASON_INVALID_ACTION,
    REASON_INVALID_DOMAIN,
    REASON_NO_HOST_INTERFACE,
    REASON_OK,
    REASON_PRIVILEGED_HOST_CHANGE,
    Grant,
    HostInterfaces,
    Observation,
    QuickControlsState,
    QuickControlsStateError,
    empty_state,
    observation_from_session,
)

ROOT = Path(__file__).resolve().parents[1]
QML = (ROOT / "prototype" / "classic" / "QuickControlsOverlay.qml").read_text(
    encoding="utf-8")
MODEL_SOURCE = (ROOT / "canopy_features" / "system"
                / "quick_controls_state.py").read_text(encoding="utf-8")


class DefaultFailClosedTests(unittest.TestCase):
    def test_empty_state_has_four_known_domains(self):
        self.assertEqual(DOMAINS, ("network", "audio", "power", "session"))
        snapshot = empty_state().snapshot()
        self.assertEqual(tuple(snapshot), DOMAINS)
        for domain, view in snapshot.items():
            with self.subTest(domain=domain):
                self.assertEqual(view.status, "unknown")
                self.assertFalse(view.observed)
                self.assertEqual(view.source, "none")
                self.assertEqual(view.availability, "UNAVAILABLE")
                self.assertFalse(view.control.allowed)
                self.assertFalse(view.settings.allowed)

    def test_empty_state_control_reasons_are_stable(self):
        state = empty_state()
        self.assertEqual(state.view("network").control.reason,
                         REASON_NO_HOST_INTERFACE)
        for domain in ("power", "session"):
            with self.subTest(domain=domain):
                self.assertEqual(state.view(domain).control.reason,
                                 REASON_PRIVILEGED_HOST_CHANGE)

    def test_unknown_domain_and_action_fail_closed_without_raising(self):
        state = empty_state()
        self.assertEqual(state.view("bluetooth").domain, "unknown")
        self.assertEqual(state.view(7).control.reason, REASON_INVALID_DOMAIN)
        self.assertEqual(state.decide("network", "reboot").reason,
                         REASON_INVALID_ACTION)
        self.assertEqual(state.decide(["network"], "toggle_wifi").reason,
                         REASON_INVALID_DOMAIN)
        self.assertEqual(state.decide("network", None).reason,
                         REASON_INVALID_ACTION)

    def test_disclosures_are_fixed_and_never_echo_caller_text(self):
        for reason, text in DISCLOSURES.items():
            with self.subTest(reason=reason):
                self.assertIsInstance(text, str)
                if reason == REASON_OK:
                    self.assertEqual(text, "Available")
                else:
                    self.assertIn("Unavailable", text)
                state = empty_state()
                self.assertEqual(state.decide("network", "bogus").disclosure,
                                 DISCLOSURES[REASON_INVALID_ACTION])
        self.assertNotIn("<script>", json.dumps(
            empty_state().to_dict(), ensure_ascii=True))

    def test_to_dict_is_json_serializable_bounded_and_frozen_at_source(self):
        payload = empty_state().to_dict()
        self.assertEqual(len(payload), 4)
        self.assertEqual(set(payload), set(DOMAINS))
        self.assertLess(len(json.dumps(payload, ensure_ascii=True)), 8192)
        self.assertIsInstance(payload["network"]["control"]["allowed"], bool)
        with self.assertRaises(TypeError):
            empty_state().snapshot()["network"] = None


class ObservationTests(unittest.TestCase):
    def test_valid_status_tokens_for_each_domain(self):
        state = QuickControlsState(observations=(
            Observation("network", "connected"),
            Observation("audio", "muted"),
            Observation("power", "discharging"),
            Observation("session", "locked", "host-events"),
        ))
        self.assertEqual(state.view("network").status_label, "Connected")
        self.assertEqual(state.view("audio").status_label, "Muted")
        self.assertEqual(state.view("power").status_label, "On battery")
        self.assertEqual(state.view("session").status_label, "Locked")
        self.assertEqual(state.view("session").source, "host-events")
        self.assertTrue(all(view.observed for view in state.snapshot().values()))

    def test_unknown_status_token_is_rejected(self):
        with self.assertRaises(QuickControlsStateError):
            Observation("network", "connected-to-mars")

    def test_wrong_types_are_rejected(self):
        for args in (("network", 1), (7, "connected"), (None, "connected")):
            with self.subTest(args=args), self.assertRaises(QuickControlsStateError):
                Observation(*args)
        with self.assertRaises(QuickControlsStateError):
            Observation("session", "locked", 123)
        with self.assertRaises(QuickControlsStateError):
            Observation("session", "locked", "bad source")

    def test_oversized_and_non_ascii_sources_are_rejected(self):
        with self.assertRaises(QuickControlsStateError):
            Observation("audio", "muted", "s" * 65)
        with self.assertRaises(QuickControlsStateError):
            Observation("audio", "muted", "hôst")

    def test_duplicate_domain_observation_is_rejected(self):
        with self.assertRaises(QuickControlsStateError):
            QuickControlsState(observations=(
                Observation("network", "connected"),
                Observation("network", "disconnected"),
            ))

    def test_wrong_observation_container_is_rejected(self):
        for value in (None, {}, iter(()), 7):
            with self.subTest(value=value), self.assertRaises(QuickControlsStateError):
                QuickControlsState(observations=value)
        with self.assertRaises(QuickControlsStateError):
            QuickControlsState(observations=(("network", "connected"),))

    def test_observe_returns_new_state_without_mutating_original(self):
        before = empty_state()
        after = before.observe(Observation("audio", "unmuted"))
        self.assertFalse(before.view("audio").observed)
        self.assertTrue(after.view("audio").observed)
        replaced = after.observe(Observation("audio", "muted"))
        self.assertEqual(replaced.view("audio").status, "muted")
        self.assertEqual(after.view("audio").status, "unmuted")

    def test_session_state_reuses_existing_lock_session_contract(self):
        self.assertEqual(observation_from_session(
            SessionState(False, True)).status, "locked")
        self.assertEqual(observation_from_session(
            SessionState(True, True)).status, "suspended")
        self.assertEqual(observation_from_session(
            SessionState(False, False)).status, "active")
        with self.assertRaises(QuickControlsStateError):
            observation_from_session({"suspended": False, "locked": False})
        with self.assertRaises(ValueError):
            SessionState(True, False)


class GrantAndBridgeTests(unittest.TestCase):
    def test_settings_bridge_is_the_only_action_available_by_default(self):
        state = QuickControlsState(
            interfaces=HostInterfaces(settings_bridge=True))
        for domain in DOMAINS:
            with self.subTest(domain=domain):
                self.assertEqual(state.decide(domain, "open_settings").reason,
                                 REASON_OK)
                self.assertFalse(state.view(domain).control.allowed)

    def test_direct_control_needs_grant_and_matching_bridge(self):
        grant = Grant("network", frozenset({"toggle_wifi"}))
        denied = QuickControlsState(grants=(grant,))
        self.assertEqual(denied.view("network").control.reason,
                         REASON_BRIDGE_DISABLED)
        allowed = QuickControlsState(
            interfaces=HostInterfaces(network_control_bridge=True),
            grants=(grant,))
        self.assertTrue(allowed.view("network").control.allowed)
        self.assertFalse(allowed.view("audio").control.allowed)
        audio = QuickControlsState(
            interfaces=HostInterfaces(audio_control_bridge=True),
            grants=(Grant("audio", frozenset({"toggle_mute"})),))
        self.assertTrue(audio.view("audio").control.allowed)

    def test_privileged_actions_are_never_allowed(self):
        for domain, action in (("power", "suspend"), ("session", "lock")):
            with self.subTest(domain=domain):
                state = QuickControlsState(
                    interfaces=HostInterfaces(
                        settings_bridge=True,
                        network_control_bridge=True,
                        audio_control_bridge=True),
                    grants=(Grant(domain, frozenset({action})),))
                decision = state.decide(domain, action)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason,
                                 REASON_PRIVILEGED_HOST_CHANGE)
                self.assertIn("privileged", decision.disclosure)

    def test_grant_validation_is_strict(self):
        with self.assertRaises(QuickControlsStateError):
            Grant("network", {"toggle_wifi"})
        with self.assertRaises(QuickControlsStateError):
            Grant("network", frozenset({"reboot"}))
        with self.assertRaises(QuickControlsStateError):
            Grant("bluetooth", frozenset())
        with self.assertRaises(QuickControlsStateError):
            Grant("network", frozenset({7}))
        with self.assertRaises(QuickControlsStateError):
            QuickControlsState(grants=(Grant("audio", frozenset()),) * 2)

    def test_host_interfaces_require_exact_bools(self):
        for value in (1, "true", None):
            with self.subTest(value=value), self.assertRaises(QuickControlsStateError):
                HostInterfaces(settings_bridge=value)
        with self.assertRaises(QuickControlsStateError):
            QuickControlsState(interfaces={"settings_bridge": True})

    def test_no_service_process_or_privileged_api_in_policy(self):
        tree = ast.parse(MODEL_SOURCE)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in ("subprocess", "socket", "os", "shutil", "asyncio",
                          "threading", "multiprocessing", "signal", "ctypes"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, imported)
        code_only = "\n".join(
            line for line in MODEL_SOURCE.splitlines()
            if not line.lstrip().startswith("#")
        )
        for forbidden in ("QProcess", "pkexec", "sudo ", "systemctl"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code_only)
        self.assertEqual(ACTIONS, frozenset({
            "open_settings", "toggle_wifi", "toggle_mute", "suspend", "lock"}))


class QmlOverlayContractTests(unittest.TestCase):
    def test_overlay_is_self_contained_and_fail_closed(self):
        self.assertIn('objectName: "canopyQuickControlsOverlay"', QML)
        self.assertIn('readonly property var domains: ["network", "audio", '
                      '"power", "session"]', QML)
        self.assertIn("property var controller: null", QML)
        self.assertIn("property var actionBridge: null", QML)
        self.assertIn('status: "unknown"', QML)
        self.assertIn('availability: ready ? "AVAILABLE" : "UNAVAILABLE"', QML)
        self.assertIn("Unknown — no host status", QML)
        self.assertIn("Unavailable — no host control interface", QML)
        self.assertIn("Unavailable — privileged host changes are not performed",
                      QML)
        self.assertIn("signal controlRequested(string domain, string action)", QML)
        self.assertIn("signal settingsLaunchFailed(string domain)", QML)

    def test_settings_use_existing_host_bridge_only(self):
        self.assertIn('typeof canopySystemLaunchEnabled !== "undefined"', QML)
        self.assertIn('typeof canopySystemLauncher !== "undefined"', QML)
        self.assertIn('canopySystemLauncher.canLaunch(settingsApp)', QML)
        self.assertIn('canopySystemLauncher.launch(settingsApp)', QML)
        for forbidden in ("Qt.createQmlObject", "Process {", "QProcess",
                          "NetworkRequest", "Timer {", "XmlHttp",
                          "Qt.openUrlExternally"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, QML)

    def test_every_visible_control_has_a_named_action_or_disclosure(self):
        for name in ("canopyQuickControlRow", "canopyQuickStatus",
                     "canopyQuickDisclosure", "canopyQuickSettingsButton",
                     "canopyQuickControlButton", "canopyQuickControlsMessage"):
            with self.subTest(name=name):
                self.assertIn('objectName: "%s"' % name, QML)
        self.assertIn("enabled: quickControls.canOpenSettings(modelData)", QML)
        self.assertIn("enabled: quickControls.canControl(modelData)", QML)
        self.assertIn("Accessible.description: quickControls.disclosureFor(modelData)",
                      QML)
        self.assertIn("Keys.onEscapePressed: quickControls.closeControls()", QML)
        self.assertIn("function canControl(domain)", QML)
        self.assertIn("function canOpenSettings(domain)", QML)

    def test_python_and_qml_disclosures_agree(self):
        for reason in (REASON_NO_HOST_INTERFACE, REASON_BRIDGE_DISABLED,
                       REASON_PRIVILEGED_HOST_CHANGE, REASON_OK):
            with self.subTest(reason=reason):
                self.assertIn(DISCLOSURES[reason], QML)


if __name__ == "__main__":
    unittest.main()
