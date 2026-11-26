"""PE-068: fail-closed desktop focus/session recovery after shell restart.

Targeted tests for the pure source-contract boundary. No host, VM, Qt,
credential, visual asset or real desktop is touched.
"""
import unittest

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    TOPICS as HOST_TOPICS,
    HostEvent,
    HostEvents,
)
from canopy_features.reliability import desktop_focus_recovery_contract as contract

CAPABILITY_PAYLOAD = {
    "status": "CAPABILITY_REPORT",
    "schema": 1,
    "component_count": 8,
    "component_codes": "OK|READINESS_SNAPSHOT|SNAPSHOT|OK|OK|OK|OK|OK",
    "negative_claims": "desktop=not_claimed",
    "has_active_pack": False,
    "needs_recovery": True,
}


_BUS = None


def _new_bus():
    """Fresh trusted bus per test so bus sequences start at one."""
    global _BUS
    callbacks = {topic: [lambda event: None] for topic in contract.TOPICS}
    bus = HostEvents(callbacks)
    for topic, functions in callbacks.items():
        for function in functions:
            bus.subscribe(topic, function)
    _BUS = bus
    return bus


class _ContractTestCase(unittest.TestCase):
    def setUp(self):
        _new_bus()


def emit(topic, payload, sequence=None):
    """Emit through a real trusted bus and return the delivered HostEvent."""
    result = _BUS.emit(topic, payload)
    if sequence is not None and sequence != result.event.sequence:
        raise AssertionError("test helper sequence mismatch")
    return result.event


def capability(needs_recovery=True, has_active_pack=False, **extra):
    payload = dict(CAPABILITY_PAYLOAD)
    payload["needs_recovery"] = needs_recovery
    payload["has_active_pack"] = has_active_pack
    payload.update(extra)
    return emit(contract.CAPABILITY_TOPIC, payload)


def session(state, **extra):
    payload = {"state": state}
    payload.update(extra)
    return emit(contract.SESSION_TOPIC, payload)


def windows(count, **extra):
    payload = {"window_count": count}
    payload.update(extra)
    return emit(contract.WINDOW_TOPIC, payload)


def observed(event, source=contract.DEFAULT_SOURCE):
    return contract.from_host_event(event, source=source)


class ContractSurfaceTests(_ContractTestCase):
    def test_existing_topic_allowlist_is_unchanged(self):
        self.assertEqual(PROTOCOL_VERSION, 2)
        self.assertEqual(len(HOST_TOPICS), 4)
        self.assertTrue(contract.TOPICS.issubset(HOST_TOPICS))
        self.assertNotIn("shell.restart", HOST_TOPICS)
        self.assertEqual(
            set(contract.TOPICS),
            {"capabilities.report", "session.state.changed",
             "window.state.changed"},
        )

    def test_constants_are_fail_closed_defaults(self):
        self.assertEqual(contract.SCHEMA, 1)
        self.assertEqual(contract.DEFAULT_SOURCE, "host-events")
        self.assertEqual(contract.CLEARED, "cleared")
        self.assertEqual(contract.RESTART, "restart")
        self.assertEqual(contract.NO_RESTORE, "no_restore")
        self.assertEqual(contract.OFFER_RESTORE, "offer_restore")

    def test_observation_validation_fail_closed(self):
        with self.assertRaises(contract.RecoveryContractError):
            contract.RecoveryObservation("restart", True)
        with self.assertRaises(contract.RecoveryContractError):
            contract.RecoveryObservation("restart", 0)
        with self.assertRaises(contract.RecoveryContractError):
            contract.RecoveryObservation("fresh", 1)
        with self.assertRaises(contract.RecoveryContractError):
            contract.RecoveryObservation("restart", 1, "Bad Source")

    def test_outcome_transition_flags(self):
        reconciler = contract.Reconciler()
        restart = observed(capability())
        outcome = reconciler.observe(restart)
        self.assertTrue(outcome.transitioned)
        self.assertEqual(outcome.current, contract.AWAITING_SESSION)
        awaiting = reconciler.observe(observed(session("active")))
        self.assertTrue(awaiting.transitioned)
        self.assertEqual(awaiting.current, contract.AWAITING_WINDOWS)
        redundant = reconciler.observe(observed(session("active")))
        self.assertFalse(redundant.transitioned)
        self.assertEqual(redundant.status, contract.REDUNDANT)


class ProjectionTests(_ContractTestCase):
    def test_non_host_event_rejected(self):
        with self.assertRaises(contract.RecoveryContractError):
            contract.from_host_event({"topic": contract.SESSION_TOPIC})

    def test_wrong_version_rejected(self):
        event = HostEvent(1, contract.SESSION_TOPIC, 1,
                          (("state", "active"),))
        with self.assertRaises(contract.RecoveryContractError):
            observed(event)

    def test_wrong_topic_rejected(self):
        event = emit("app.catalog.changed", {"item_count": 1})
        with self.assertRaises(contract.RecoveryContractError):
            observed(event)

    def test_sequence_validation(self):
        for sequence in (0, -1, True, 1_000_000_000_001):
            with self.subTest(sequence=sequence):
                event = HostEvent(PROTOCOL_VERSION, contract.SESSION_TOPIC,
                                  sequence, (("state", "active"),))
                with self.assertRaises(contract.RecoveryContractError):
                    observed(event)

    def test_source_provenance(self):
        event = session("active", source=contract.DEFAULT_SOURCE)
        observation = observed(event)
        self.assertEqual(observation.source, contract.DEFAULT_SOURCE)
        with self.assertRaises(contract.RecoveryContractError):
            observed(event, source="alternate-host")
        for bad in ("", "Owner/Secret", "x" * 65, "\u202eactive"):
            with self.subTest(bad=bad):
                with self.assertRaises(contract.RecoveryContractError):
                    observed(session("active"), source=bad)

    def test_capability_restart_and_cleared(self):
        self.assertEqual(observed(capability()).kind, contract.RESTART)
        self.assertEqual(observed(capability(False)).kind, contract.CLEARED)

    def test_active_pack_with_recovery_required_is_contradictory(self):
        with self.assertRaises(contract.RecoveryContractError):
            observed(capability(needs_recovery=True, has_active_pack=True))

    def test_capability_wrong_types_fail_closed(self):
        for needs_recovery, has_active_pack in ((1, False), (True, 1),
                                                ("true", False)):
            with self.subTest(needs_recovery=needs_recovery):
                with self.assertRaises(contract.RecoveryContractError):
                    observed(capability(needs_recovery, has_active_pack))
        with self.assertRaises(contract.RecoveryContractError):
            observed(capability(status="CAPABILITY_REPORT.ECHO"))
        with self.assertRaises(contract.RecoveryContractError):
            observed(capability(schema=2))
        with self.assertRaises(contract.RecoveryContractError):
            observed(emit(contract.CAPABILITY_TOPIC,
                          {"status": "CAPABILITY_REPORT", "schema": 1,
                           "has_active_pack": False}))

    def test_session_states(self):
        self.assertEqual(observed(session("active")).kind,
                         contract.SESSION_ACTIVE)
        self.assertEqual(observed(session("locked")).kind,
                         contract.SESSION_INACTIVE)
        self.assertEqual(observed(session("suspended")).kind,
                         contract.SESSION_INACTIVE)

    def test_session_missing_or_unknown_state(self):
        self.assertEqual(observed(emit(contract.SESSION_TOPIC, {})).kind,
                         contract.UNAVAILABLE)
        for state in ("active ", "ACTIVE", "away", True, 1, None):
            with self.subTest(state=state):
                with self.assertRaises(contract.RecoveryContractError):
                    observed(session(state))

    def test_window_counts(self):
        self.assertEqual(observed(windows(0)).kind, contract.WINDOWS_EMPTY)
        self.assertEqual(observed(windows(3)).kind, contract.WINDOWS_READY)
        self.assertEqual(observed(emit(contract.WINDOW_TOPIC, {})).kind,
                         contract.UNAVAILABLE)

    def test_window_count_wrong_types_fail_closed(self):
        for count in (True, "2", 1.0, -1, contract.MAX_WINDOW_COUNT + 1, None):
            with self.subTest(count=count):
                with self.assertRaises(contract.RecoveryContractError):
                    observed(windows(count))

    def test_window_optional_state_field_is_bounded(self):
        self.assertEqual(observed(windows(1, state="normal")).kind,
                         contract.WINDOWS_READY)
        with self.assertRaises(contract.RecoveryContractError):
            observed(windows(1, state="x" * 500))

    def test_unknown_payload_field_rejected(self):
        with self.assertRaises(contract.RecoveryContractError):
            observed(session("active", surprise=1))
        with self.assertRaises(contract.RecoveryContractError):
            observed(windows(1, surprise=1))
        with self.assertRaises(contract.RecoveryContractError):
            observed(capability(surprise=1))

    def test_event_payload_is_not_mutated(self):
        event = session("active", source=contract.DEFAULT_SOURCE)
        before = dict(event.payload)
        observed(event)
        self.assertEqual(dict(event.payload), before)


class ReconcilerTests(_ContractTestCase):
    def test_default_is_cold_and_never_offers_restore(self):
        reconciler = contract.Reconciler()
        view = reconciler.view()
        self.assertEqual(view.status, contract.COLD)
        self.assertEqual(view.decision, contract.NO_RESTORE)
        self.assertFalse(view.restart_seen)
        self.assertEqual(view.transition_count, 0)
        self.assertEqual(reconciler.history, ())

    def test_view_negative_claims_and_immutability(self):
        view = contract.Reconciler().view()
        record = view.to_dict()
        self.assertEqual(record["schema"], contract.SCHEMA)
        for key in ("focus_actuated", "desktop_session_started",
                    "shell_running", "mint_acceptance_proven",
                    "owner_visual_approval", "measurement_performed",
                    "window_focused"):
            self.assertIs(record[key], False)
        with self.assertRaises(TypeError):
            record["status"] = contract.RESTORE_READY
        self.assertEqual(view.to_dict(), record)

    def test_happy_path_restore_ready(self):
        reconciler = contract.Reconciler()
        outcomes = [
            reconciler.observe(observed(capability())),
            reconciler.observe(observed(session("active"))),
            reconciler.observe(observed(windows(2))),
        ]
        self.assertEqual([o.status for o in outcomes],
                         [contract.TRANSITION] * 3)
        self.assertEqual([o.current for o in outcomes],
                         [contract.AWAITING_SESSION, contract.AWAITING_WINDOWS,
                          contract.RESTORE_READY])
        view = reconciler.view()
        self.assertEqual(view.decision, contract.OFFER_RESTORE)
        self.assertTrue(view.restart_seen)
        self.assertTrue(view.session_ready)
        self.assertTrue(view.window_ready)
        self.assertEqual(view.transition_count, 3)
        self.assertEqual(len(reconciler.history), 3)

    def test_restore_decision_is_not_actuation(self):
        reconciler = contract.Reconciler()
        for event in (capability(), session("active"), windows(1)):
            reconciler.observe(observed(event))
        record = reconciler.view().to_dict()
        self.assertEqual(record["status"], contract.RESTORE_READY)
        self.assertEqual(record["decision"], contract.OFFER_RESTORE)
        self.assertIs(record["focus_actuated"], False)
        self.assertIs(record["shell_running"], False)

    def test_redundant_facts_do_not_repeat_decision(self):
        reconciler = contract.Reconciler()
        for event in (capability(), session("active"), windows(1)):
            reconciler.observe(observed(event))
        before = reconciler.view()
        for event in (session("active"), windows(4)):
            outcome = reconciler.observe(observed(event))
            self.assertEqual(outcome.status, contract.REDUNDANT)
        after = reconciler.view()
        self.assertEqual(after.status, before.status)
        self.assertEqual(after.transition_count, before.transition_count)

    def test_window_before_session_does_not_unlock_restore(self):
        reconciler = contract.Reconciler()
        reconciler.observe(observed(capability()))
        reconciler.observe(observed(windows(3)))
        self.assertEqual(reconciler.status, contract.AWAITING_SESSION)
        outcome = reconciler.observe(observed(session("active")))
        self.assertEqual(outcome.current, contract.AWAITING_WINDOWS)
        self.assertEqual(reconciler.view().decision, contract.NO_RESTORE)
        reconciler.observe(observed(windows(1)))
        self.assertEqual(reconciler.view().decision, contract.OFFER_RESTORE)

    def test_pre_restart_facts_are_ignored(self):
        reconciler = contract.Reconciler()
        for event in (session("active"), windows(2)):
            outcome = reconciler.observe(observed(event))
            self.assertEqual(outcome.status, contract.REDUNDANT)
        self.assertEqual(reconciler.status, contract.COLD)
        reconciler.observe(observed(capability()))
        self.assertEqual(reconciler.status, contract.AWAITING_SESSION)

    def test_session_inactive_defers_recovery(self):
        for state in ("locked", "suspended"):
            with self.subTest(state=state):
                reconciler = contract.Reconciler()
                reconciler.observe(observed(capability()))
                reconciler.observe(observed(session(state)))
                reconciler.observe(observed(windows(2)))
                self.assertEqual(reconciler.status, contract.DEFERRED)
                self.assertEqual(reconciler.view().decision,
                                 contract.NO_RESTORE)

    def test_inactive_after_ready_defers(self):
        reconciler = contract.Reconciler()
        for event in (capability(), session("active"), windows(2),
                      session("locked")):
            reconciler.observe(observed(event))
        self.assertEqual(reconciler.status, contract.DEFERRED)
        self.assertEqual(reconciler.view().decision, contract.NO_RESTORE)

    def test_empty_window_defers_recovery(self):
        reconciler = contract.Reconciler()
        for event in (capability(), session("active"), windows(0)):
            reconciler.observe(observed(event))
        self.assertEqual(reconciler.status, contract.DEFERRED)
        self.assertEqual(reconciler.view().decision, contract.NO_RESTORE)

    def test_missing_fact_does_not_assume_readiness(self):
        reconciler = contract.Reconciler()
        self.assertEqual(reconciler.observe(observed(capability())).status,
                         contract.TRANSITION)
        for event in (emit(contract.SESSION_TOPIC, {}),
                      emit(contract.WINDOW_TOPIC, {})):
            outcome = reconciler.observe(observed(event))
            self.assertEqual(outcome.status, contract.REDUNDANT)
        self.assertEqual(reconciler.view().decision, contract.NO_RESTORE)

    def test_unavailable_after_ready_does_not_retract_or_invent(self):
        reconciler = contract.Reconciler()
        for event in (capability(), session("active"), windows(2)):
            reconciler.observe(observed(event))
        ready = reconciler.view()
        outcome = reconciler.observe(observed(emit(contract.SESSION_TOPIC, {})))
        self.assertEqual(outcome.status, contract.REDUNDANT)
        self.assertEqual(reconciler.view().status, ready.status)
        self.assertEqual(reconciler.view().transition_count,
                         ready.transition_count)

    def test_cleared_report_returns_to_cold(self):
        reconciler = contract.Reconciler()
        for event in (capability(), session("active"), windows(2)):
            reconciler.observe(observed(event))
        reconciler.observe(observed(capability(False)))
        self.assertEqual(reconciler.status, contract.COLD)
        self.assertEqual(reconciler.view().decision, contract.NO_RESTORE)
        self.assertFalse(reconciler.view().restart_seen)

    def test_new_restart_resets_prior_ready_facts(self):
        reconciler = contract.Reconciler()
        for event in (capability(), session("active"), windows(2)):
            reconciler.observe(observed(event))
        self.assertEqual(reconciler.status, contract.RESTORE_READY)
        reconciler.observe(observed(capability()))
        self.assertEqual(reconciler.status, contract.AWAITING_SESSION)
        self.assertEqual(reconciler.view().decision, contract.NO_RESTORE)

    def test_duplicate_fingerprint_is_ignored(self):
        reconciler = contract.Reconciler()
        observation = observed(capability())
        self.assertEqual(reconciler.observe(observation).status,
                         contract.TRANSITION)
        second = reconciler.observe(observation)
        self.assertEqual(second.status, contract.DUPLICATE)
        self.assertEqual(reconciler.view().transition_count, 1)

    def test_stale_sequence_cannot_regress(self):
        reconciler = contract.Reconciler()
        reconciler.observe(observed(capability()))
        reconciler.observe(observed(session("active")))
        ready = observed(windows(1))
        self.assertEqual(reconciler.observe(ready).status, contract.TRANSITION)
        stale = contract.RecoveryObservation(
            contract.SESSION_INACTIVE, ready.sequence - 1)
        outcome = reconciler.observe(stale)
        self.assertEqual(outcome.status, contract.STALE)
        self.assertEqual(reconciler.view().status, contract.RESTORE_READY)

    def test_reordered_input_never_unlocks_restore(self):
        reconciler = contract.Reconciler()
        events = [capability(), session("active"), windows(1)]
        observations = [observed(event) for event in events]
        reversed_reconciler = contract.Reconciler()
        for observation in reversed(observations):
            reversed_reconciler.observe(observation)
        self.assertEqual(reversed_reconciler.view().decision,
                         contract.NO_RESTORE)

    def test_bounded_history_and_dedup_window(self):
        reconciler = contract.Reconciler()
        reconciler.observe(observed(capability()))
        for sequence in range(2, 90):
            reconciliation = reconciler.observe(
                contract.RecoveryObservation(
                    contract.WINDOWS_READY, sequence))
            self.assertIn(reconciliation.status,
                          {contract.TRANSITION, contract.REDUNDANT})
        self.assertLessEqual(len(reconciler.history), contract.MAX_HISTORY)
        replay = contract.RecoveryObservation(contract.WINDOWS_READY, 2)
        self.assertEqual(reconciler.observe(replay).status, contract.STALE)

    def test_close_refuses_later_observations(self):
        reconciler = contract.Reconciler()
        reconciler.observe(observed(capability()))
        reconciler.close()
        self.assertTrue(reconciler.closed)
        self.assertEqual(reconciler.history, ())
        self.assertEqual(reconciler.view().status, contract.COLD)
        with self.assertRaises(contract.RecoveryContractClosed):
            reconciler.observe(observed(session("active")))

    def test_deterministic_equal_inputs(self):
        def replay():
            reconciler = contract.Reconciler()
            for event in (capability(), session("active"), windows(2)):
                reconciler.observe(observed(event))
            return reconciler.view().to_dict()
        first = dict(replay())
        second = dict(replay())
        self.assertEqual(first, second)

    def test_invalid_observe_argument_fails_closed(self):
        reconciler = contract.Reconciler()
        for bad in (None, "restart", {"kind": "restart"}):
            with self.subTest(bad=bad):
                with self.assertRaises(contract.RecoveryContractError):
                    reconciler.observe(bad)
        self.assertEqual(reconciler.status, contract.COLD)

    def test_invalid_history_bound_rejected(self):
        for bound in (0, -1, True, contract.MAX_HISTORY + 1, "16"):
            with self.subTest(bound=bound):
                with self.assertRaises(contract.RecoveryContractError):
                    contract.Reconciler(history_limit=bound)


if __name__ == "__main__":
    unittest.main()
