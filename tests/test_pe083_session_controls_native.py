"""PE-083: bounded native host-event path for logout/shutdown contracts.

Targeted, offline-only tests. No real logout, reboot, VM, D-Bus, credential,
process, Qt runtime or host observation is used. Every event and grant here is
a synthetic in-memory object supplied by the test.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from canopy_core.host_events import PROTOCOL_VERSION, TOPICS, HostEvent
from canopy_features.system import quick_controls_state as qcs

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "canopy_features" / "system" / "session_controls_native.py"


def contract():
    """Import lazily so an absent contract is a fast, explicit RED."""
    from canopy_features.system import session_controls_native
    return session_controls_native


def event(m, sequence, state="active", *, topic=None, version=None):
    """Build a real protocol-v2 HostEvent with the documented session field."""
    return HostEvent(
        version=m.PROTOCOL_VERSION if version is None else version,
        topic=m.SESSION_TOPIC if topic is None else topic,
        sequence=sequence,
        fields=(("state", state),),
    )


def capability(m, *, interface="logind", action="logout", available=True):
    return m._controls.NativeCapability(interface=interface, action=action,
                                        available=available, source="host")


def confirmation(m, *, interface="logind", action="logout", confirmed=True):
    return m._controls.Confirmation(interface=interface, action=action,
                                    confirmed=confirmed, source="user")


def ready(m, action="logout"):
    """Return a gate with a trusted active observation and matching grant."""
    path = m.SessionControlsNativePath()
    result = path.submit(event(m, 1, "active"))
    assert result.accepted
    path.drain()
    return path, capability(m, action=action), confirmation(m, action=action)


class ProtocolBoundaryTests(unittest.TestCase):
    def test_no_new_topic_or_protocol_version(self):
        m = contract()
        self.assertEqual(TOPICS, frozenset({
            "app.catalog.changed", "window.state.changed",
            "session.state.changed", "capabilities.report",
        }))
        self.assertEqual(m.PROTOCOL_VERSION, PROTOCOL_VERSION)
        self.assertIn(m.SESSION_TOPIC, TOPICS)
        self.assertEqual(m.SESSION_TOPIC, "session.state.changed")
        self.assertEqual(m.SESSION_STATUS, qcs.STATUS_TOKENS["session"])

    def test_status_vocabulary_is_reused_not_extended(self):
        m = contract()
        self.assertEqual(m.STATUS_ACTIVE, "active")
        self.assertEqual(m.SESSION_STATUS,
                         frozenset({"active", "locked", "suspended", "unknown"}))

    def test_module_has_no_execution_or_transport_imports(self):
        m = contract()
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {"os", "sys", "subprocess", "socket", "shutil", "signal",
                     "threading", "asyncio", "dbus", "time"}
        self.assertFalse(imported & forbidden)
        source = MODULE_PATH.read_text(encoding="utf-8")
        for token in ("systemctl", "loginctl", "os.system", "Popen", "exec("):
            self.assertNotIn(token, source)
        self.assertIn(m._controls.__name__, "canopy_features.system.session_controls")


class FailClosedStateTests(unittest.TestCase):
    def test_no_observation_denies_with_stable_disclosure(self):
        m = contract()
        path = m.SessionControlsNativePath()
        decision = path.decide("logout", capability(m), confirmation(m))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_NO_HOST_OBSERVATION)
        self.assertIsNone(decision.path)
        self.assertEqual(decision.disclosure, m.DISCLOSURES[decision.reason])
        self.assertEqual(path.availability, m.UNAVAILABLE)
        self.assertIn("no host status observation", decision.disclosure)

    def test_active_observation_with_matching_grant_allows_inert_path(self):
        m = contract()
        path, cap, conf = ready(m)
        decision = path.decide("logout", cap, conf)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_OK)
        self.assertEqual(decision.path.action, "logout")
        self.assertEqual(decision.path.interface, "logind")
        payload = decision.to_dict()
        self.assertFalse(payload["executed"])
        self.assertEqual(payload["execution"], "host-only-not-performed")
        self.assertNotIn("argv", payload)
        self.assertNotIn("command", payload)
        self.assertNotIn("argv", payload["path"])
        self.assertNotIn("command", payload["path"])

    def test_shutdown_is_a_decision_not_an_execution(self):
        m = contract()
        path, cap, conf = ready(m, "shutdown")
        decision = path.decide("shutdown", cap, conf)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.path.action, "shutdown")
        self.assertEqual(decision.to_dict()["executed"], False)

    def test_session_manager_cannot_shutdown(self):
        m = contract()
        path, _, _ = ready(m, "shutdown")
        decision = path.decide(
            "shutdown",
            capability(m, interface="session-manager", action="shutdown"),
            confirmation(m, interface="session-manager", action="shutdown"),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_NO_HOST_INTERFACE)

    def test_locked_session_denies_privileged_action(self):
        m = contract()
        path = m.SessionControlsNativePath()
        path.submit(event(m, 1, "locked"))
        path.drain()
        decision = path.decide("logout", capability(m), confirmation(m))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_SESSION_NOT_ACTIVE)
        self.assertIsNone(decision.path)

    def test_suspended_session_denies_privileged_action(self):
        m = contract()
        path = m.SessionControlsNativePath()
        path.submit(event(m, 1, "suspended"))
        path.drain()
        decision = path.decide("shutdown", capability(m, action="shutdown"),
                               confirmation(m, action="shutdown"))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_SESSION_NOT_ACTIVE)

    def test_unknown_status_denies_privileged_action(self):
        m = contract()
        path = m.SessionControlsNativePath()
        path.submit(event(m, 1, "unknown"))
        path.drain()
        decision = path.decide("logout", capability(m), confirmation(m))
        self.assertFalse(decision.allowed)
        # An explicit unknown observation still carries the no-observation
        # disclosure; it never becomes an offerable control.
        self.assertEqual(decision.reason, m.REASON_NO_HOST_OBSERVATION)

    def test_active_after_lock_requires_explicit_reobservation(self):
        m = contract()
        path = m.SessionControlsNativePath()
        path.submit(event(m, 1, "locked"))
        path.drain()
        path.submit(event(m, 2, "active"))
        path.drain()
        decision = path.decide("logout", capability(m), confirmation(m))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_REOBSERVATION)
        path.reobserve_ready()
        self.assertTrue(path.decide("logout", capability(m), confirmation(m)).allowed)

    def test_reobservation_ack_cannot_override_a_nonactive_session(self):
        m = contract()
        path = m.SessionControlsNativePath()
        path.submit(event(m, 1, "locked"))
        path.drain()
        path.reobserve_ready()
        decision = path.decide("logout", capability(m), confirmation(m))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_SESSION_NOT_ACTIVE)


class GrantTests(unittest.TestCase):
    def test_raw_command_candidate_is_refused_even_when_ready(self):
        m = contract()
        path, cap, conf = ready(m)
        decision = path.decide("logout", cap, conf,
                               command_candidate=["/bin/true"])
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_RAW_COMMAND_REFUSED)
        self.assertIsNone(decision.path)

    def test_explicit_none_is_a_command_candidate_and_is_refused(self):
        m = contract()
        path, cap, conf = ready(m)
        decision = path.decide("logout", cap, conf, command_candidate=None)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_RAW_COMMAND_REFUSED)

    def test_unconfirmed_grant_is_denied(self):
        m = contract()
        path, _, _ = ready(m)
        decision = path.decide("logout", capability(m),
                               confirmation(m, confirmed=False))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_UNCONFIRMED)

    def test_mismatched_interface_is_denied(self):
        m = contract()
        path, _, _ = ready(m)
        decision = path.decide(
            "logout", capability(m, interface="logind"),
            confirmation(m, interface="session-manager"))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_INVALID_GRANT)

    def test_unavailable_capability_is_denied(self):
        m = contract()
        path, _, _ = ready(m)
        decision = path.decide("logout", capability(m, available=False),
                               confirmation(m))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_BRIDGE_DISABLED)

    def test_unsupported_action_returns_stable_invalid_action(self):
        m = contract()
        path, _, _ = ready(m)
        decision = path.decide("reboot", capability(m), confirmation(m))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_INVALID_ACTION)

    def test_wrong_capability_type_raises_domain_error(self):
        m = contract()
        path, _, conf = ready(m)
        with self.assertRaises(m.SessionControlsNativeError):
            path.decide("logout", {"interface": "logind"}, conf)

    def test_wrong_confirmation_type_raises_domain_error(self):
        m = contract()
        path, cap, _ = ready(m)
        with self.assertRaises(m.SessionControlsNativeError):
            path.decide("logout", cap, True)


class EventEnvelopeTests(unittest.TestCase):
    def test_wrong_event_type_is_a_domain_error(self):
        m = contract()
        path = m.SessionControlsNativePath()
        with self.assertRaises(m.SessionControlsNativeError):
            path.submit({"topic": m.SESSION_TOPIC})

    def test_wrong_topic_is_a_domain_error_and_fails_closed(self):
        m = contract()
        path = m.SessionControlsNativePath()
        with self.assertRaises(m.SessionControlsNativeError):
            path.submit(event(m, 1, topic="capabilities.report"))
        self.assertEqual(path.reason, m.REASON_HOST_UNAVAILABLE)

    def test_wrong_version_is_a_domain_error(self):
        m = contract()
        path = m.SessionControlsNativePath()
        with self.assertRaises(m.SessionControlsNativeError):
            path.submit(event(m, 1, version=1))

    def test_bool_sequence_is_rejected(self):
        m = contract()
        path = m.SessionControlsNativePath()
        with self.assertRaises(m.SessionControlsNativeError):
            path.submit(event(m, True))

    def test_negative_sequence_is_rejected(self):
        m = contract()
        path = m.SessionControlsNativePath()
        with self.assertRaises(m.SessionControlsNativeError):
            path.submit(event(m, -1))

    def test_invalid_state_at_drain_loses_the_boundary(self):
        m = contract()
        path = m.SessionControlsNativePath()
        path.submit(event(m, 1, "active\nhostile"))
        report = path.drain()
        self.assertEqual(report.processed, 0)
        self.assertEqual(path.reason, m.REASON_HOST_UNAVAILABLE)
        self.assertEqual(path.status, "unknown")
        self.assertIn("invalid-observation", path.view()["history"])

    def test_missing_state_field_at_drain_loses_the_boundary(self):
        m = contract()
        path = m.SessionControlsNativePath()
        path.submit(HostEvent(PROTOCOL_VERSION, m.SESSION_TOPIC, 1, ()))
        path.drain()
        self.assertEqual(path.reason, m.REASON_HOST_UNAVAILABLE)

    def test_stale_sequence_cannot_regress_active_state(self):
        m = contract()
        path = m.SessionControlsNativePath()
        path.submit(event(m, 2, "active"))
        path.drain()
        path.submit(event(m, 1, "locked"))
        report = path.drain()
        self.assertEqual(report.ignored, 1)
        self.assertEqual(path.status, "active")
        self.assertTrue(path.decide("logout", capability(m), confirmation(m)).allowed)

    def test_duplicate_sequence_is_ignored(self):
        m = contract()
        path = m.SessionControlsNativePath()
        path.submit(event(m, 1, "active"))
        path.drain()
        path.submit(event(m, 1, "locked"))
        report = path.drain()
        self.assertEqual(report.ignored, 1)
        self.assertEqual(path.status, "active")

    def test_drain_is_bounded_by_limit(self):
        m = contract()
        path = m.SessionControlsNativePath()
        for sequence, state in ((1, "unknown"), (2, "locked"),
                                (3, "suspended"), (4, "active")):
            path.submit(event(m, sequence, state))
        report = path.drain(limit=2)
        self.assertLessEqual(report.processed, 2)
        self.assertEqual(report.pending, 2)

    def test_drain_rejects_bool_and_oversized_limits(self):
        m = contract()
        path = m.SessionControlsNativePath()
        for bad in (True, 0, m.MAX_DRAIN + 1, "2"):
            with self.assertRaises(m.SessionControlsNativeError):
                path.drain(limit=bad)


class BoundedBatchTests(unittest.TestCase):
    def test_submit_many_consumes_at_most_the_batch_ceiling(self):
        m = contract()
        path = m.SessionControlsNativePath(max_pending=8)
        seen = []

        def events():
            for index in range(100):  # finite: never an unbounded RED input
                seen.append(index)
                yield event(m, index + 1, "active")

        result = path.submit_many(events())
        # The instance bound is lower than the module ceiling; consumption
        # must follow the instance, not the hard ceiling.
        self.assertEqual(len(seen), 8)
        self.assertLessEqual(8, m.MAX_BATCH)
        self.assertEqual(result.consumed, 8)
        self.assertEqual(result.queued, 8)
        self.assertEqual(result.rejected, 0)
        self.assertFalse(result.stopped)

    def test_submit_many_rejects_scalar_and_mapping(self):
        m = contract()
        path = m.SessionControlsNativePath()
        for bad in ("active", b"active", {"state": "active"}, 7):
            with self.assertRaises(m.SessionControlsNativeError):
                path.submit_many(bad)

    def test_submit_many_stops_and_fails_closed_on_bad_event(self):
        m = contract()
        path = m.SessionControlsNativePath()
        batch = (event(m, 1, "active"),
                 event(m, 2, topic="capabilities.report"),
                 event(m, 3, "active"))
        result = path.submit_many(batch)
        self.assertTrue(result.stopped)
        self.assertEqual(result.consumed, 2)
        self.assertEqual(path.reason, m.REASON_HOST_UNAVAILABLE)

    def test_reject_new_overflow_fails_closed(self):
        m = contract()
        path = m.SessionControlsNativePath(max_pending=2)
        path.submit(event(m, 1, "active"))
        path.submit(event(m, 2, "active"))
        result = path.submit(event(m, 3, "active"))
        self.assertFalse(result.accepted)
        self.assertEqual(result.status, m.REJECTED)
        self.assertEqual(path.reason, m.REASON_HOST_UNAVAILABLE)
        self.assertEqual(path.view()["pending"], 0)

    def test_drop_oldest_overflow_also_fails_closed(self):
        m = contract()
        path = m.SessionControlsNativePath(max_pending=2,
                                           overflow_policy="drop_oldest")
        path.submit(event(m, 1, "active"))
        path.submit(event(m, 2, "active"))
        result = path.submit(event(m, 3, "active"))
        self.assertTrue(result.accepted)
        self.assertEqual(result.status, m.DROPPED_OLDEST)
        self.assertEqual(path.reason, m.REASON_HOST_UNAVAILABLE)
        self.assertEqual(path.view()["pending"], 0)

    def test_bounds_cannot_be_raised_above_ceiling(self):
        m = contract()
        for kwargs in ({"max_pending": m.MAX_PENDING + 1},
                       {"max_drain": m.MAX_DRAIN + 1},
                       {"overflow_policy": "ignore"}):
            with self.assertRaises(m.SessionControlsNativeError):
                m.SessionControlsNativePath(**kwargs)


class BoundaryLifecycleTests(unittest.TestCase):
    def test_host_unavailable_clears_queued_events(self):
        m = contract()
        path, cap, conf = ready(m)
        path.submit(event(m, 2, "active"))
        path.mark_host_unavailable()
        self.assertEqual(path.view()["pending"], 0)
        self.assertEqual(path.reason, m.REASON_HOST_UNAVAILABLE)
        self.assertFalse(path.decide("logout", cap, conf).allowed)

    def test_mark_host_available_alone_does_not_restore_offers(self):
        m = contract()
        path, cap, conf = ready(m)
        path.mark_host_unavailable()
        self.assertTrue(path.mark_host_available())
        self.assertFalse(path.decide("logout", cap, conf).allowed)
        self.assertEqual(path.reason, m.REASON_REOBSERVATION)

    def test_late_event_after_boundary_loss_cannot_resurrect_active(self):
        m = contract()
        path, cap, conf = ready(m)
        path.mark_host_unavailable()
        path.mark_host_available()
        path.submit(event(m, 1, "active"))  # stale relative to kept sequence
        path.drain()
        self.assertFalse(path.decide("logout", cap, conf).allowed)
        path.submit(event(m, 2, "active"))
        path.drain()
        self.assertFalse(path.decide("logout", cap, conf).allowed)
        path.reobserve_ready()
        self.assertTrue(path.decide("logout", cap, conf).allowed)

    def test_fresh_observation_after_loss_still_needs_ack(self):
        m = contract()
        path, cap, conf = ready(m)
        path.mark_host_unavailable()
        path.mark_host_available()
        path.submit(event(m, 2, "active"))
        path.drain()
        decision = path.decide("logout", cap, conf)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_REOBSERVATION)

    def test_close_is_irreversible_and_fails_closed(self):
        m = contract()
        path, cap, conf = ready(m)
        path.close()
        path.close()
        self.assertEqual(path.reason, m.REASON_CLOSED)
        self.assertFalse(path.decide("logout", cap, conf).allowed)
        with self.assertRaises(m.SessionControlsNativeError):
            path.submit(event(m, 2, "active"))
        with self.assertRaises(m.SessionControlsNativeError):
            path.mark_host_available()
        with self.assertRaises(m.SessionControlsNativeError):
            path.reobserve_ready()

    def test_history_and_stats_are_bounded(self):
        m = contract()
        path = m.SessionControlsNativePath()
        for _ in range(m.MAX_HISTORY + 10):
            path.mark_host_unavailable()
            path.mark_host_available()
        view = path.view()
        self.assertLessEqual(len(view["history"]), m.MAX_HISTORY)
        self.assertTrue(all(isinstance(v, int) for v in view["counts"].values()))
        self.assertEqual(path.stats["boundary_losses"], m.MAX_HISTORY + 10)

    def test_view_is_read_only_with_fixed_keys(self):
        m = contract()
        path = m.SessionControlsNativePath()
        view = path.view()
        with self.assertRaises(TypeError):
            view["status"] = "active"
        self.assertEqual(tuple(view), (
            "boundary", "closed", "reobservation_required", "status",
            "sequence", "pending", "overflow_policy", "availability",
            "reason", "disclosure", "history", "counts",
        ))

    def test_snapshots_contain_no_command_or_credential_fields(self):
        m = contract()
        path, cap, conf = ready(m)
        rendered = json.dumps({
            "decision": path.decide("logout", cap, conf).to_dict(),
            "view": path.to_dict(),
            "stats": dict(path.stats),
        })
        for token in ("argv", "command", "password", "credential", "token",
                      "secret", "systemctl", "loginctl"):
            self.assertNotIn(token, rendered)

    def test_reason_disclosures_are_caller_independent(self):
        m = contract()
        path = m.SessionControlsNativePath()
        before = path.disclosure
        path.submit(event(m, 1, "junk-value"))
        path.drain()
        self.assertEqual(before, m.DISCLOSURES[m.REASON_NO_HOST_OBSERVATION])
        self.assertEqual(path.disclosure, m.DISCLOSURES[m.REASON_HOST_UNAVAILABLE])
        self.assertNotIn("junk-value", path.disclosure)


class ReconciledStateTests(unittest.TestCase):
    def test_existing_reconciled_locked_state_denies(self):
        m = contract()
        from canopy_features.reliability.lock_session_events import SessionState
        path = m.SessionControlsNativePath()
        path.observe_session_state(SessionState(suspended=False, locked=True))
        decision = path.decide("logout", capability(m), confirmation(m))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_SESSION_NOT_ACTIVE)

    def test_reconciled_active_after_suspended_requires_ack(self):
        m = contract()
        from canopy_features.reliability.lock_session_events import SessionState
        path = m.SessionControlsNativePath()
        path.observe_session_state(SessionState(suspended=True, locked=True))
        path.observe_session_state(SessionState(suspended=False, locked=False))
        decision = path.decide("logout", capability(m), confirmation(m))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, m.REASON_REOBSERVATION)
        path.reobserve_ready()
        self.assertTrue(path.decide("logout", capability(m), confirmation(m)).allowed)

    def test_forged_reconciled_state_subclass_is_refused(self):
        m = contract()
        from canopy_features.reliability.lock_session_events import SessionState

        class Forged(SessionState):
            pass

        path = m.SessionControlsNativePath()
        with self.assertRaises(m.SessionControlsNativeError):
            path.observe_session_state(Forged(False, False))


if __name__ == "__main__":
    unittest.main()
