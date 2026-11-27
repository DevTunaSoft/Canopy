"""Targeted tests for the PE-102 window activation/minimize/restore boundary."""
import unittest

from canopy_core.host_events import (
    CAPABILITIES_TOPIC,
    PROTOCOL_VERSION,
    HostEvent,
    HostEvents,
)
from canopy_features.windows import window_activation_contract as contract
from canopy_features.windows.window_state_capabilities import (
    VALID_TRANSITIONS,
    WindowState,
    WindowStateAction,
    WindowStateFeature,
    negotiate,
)

SEEN = []


def _record(event):
    """Stable module-level callback so HostEvents identity checks succeed."""
    SEEN.append(event)


def _event(state="normal", sequence=1, *, fields=None, source=None):
    if fields is None:
        fields = (("state", state),) if state is not None else ()
        if source is not None:
            fields = fields + (("source", source),)
    return HostEvent(PROTOCOL_VERSION, contract.WINDOW_TOPIC, sequence, fields)


def _boundary(target="minimized", backend="x11", requested=None, **kwargs):
    if requested is None:
        requested = frozenset({
            WindowStateFeature.MINIMIZE, WindowStateFeature.MAXIMIZE,
            WindowStateFeature.RESTORE,
        })
    return contract.ActivationBoundary(
        negotiation=negotiate(backend, requested), target_state=target, **kwargs
    )


def _decision_kwargs(**overrides):
    values = dict(
        schema=contract.SCHEMA, outcome=contract.OFFER, action="minimize",
        reason="capability_granted", status="SUPPORTED", kind=contract.OBSERVED,
        sequence=1, source=contract.DEFAULT_SOURCE,
        observed_state="normal", target_state="minimized",
        acceptance=contract.ACCEPTANCE_NOT_ESTABLISHED,
        observation=contract.OBSERVATION_NOT_PERFORMED,
        wm_requests=0, polling=False, mint_acceptance_proven=False,
        owner_visual_approval=False, screen_reader="NOT_RUN",
    )
    values.update(overrides)
    return values


class _BoundaryCase(unittest.TestCase):
    def setUp(self):
        SEEN.clear()
        self.boundary = _boundary()

    def decide_event(self, state, sequence=1):
        self.boundary.ingest(_event(state, sequence))
        return self.boundary.drain()[0]


class TestProjections(unittest.TestCase):
    def test_observed_window_state(self):
        observation = contract.from_host_event(_event("minimized", 7))
        self.assertEqual(
            (observation.kind, observation.sequence, observation.state,
             observation.source),
            (contract.OBSERVED, 7, "minimized", contract.DEFAULT_SOURCE),
        )

    def test_missing_state_is_explicit_no_facts(self):
        observation = contract.from_host_event(_event(None, 3))
        self.assertEqual(observation.kind, contract.NO_FACTS)
        self.assertEqual(observation.state, "")

    def test_explicit_source_accepted(self):
        observation = contract.from_host_event(
            _event("normal", 2, source="trusted-host"),
            source="trusted-host",
        )
        self.assertEqual(observation.source, "trusted-host")

    def test_contradictory_source_rejected(self):
        with self.assertRaises(contract.ActivationError):
            contract.from_host_event(_event("normal", 2, source="other-host"))

    def test_unknown_window_field_rejected(self):
        with self.assertRaises(contract.ActivationError):
            contract.from_host_event(_event(fields=(("window_count", 2),)))

    def test_crash_field_is_not_reinterpreted(self):
        fields = (("state", "normal"), ("app_id", "files"), ("pid", 12))
        with self.assertRaises(contract.ActivationError):
            contract.from_host_event(_event(fields=fields))

    def test_duplicate_field_rejected(self):
        fields = (("state", "normal"), ("state", "minimized"))
        with self.assertRaises(contract.ActivationError):
            contract.from_host_event(_event(fields=fields))

    def test_malformed_fields_type_rejected(self):
        event = HostEvent(PROTOCOL_VERSION, contract.WINDOW_TOPIC, 1, [])
        with self.assertRaises(contract.ActivationError):
            contract.from_host_event(event)

    def test_capability_topic_rejected(self):
        event = HostEvent(PROTOCOL_VERSION, CAPABILITIES_TOPIC, 1,
                          (("state", "normal"),))
        with self.assertRaises(contract.ActivationError):
            contract.from_host_event(event)

    def test_wrong_protocol_version_rejected(self):
        event = HostEvent(1, contract.WINDOW_TOPIC, 1, (("state", "normal"),))
        with self.assertRaises(contract.ActivationError):
            contract.from_host_event(event)

    def test_wrong_event_type_rejected(self):
        with self.assertRaises(contract.ActivationError):
            contract.from_host_event({"state": "normal"})

    def test_hostile_window_state_types_rejected(self):
        for value in (True, 1, [], "MINIMIZED", "minimized\n", "bogus"):
            with self.subTest(value=value):
                with self.assertRaises(contract.ActivationError):
                    contract.from_host_event(_event(value))

    def test_explicit_none_state_rejected(self):
        # None is used by the helper to mean "field absent"; an explicitly
        # published None value must be refused rather than read as no_facts.
        with self.assertRaises(contract.ActivationError):
            contract.from_host_event(_event(fields=(("state", None),)))

    def test_hostile_sequence_rejected(self):
        for value in (0, -1, True, 1.5, "1", contract.MAX_SEQUENCE + 1):
            with self.subTest(value=value):
                event = HostEvent(PROTOCOL_VERSION, contract.WINDOW_TOPIC,
                                  value, (("state", "normal"),))
                with self.assertRaises(contract.ActivationError):
                    contract.from_host_event(event)

    def test_hostile_source_rejected(self):
        for value in ("", "BAD", "bad source", "bad\u200bsource", "a" * 65,
                      None, True):
            with self.subTest(value=value):
                with self.assertRaises(contract.ActivationError):
                    contract.from_host_event(_event("normal", source=value),
                                             source=value)

    def test_observation_to_dict_is_read_only_and_ordered(self):
        view = contract.from_host_event(_event("normal")).to_dict()
        self.assertEqual(list(view), ["kind", "sequence", "state", "source"])
        with self.assertRaises(TypeError):
            view["state"] = "minimized"

    def test_event_from_existing_bus(self):
        bus = HostEvents({contract.WINDOW_TOPIC: [_record]})
        token = bus.subscribe(contract.WINDOW_TOPIC, _record)
        result = bus.emit(contract.WINDOW_TOPIC, {"state": "minimized"})
        self.assertEqual((result.delivered, result.callback_failures), (1, 0))
        self.assertEqual(contract.from_host_event(SEEN[-1]).state, "minimized")
        bus.unsubscribe(token)
        bus.close()


class TestBoundaryDecisions(_BoundaryCase):
    def test_minimize_offer_on_capable_backend(self):
        decision = self.decide_event("normal")
        self.assertEqual((decision.outcome, decision.action, decision.status),
                         (contract.OFFER, "minimize", "SUPPORTED"))

    def test_restore_offer_from_minimized(self):
        boundary = _boundary(target="normal")
        boundary.ingest(_event("minimized"))
        decision = boundary.drain()[0]
        self.assertEqual((decision.outcome, decision.action, decision.status),
                         (contract.OFFER, "restore", "SUPPORTED"))

    def test_restore_offer_from_maximized_to_normal(self):
        boundary = _boundary(target="normal")
        boundary.ingest(_event("maximized"))
        decision = boundary.drain()[0]
        self.assertEqual((decision.outcome, decision.action),
                         (contract.OFFER, "restore"))

    def test_maximize_offer_uses_existing_transition_table(self):
        boundary = _boundary(target="maximized")
        boundary.ingest(_event("normal"))
        decision = boundary.drain()[0]
        self.assertEqual((decision.outcome, decision.action),
                         (contract.OFFER, "maximize"))

    def test_redundant_when_already_at_target(self):
        boundary = _boundary(target="normal")
        boundary.ingest(_event("normal"))
        decision = boundary.drain()[0]
        self.assertEqual((decision.outcome, decision.action, decision.reason),
                         (contract.REDUNDANT, "", "already_at_target"))

    def test_ambiguous_maximize_to_minimize_rejected(self):
        decision = self.decide_event("maximized")
        self.assertEqual((decision.outcome, decision.reason),
                         (contract.REJECTED, "ambiguous_prior_state"))

    def test_minimized_to_maximized_rejected(self):
        boundary = _boundary(target="maximized")
        boundary.ingest(_event("minimized"))
        decision = boundary.drain()[0]
        self.assertEqual((decision.outcome, decision.reason),
                         (contract.REJECTED, "no_direct_transition"))

    def test_wayland_minimize_fallback(self):
        boundary = _boundary(backend="wayland",
                             requested=frozenset({WindowStateFeature.MINIMIZE}))
        boundary.ingest(_event("normal"))
        decision = boundary.drain()[0]
        self.assertEqual((decision.outcome, decision.action, decision.status),
                         (contract.FALLBACK, "", "UNSUPPORTED"))

    def test_partial_negotiation_keeps_restore_offer(self):
        requested = frozenset({
            WindowStateFeature.MINIMIZE, WindowStateFeature.RESTORE,
        })
        fallback = _boundary(backend="wayland", requested=requested)
        fallback.ingest(_event("normal"))
        self.assertEqual(fallback.drain()[0].outcome, contract.FALLBACK)
        boundary = _boundary(target="normal", backend="wayland",
                             requested=requested)
        boundary.ingest(_event("minimized"))
        decision = boundary.drain()[0]
        self.assertEqual((decision.outcome, decision.status),
                         (contract.OFFER, "PARTIAL"))

    def test_unknown_backend_fallback(self):
        boundary = _boundary(target="normal", backend="mystery-compositor")
        boundary.ingest(_event("minimized"))
        decision = boundary.drain()[0]
        self.assertEqual((decision.outcome, decision.status),
                         (contract.FALLBACK, "UNSUPPORTED"))

    def test_no_facts_defers_without_action(self):
        boundary = _boundary()
        boundary.ingest(_event(None))
        decision = boundary.drain()[0]
        self.assertEqual((decision.outcome, decision.action, decision.status,
                          decision.kind),
                         (contract.DEFER, "", "", contract.NO_FACTS))

    def test_decision_to_dict_is_read_only_and_ordered(self):
        view = self.decide_event("normal").to_dict()
        self.assertEqual(list(view), [
            "schema", "outcome", "action", "reason", "status", "kind",
            "sequence", "source", "observed_state", "target_state",
            "acceptance", "observation", "wm_requests", "polling",
            "mint_acceptance_proven", "owner_visual_approval", "screen_reader",
        ])
        with self.assertRaises(TypeError):
            view["wm_requests"] = 1

    def test_snapshot_negative_claims(self):
        self.decide_event("normal")
        snapshot = self.boundary.snapshot()
        self.assertEqual(snapshot["outcome"], contract.OFFER)
        self.assertEqual(snapshot["action"], "minimize")
        self.assertEqual(
            (snapshot["wm_requests"], snapshot["polling"],
             snapshot["acceptance"], snapshot["observation"],
             snapshot["screen_reader"], snapshot["mint_acceptance_proven"],
             snapshot["owner_visual_approval"]),
            (0, False, "NOT_ESTABLISHED", "NOT_PERFORMED", "NOT_RUN",
             False, False),
        )
        with self.assertRaises(TypeError):
            snapshot["wm_requests"] = 1

    def test_transition_actions_come_from_existing_module(self):
        expected = {
            (state.value, result.value): action.value
            for (state, action), result in VALID_TRANSITIONS.items()
        }
        self.assertEqual(dict(contract._TRANSITION_ACTION), expected)
        self.assertTrue(set(contract._TRANSITION_ACTION.values()) <= contract.ACTIONS)
        self.assertEqual(
            contract._ACTION_ENUM["restore"], WindowStateAction.RESTORE
        )
        self.assertEqual(WindowState.MINIMIZED.value, "minimized")

    def test_forged_decision_claims_rejected(self):
        for label, value in (
            ("action", ""), ("status", ""), ("wm_requests", 1),
            ("polling", True), ("acceptance", "ESTABLISHED"),
            ("observation", "PERFORMED"), ("screen_reader", "DONE"),
            ("mint_acceptance_proven", True), ("owner_visual_approval", True),
            ("schema", 2), ("reason", "unknown_reason"), ("action", "close"),
        ):
            with self.subTest(label=label, value=value):
                with self.assertRaises(contract.ActivationError):
                    contract.ActivationDecision(**_decision_kwargs(**{label: value}))
        forged = _decision_kwargs(outcome=contract.DEFER, kind=contract.OBSERVED,
                                  action="", status="")
        with self.assertRaises(contract.ActivationError):
            contract.ActivationDecision(**forged)


class TestBoundaryBounds(_BoundaryCase):
    def test_duplicate_and_stale_sequences_rejected(self):
        self.assertEqual(self.boundary.ingest(_event("normal", 4)), 4)
        with self.assertRaises(contract.ActivationError):
            self.boundary.ingest(_event("minimized", 4))
        self.assertEqual(self.boundary.last_rejection, "STALE_SEQUENCE")
        with self.assertRaises(contract.ActivationError):
            self.boundary.ingest(_event("normal", 3))
        self.assertEqual(self.boundary.pending, 1)
        self.assertEqual(self.boundary.ingest(_event("minimized", 5)), 5)

    def test_invalid_event_is_counted_without_queue_mutation(self):
        with self.assertRaises(contract.ActivationError):
            self.boundary.ingest(_event(fields=(("window_count", 2),)))
        self.assertEqual(self.boundary.last_rejection, "INVALID_EVENT")
        self.assertEqual(self.boundary.pending, 0)

    def test_pending_queue_bound(self):
        boundary = _boundary(max_pending=1)
        boundary.ingest(_event("normal", 1))
        with self.assertRaises(contract.ActivationError):
            boundary.ingest(_event("minimized", 2))
        self.assertEqual(boundary.last_rejection, "QUEUE_FULL")
        self.assertEqual(boundary.pending, 1)

    def test_drop_oldest_policy_stays_bounded(self):
        boundary = _boundary(max_pending=2, overflow="drop_oldest")
        for sequence in (1, 2, 3):
            boundary.ingest(_event("normal", sequence))
        self.assertEqual(boundary.pending, 2)
        decisions = boundary.drain()
        self.assertEqual(tuple(item.sequence for item in decisions), (2, 3))

    def test_invalid_overflow_and_bounds_rejected(self):
        for kwargs in (
            {"overflow": "append"}, {"max_pending": 0}, {"max_pending": 17},
            {"max_pending": True}, {"max_drain": 0}, {"max_drain": 9},
            {"history_limit": 0}, {"history_limit": 17},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(contract.ActivationError):
                    _boundary(**kwargs)

    def test_drain_bound_and_invalid_limit(self):
        boundary = _boundary(max_drain=2)
        for sequence in (1, 2, 3):
            boundary.ingest(_event("minimized", sequence))
        self.assertEqual(len(boundary.drain()), 2)
        self.assertEqual(len(boundary.drain()), 1)
        for limit in (0, 3, True, "1"):
            with self.subTest(limit=limit):
                with self.assertRaises(contract.ActivationError):
                    boundary.drain(limit)
        self.assertEqual(boundary.last_rejection, "INVALID_LIMIT")

    def test_history_bound(self):
        boundary = _boundary(history_limit=2)
        for sequence in (1, 2, 3):
            boundary.ingest(_event("normal", sequence))
        boundary.drain()
        self.assertEqual(tuple(item.sequence for item in boundary.history), (2, 3))

    def test_history_snapshot_is_immutable_and_cached(self):
        boundary = _boundary()
        boundary.ingest(_event("normal", 1))
        boundary.drain()
        first = boundary.history
        self.assertIsInstance(first, tuple)
        self.assertIs(boundary.history, first)
        boundary.ingest(_event("minimized", 2))
        boundary.drain()
        self.assertIsNot(boundary.history, first)

    def test_decisions_built_before_queue_removal(self):
        for sequence in (1, 2):
            self.boundary.ingest(_event("normal", sequence))
        original = self.boundary._decide
        calls = []

        def counting(observation):
            calls.append(observation.sequence)
            if len(calls) == 2:
                self.assertEqual(self.boundary.pending, 2)
            return original(observation)

        self.boundary._decide = counting
        self.assertEqual(len(self.boundary.drain()), 2)
        self.assertEqual(self.boundary.pending, 0)

    def test_close_fails_closed(self):
        boundary = _boundary()
        boundary.ingest(_event("normal", 1))
        boundary.drain()
        boundary.close()
        self.assertTrue(boundary.closed)
        for action in (
            lambda: boundary.ingest(_event("normal", 2)),
            lambda: boundary.drain(),
            lambda: boundary.snapshot(),
        ):
            with self.assertRaises(contract.ActivationClosed):
                action()
        boundary.close()

    def test_hostile_context_types_rejected(self):
        for target in (True, 1, None, "", "MINIMIZED", "bogus"):
            with self.subTest(target=target):
                with self.assertRaises(contract.ActivationError):
                    _boundary(target=target)
        with self.assertRaises(contract.ActivationError):
            contract.ActivationBoundary(negotiation="x11", target_state="normal")
        from canopy_features.windows.window_state_capabilities import Negotiation
        for negotiation in (
            Negotiation("x11", "SUPPORTED", frozenset()),
            Negotiation("x11", "UNSUPPORTED",
                        frozenset({WindowStateFeature.MINIMIZE})),
            Negotiation("x11", "PARTIAL", frozenset({"minimize"})),
        ):
            with self.subTest(negotiation=negotiation):
                with self.assertRaises(contract.ActivationError):
                    contract.ActivationBoundary(negotiation=negotiation,
                                                target_state="normal")
        with self.assertRaises(contract.ActivationError):
            _boundary(source=None)


if __name__ == "__main__":
    unittest.main()
