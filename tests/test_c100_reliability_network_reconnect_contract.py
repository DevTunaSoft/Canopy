"""Targeted contracts for network disconnect/reconnect status reconciliation.

Pure-Python, synthetic evidence only. No network, socket, credential, host
probe, Qt, Mint or visual behavior is exercised here.
"""
import unittest

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    HostEvent,
    HostEvents,
    HostEventError,
)
from canopy_features.reliability.network_reconnect_contract import (
    CONNECT,
    CONNECTED,
    DISCONNECT,
    DISCONNECTED,
    DUPLICATE,
    NETWORK_FIELD,
    REDUNDANT,
    RECONNECTED,
    STALE,
    TOPIC,
    TRANSITION,
    UNAVAILABLE,
    UNKNOWN,
    NetworkObservation,
    NetworkReconnectClosed,
    NetworkReconnectError,
    Reconciler,
    from_host_event,
)
from canopy_features.system.quick_controls_state import (
    AVAILABLE as QC_AVAILABLE,
    STATUS_TOKENS,
    UNAVAILABLE as QC_UNAVAILABLE,
    Observation,
)


def event(sequence, payload, *, topic=TOPIC, version=PROTOCOL_VERSION):
    """Build a delivered host event without creating a bus or network call."""
    return HostEvent(version, topic, sequence,
                     tuple(sorted((k, v) for k, v in payload.items())))


class InitialStatusTests(unittest.TestCase):
    def test_starts_unknown_without_observation(self):
        reconciler = Reconciler()
        view = reconciler.view()
        self.assertEqual(view.status, UNKNOWN)
        self.assertEqual(view.previous_status, UNKNOWN)
        self.assertEqual(view.transition_count, 0)
        self.assertFalse(view.observed)
        self.assertEqual(view.source, "none")
        self.assertEqual(view.quick_controls_status, UNKNOWN)
        self.assertEqual(view.availability, QC_UNAVAILABLE)

    def test_first_connect_is_connected_not_reconnected(self):
        reconciler = Reconciler()
        outcome = reconciler.observe(NetworkObservation(CONNECT, 1))
        self.assertEqual(outcome.status, TRANSITION)
        self.assertEqual(outcome.previous, UNKNOWN)
        self.assertEqual(outcome.current, CONNECTED)
        self.assertTrue(outcome.transitioned)

    def test_first_disconnect_is_disconnected(self):
        reconciler = Reconciler()
        outcome = reconciler.observe(NetworkObservation(DISCONNECT, 1))
        self.assertEqual(outcome.current, DISCONNECTED)
        self.assertEqual(reconciler.view().availability, QC_UNAVAILABLE)


class ReconnectTransitionTests(unittest.TestCase):
    def test_disconnect_then_connect_is_reconnected(self):
        reconciler = Reconciler()
        reconciler.observe(NetworkObservation(DISCONNECT, 1))
        outcome = reconciler.observe(NetworkObservation(CONNECT, 2))
        self.assertEqual(outcome.status, TRANSITION)
        self.assertEqual(outcome.previous, DISCONNECTED)
        self.assertEqual(outcome.current, RECONNECTED)
        view = reconciler.view()
        self.assertEqual(view.availability, QC_AVAILABLE)
        self.assertEqual(view.quick_controls_status, "connected")

    def test_unavailable_then_connect_is_reconnected(self):
        reconciler = Reconciler()
        reconciler.observe(NetworkObservation(UNAVAILABLE, 1))
        outcome = reconciler.observe(NetworkObservation(CONNECT, 2))
        self.assertEqual(outcome.current, RECONNECTED)

    def test_reconnect_then_connect_settles_to_connected(self):
        reconciler = Reconciler()
        reconciler.observe(NetworkObservation(DISCONNECT, 1))
        reconciler.observe(NetworkObservation(CONNECT, 2))
        outcome = reconciler.observe(NetworkObservation(CONNECT, 3))
        self.assertEqual(outcome.current, CONNECTED)
        self.assertEqual(outcome.previous, RECONNECTED)

    def test_reconnect_then_disconnect_is_disconnected(self):
        reconciler = Reconciler()
        reconciler.observe(NetworkObservation(DISCONNECT, 1))
        reconciler.observe(NetworkObservation(CONNECT, 2))
        outcome = reconciler.observe(NetworkObservation(DISCONNECT, 3))
        self.assertEqual(outcome.current, DISCONNECTED)

    def test_redundant_connect_reports_without_transition(self):
        reconciler = Reconciler()
        reconciler.observe(NetworkObservation(CONNECT, 1))
        outcome = reconciler.observe(NetworkObservation(CONNECT, 2))
        self.assertEqual(outcome.status, REDUNDANT)
        self.assertEqual(outcome.current, CONNECTED)
        self.assertEqual(reconciler.view().transition_count, 1)

    def test_unavailable_is_a_fixed_graceful_token(self):
        reconciler = Reconciler()
        reconciler.observe(NetworkObservation(CONNECT, 1))
        outcome = reconciler.observe(NetworkObservation(UNAVAILABLE, 2))
        self.assertEqual(outcome.current, UNAVAILABLE)
        self.assertEqual(reconciler.view().availability, QC_UNAVAILABLE)
        self.assertEqual(reconciler.view().quick_controls_status, UNKNOWN)


class OrderingAndBoundTests(unittest.TestCase):
    def test_duplicate_does_not_transition_or_consume_history(self):
        reconciler = Reconciler(history_limit=4)
        observation = NetworkObservation(DISCONNECT, 1)
        self.assertEqual(reconciler.observe(observation).status, TRANSITION)
        self.assertEqual(reconciler.observe(observation).status, DUPLICATE)
        self.assertEqual(reconciler.view().transition_count, 1)
        self.assertEqual(len(reconciler.history), 1)

    def test_stale_sequence_cannot_regress_status(self):
        reconciler = Reconciler()
        reconciler.observe(NetworkObservation(DISCONNECT, 5))
        outcome = reconciler.observe(NetworkObservation(CONNECT, 4))
        self.assertEqual(outcome.status, STALE)
        self.assertEqual(reconciler.view().status, DISCONNECTED)
        self.assertEqual(reconciler.view().transition_count, 1)

    def test_same_sequence_conflict_is_stale(self):
        reconciler = Reconciler()
        reconciler.observe(NetworkObservation(DISCONNECT, 1))
        outcome = reconciler.observe(NetworkObservation(CONNECT, 1))
        self.assertEqual(outcome.status, STALE)
        self.assertEqual(reconciler.view().status, DISCONNECTED)

    def test_rejected_stale_event_does_not_consume_duplicate_slot(self):
        reconciler = Reconciler()
        accepted = NetworkObservation(DISCONNECT, 1)
        reconciler.observe(accepted)
        stale = NetworkObservation(UNAVAILABLE, 1)  # same sequence, new kind
        self.assertEqual(reconciler.observe(stale).status, STALE)
        self.assertEqual(reconciler.observe(accepted).status, DUPLICATE)

    def test_history_is_bounded_and_immutable(self):
        reconciler = Reconciler(history_limit=2)
        for sequence, kind in ((1, DISCONNECT), (2, CONNECT), (3, DISCONNECT)):
            reconciler.observe(NetworkObservation(kind, sequence))
        history = reconciler.history
        self.assertEqual(len(history), 2)
        self.assertIsInstance(history, tuple)
        with self.assertRaises(TypeError):
            history[0] = None
        self.assertEqual([item.current for item in history],
                         [RECONNECTED, DISCONNECTED])

    def test_invalid_bounds_and_wrong_types_fail_closed(self):
        for bad in (0, -1, 65, 1.0, True, "4", [4], None):
            with self.subTest(history_limit=bad), self.assertRaises(
                    NetworkReconnectError):
                Reconciler(history_limit=bad)
        with self.assertRaises(NetworkReconnectError):
            Reconciler().observe({"kind": CONNECT, "sequence": 1})
        for bad in (1, True, None, "", "CONNECT", "connect\n"):
            with self.subTest(kind=bad), self.assertRaises(NetworkReconnectError):
                NetworkObservation(bad, 1)
        for bad in (0, -1, 1.0, True, "1", None):
            with self.subTest(sequence=bad), self.assertRaises(
                    NetworkReconnectError):
                NetworkObservation(CONNECT, bad)

    def test_close_is_fail_closed_and_idempotent(self):
        reconciler = Reconciler()
        reconciler.observe(NetworkObservation(DISCONNECT, 1))
        reconciler.close()
        reconciler.close()
        self.assertTrue(reconciler.closed)
        self.assertEqual(reconciler.history, ())
        with self.assertRaises(NetworkReconnectClosed):
            reconciler.observe(NetworkObservation(CONNECT, 2))


class HostEventBoundaryTests(unittest.TestCase):
    def test_event_false_then_true_drives_reconnect(self):
        reconciler = Reconciler()
        first = from_host_event(
            event(1, {NETWORK_FIELD: False, "source": "host-events"}))
        second = from_host_event(
            event(2, {NETWORK_FIELD: True, "source": "host-events"}))
        self.assertEqual(first.kind, DISCONNECT)
        self.assertEqual(second.kind, CONNECT)
        reconciler.observe(first)
        self.assertEqual(reconciler.observe(second).current, RECONNECTED)

    def test_event_without_network_field_is_unavailable(self):
        observation = from_host_event(event(7, {"status": "CAPABILITY_REPORT"}))
        self.assertEqual(observation.kind, UNAVAILABLE)
        self.assertEqual(observation.sequence, 7)

    def test_event_wrong_envelope_is_refused(self):
        for bad_event in (
                object(),
                event(1, {NETWORK_FIELD: True}, topic="capabilities.report.x"),
                event(1, {NETWORK_FIELD: True}, version=1),
                HostEvent(PROTOCOL_VERSION, TOPIC, 0, ()),
        ):
            with self.subTest(bad_event=bad_event), self.assertRaises(
                    NetworkReconnectError):
                from_host_event(bad_event)

    def test_event_hostile_field_types_are_refused(self):
        for bad in (1, "true", None, [True], 0.0):
            with self.subTest(value=bad), self.assertRaises(NetworkReconnectError):
                from_host_event(event(1, {NETWORK_FIELD: bad}))

    def test_event_contradictory_source_is_refused(self):
        bad = event(1, {NETWORK_FIELD: True, "source": "someone-else"})
        with self.assertRaises(NetworkReconnectError):
            from_host_event(bad, source="host-events")
        good = event(2, {NETWORK_FIELD: True, "source": "host-events"})
        self.assertEqual(from_host_event(good, source="host-events").source,
                         "host-events")

    def test_event_hostile_source_token_is_refused(self):
        for bad in ("Host-Events", "host events", "x" * 65, "host\nevents",
                    "\ud800", 12, None, True):
            with self.subTest(source=bad), self.assertRaises(
                    NetworkReconnectError):
                from_host_event(event(1, {NETWORK_FIELD: True}), source=bad)

    def test_real_bus_delivery_is_accepted(self):
        seen = []
        def on_event(host_event):
            seen.append(host_event)

        bus = HostEvents({TOPIC: [on_event]})
        bus.subscribe(TOPIC, on_event)
        result = bus.emit(TOPIC, {NETWORK_FIELD: False, "source": "host-events"})
        self.assertEqual((result.delivered, result.callback_failures), (1, 0))
        observation = from_host_event(seen[0], source="host-events")
        reconciler = Reconciler()
        self.assertEqual(reconciler.observe(observation).status, TRANSITION)
        self.assertEqual(reconciler.view().status, DISCONNECTED)
        bus.close()


class ViewContractTests(unittest.TestCase):
    def test_status_tokens_are_fixed_and_ui_tokens_are_existing(self):
        reconcile = Reconciler()
        reconcile.observe(NetworkObservation(DISCONNECT, 1))
        view = reconcile.view()
        self.assertEqual(view.status, DISCONNECTED)
        self.assertIn(view.quick_controls_status, STATUS_TOKENS["network"])
        self.assertIn(view.availability, (QC_AVAILABLE, QC_UNAVAILABLE))
        mapping = view.to_dict()
        self.assertEqual(mapping["status"], DISCONNECTED)
        self.assertEqual(mapping["quick_controls_status"], "disconnected")
        with self.assertRaises(TypeError):
            mapping["status"] = "forged"

    def test_event_payload_uses_only_existing_field_names(self):
        reconcile = Reconciler()
        reconcile.observe(NetworkObservation(DISCONNECT, 1))
        payload = reconcile.view().to_event_payload()
        self.assertEqual(set(payload), {"status", "source", NETWORK_FIELD})
        self.assertEqual(payload[NETWORK_FIELD], False)
        self.assertEqual(payload["status"], DISCONNECTED)
        # The payload must be directly emit-able on the existing bus.
        def on_event(host_event):
            self.assertIsInstance(host_event, HostEvent)

        bus = HostEvents({TOPIC: [on_event]})
        bus.subscribe(TOPIC, on_event)
        self.assertEqual(bus.emit(TOPIC, dict(payload)).delivered, 1)
        bus.close()

    def test_unavailable_payload_omits_network_fact(self):
        reconcile = Reconciler()
        reconcile.observe(NetworkObservation(UNAVAILABLE, 1))
        payload = reconcile.view().to_event_payload()
        self.assertNotIn(NETWORK_FIELD, payload)
        self.assertEqual(payload["status"], UNAVAILABLE)

    def test_reconnected_payload_is_consistent(self):
        reconcile = Reconciler()
        reconcile.observe(NetworkObservation(DISCONNECT, 1))
        reconcile.observe(NetworkObservation(CONNECT, 2))
        payload = reconcile.view().to_event_payload()
        self.assertEqual(payload["status"], RECONNECTED)
        self.assertIs(payload[NETWORK_FIELD], True)

    def test_as_observation_reuses_quick_controls_model(self):
        reconcile = Reconciler()
        reconcile.observe(NetworkObservation(CONNECT, 1))
        observation = reconcile.view().as_observation()
        self.assertIsInstance(observation, Observation)
        self.assertEqual(observation.domain, "network")
        self.assertEqual(observation.status, "connected")

    def test_view_is_stable_and_deterministic(self):
        first = Reconciler()
        second = Reconciler()
        for reconciler in (first, second):
            reconciler.observe(NetworkObservation(DISCONNECT, 1))
            reconciler.observe(NetworkObservation(CONNECT, 2))
        self.assertEqual(first.view().to_dict(), second.view().to_dict())
        self.assertEqual(first.view(), second.view())

    def test_error_hierarchy_stays_with_host_event_domain(self):
        self.assertTrue(issubclass(NetworkReconnectError, HostEventError))
        self.assertTrue(issubclass(NetworkReconnectClosed, RuntimeError))
        self.assertEqual(UNAVAILABLE, "unavailable")


if __name__ == "__main__":
    unittest.main()
