"""PE-048: fail-closed native-path session control contract tests.

No VM, D-Bus, session manager, power command, Qt runtime or real host
capability is used. All facts are synthetic objects supplied by the test.
The contract under test only decides and describes; it never executes.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from canopy_core.host_events import TOPICS
from canopy_features.security import privilege_boundary
from canopy_features.system import quick_controls_state as qcs

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "canopy_features" / "system" / "session_controls.py"
_UNSET = object()


def contract():
    """Import lazily so an absent contract is a fast, explicit RED."""
    from canopy_features.system import session_controls
    return session_controls


def capability(m, *, interface="logind", action="logout", available=True,
               source="host"):
    return m.NativeCapability(interface=interface, action=action,
                              available=available, source=source)


def confirmation(m, *, action="logout", interface="logind", confirmed=True,
                 source="user"):
    return m.Confirmation(action=action, interface=interface,
                          confirmed=confirmed, source=source)


def decision(m, *, action="logout", interface="logind", available=True,
             confirmed=True, command_candidate=_UNSET):
    kwargs = {}
    if command_candidate is not _UNSET:
        kwargs["command_candidate"] = command_candidate
    return m.evaluate_native_path(
        action,
        capability=capability(m, interface=interface, action=action,
                              available=available),
        confirmation=confirmation(m, action=action, interface=interface,
                                  confirmed=confirmed),
        **kwargs,
    )


class AllowedPathTests(unittest.TestCase):
    def test_logout_via_logind_produces_inert_native_path(self):
        m = contract()
        result = decision(m, action=m.ACTION_LOGOUT)
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, m.REASON_OK)
        self.assertIsNotNone(result.path)
        self.assertEqual(result.path.action, "logout")
        self.assertEqual(result.path.interface, "logind")
        payload = result.to_dict()
        self.assertFalse(payload["executed"])
        self.assertNotIn("argv", payload)
        self.assertNotIn("command", payload)
        self.assertNotIn("argv", payload["path"])
        self.assertNotIn("command", payload["path"])

    def test_shutdown_via_logind_is_a_decision_not_an_execution(self):
        m = contract()
        result = decision(m, action=m.ACTION_SHUTDOWN)
        self.assertTrue(result.allowed)
        self.assertEqual(result.path.interface, "logind")
        self.assertEqual(result.path.action, "shutdown")
        self.assertEqual(result.to_dict()["execution"], "host-only-not-performed")

    def test_session_manager_logout_is_supported_but_shutdown_is_not(self):
        m = contract()
        logout = decision(m, interface="session-manager", action=m.ACTION_LOGOUT)
        self.assertTrue(logout.allowed)
        shutdown = decision(m, interface="session-manager",
                            action=m.ACTION_SHUTDOWN)
        self.assertFalse(shutdown.allowed)
        self.assertEqual(shutdown.reason, qcs.REASON_NO_HOST_INTERFACE)
        self.assertIsNone(shutdown.path)

    def test_path_snapshot_is_fresh_and_immutable(self):
        m = contract()
        result = decision(m)
        first = result.to_dict()
        first["action"] = "mutated"
        first["interface"] = "mutated"
        second = result.to_dict()
        self.assertEqual(second["action"], "logout")
        self.assertEqual(second["interface"], "logind")
        with self.assertRaises(Exception):
            result.path.action = "mutated"

    def test_source_provenance_is_preserved_without_guessing(self):
        m = contract()
        result = m.evaluate_native_path(
            "logout",
            capability=capability(m, source="host-capability-report"),
            confirmation=confirmation(m, source="user-confirm-dialog"),
        )
        self.assertTrue(result.allowed)
        self.assertEqual(result.path.capability_source, "host-capability-report")
        self.assertEqual(result.path.confirmation_source, "user-confirm-dialog")


class FailClosedTests(unittest.TestCase):
    def test_unavailable_native_interface_is_refused(self):
        m = contract()
        result = decision(m, available=False)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, qcs.REASON_BRIDGE_DISABLED)
        self.assertIsNone(result.path)
        self.assertEqual(result.disclosure,
                         qcs.DISCLOSURES[qcs.REASON_BRIDGE_DISABLED])

    def test_missing_confirmation_is_refused(self):
        m = contract()
        result = decision(m, confirmed=False)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, m.REASON_UNCONFIRMED)
        self.assertIsNone(result.path)

    def test_mismatched_capability_action_is_refused(self):
        m = contract()
        result = m.evaluate_native_path(
            "shutdown",
            capability=capability(m, action="logout"),
            confirmation=confirmation(m, action="shutdown"),
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, qcs.REASON_INVALID_GRANT)

    def test_mismatched_confirmation_interface_is_refused(self):
        m = contract()
        result = m.evaluate_native_path(
            "logout",
            capability=capability(m, interface="logind"),
            confirmation=confirmation(m, interface="session-manager"),
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, qcs.REASON_INVALID_GRANT)

    def test_unknown_interface_is_refused_at_construction(self):
        m = contract()
        with self.assertRaises(m.SessionControlsError):
            capability(m, interface="unlisted-interface")
        with self.assertRaises(m.SessionControlsError):
            confirmation(m, interface="unlisted-interface")

    def test_invalid_action_never_inherits_a_path(self):
        m = contract()
        for action in ("suspend", "lock", "reboot", "", 7, None, ("logout",)):
            with self.subTest(action=action):
                result = m.evaluate_native_path(
                    action, capability=capability(m),
                    confirmation=confirmation(m))
                self.assertFalse(result.allowed)
                self.assertEqual(result.reason, qcs.REASON_INVALID_ACTION)
                self.assertIsNone(result.path)

    def test_wrong_capability_or_confirmation_type_raises_domain_error(self):
        m = contract()
        good_capability = capability(m)
        good_confirmation = confirmation(m)
        with self.assertRaises(m.SessionControlsError):
            m.evaluate_native_path("logout", capability={"available": True},
                                   confirmation=good_confirmation)
        with self.assertRaises(m.SessionControlsError):
            m.evaluate_native_path("logout", capability=good_capability,
                                   confirmation=True)

    def test_capability_fields_reject_hostile_types_and_bounds(self):
        m = contract()
        for kwargs in (
            {"interface": b"logind"},
            {"action": "logout\x00"},
            {"available": 1},
            {"source": "host/source with spaces"},
            {"source": "x" * 65},
            {"source": None},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(m.SessionControlsError):
                    capability(m, **kwargs)

    def test_confirmation_fields_reject_hostile_types(self):
        m = contract()
        for kwargs in (
            {"confirmed": 1},
            {"source": "user\nconfirm"},
            {"action": ["logout"]},
            {"interface": None},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(m.SessionControlsError):
                    confirmation(m, **kwargs)

    def test_direct_path_construction_is_validated(self):
        m = contract()
        with self.assertRaises(m.SessionControlsError):
            m.NativePath(action="logout", interface="logind",
                         capability_source="host", confirmation_source="bad\n")
        with self.assertRaises(m.SessionControlsError):
            m.NativePath(action="delete", interface="logind",
                         capability_source="host", confirmation_source="user")

    def test_decision_reason_is_always_a_known_disclosure(self):
        m = contract()
        for result in (decision(m), decision(m, available=False),
                       decision(m, confirmed=False),
                       decision(m, interface="session-manager",
                                action=m.ACTION_SHUTDOWN)):
            with self.subTest(reason=result.reason):
                self.assertIn(result.reason, m.DISCLOSURES)
                self.assertEqual(result.disclosure, m.DISCLOSURES[result.reason])
                self.assertFalse(result.to_dict()["executed"])


class RawCommandTests(unittest.TestCase):
    def test_raw_power_command_is_never_accepted(self):
        m = contract()
        result = decision(m, command_candidate=("shutdown", "-h", "now"))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, m.REASON_RAW_COMMAND_REFUSED)
        self.assertEqual(result.boundary_reason,
                         privilege_boundary.DENIED_SYSTEM_COMMAND)
        self.assertIsNone(result.path)

    def test_elevation_wrapper_is_never_accepted(self):
        m = contract()
        result = decision(m, command_candidate=("sudo", "loginctl", "poweroff"))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, m.REASON_RAW_COMMAND_REFUSED)
        self.assertEqual(result.boundary_reason,
                         privilege_boundary.DENIED_ELEVATION)

    def test_even_boundary_allowed_argv_is_refused_by_this_contract(self):
        m = contract()
        self.assertTrue(privilege_boundary.evaluate(("logout",), euid=None).allowed)
        result = decision(m, command_candidate=("logout",))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, m.REASON_RAW_COMMAND_REFUSED)

    def test_command_candidate_of_any_shape_fails_closed(self):
        m = contract()
        for candidate in ("shutdown", None, 7, {"argv": ["logout"]},
                          ["logout", None], object()):
            with self.subTest(candidate=type(candidate).__name__):
                result = decision(m, command_candidate=candidate)
                self.assertFalse(result.allowed)
                self.assertEqual(result.reason, m.REASON_RAW_COMMAND_REFUSED)
                self.assertIsNone(result.path)

    def test_refuse_command_candidate_is_public_and_returns_no_path(self):
        m = contract()
        for candidate in (("shutdown",), ("pkexec", "logout"), ("loginctl",)):
            with self.subTest(candidate=candidate[0]):
                result = m.refuse_command_candidate(candidate)
                self.assertFalse(result.allowed)
                self.assertEqual(result.reason, m.REASON_RAW_COMMAND_REFUSED)
                self.assertIsNone(result.path)


class ContractBoundaryTests(unittest.TestCase):
    def test_existing_host_topic_is_reused_not_extended(self):
        contract()
        self.assertEqual(len(TOPICS), 4)
        self.assertIn("session.state.changed", TOPICS)
        self.assertEqual(contract().SESSION_TOPIC, "session.state.changed")

    def test_module_has_no_process_io_clock_or_bus_surface(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        forbidden_calls = {"open", "system", "popen", "Popen", "run",
                           "socket", "Timer", "sleep", "poll", "emit",
                           "subscribe", "spawn"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, forbidden_calls)
        forbidden_imports = {"os", "subprocess", "socket", "time", "pathlib",
                             "threading", "datetime", "random"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], forbidden_imports)
            if isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                self.assertNotIn(root, forbidden_imports)

    def test_module_source_contains_no_raw_command_or_transport(self):
        source = "\n".join(
            line for line in MODULE_PATH.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#"))
        for token in ("subprocess", "os.environ", "pkexec", "sudo ",
                      "systemctl", "gdbus", "dbus-send", "Popen",
                      "QProcess", "socket.", "poweroff", "reboot"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_protocol_version_is_not_redefined(self):
        m = contract()
        self.assertEqual(m.PROTOCOL_VERSION, 2)
        self.assertIs(m.TOPICS, TOPICS)


if __name__ == "__main__":
    unittest.main()
