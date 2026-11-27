"""Targeted tests for PE-086 bounded workspace behavior contracts.

These exercise the trusted-host event boundary only. Nothing here starts a
window manager, observes a compositor or claims desktop acceptance.
"""
import unittest

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    HostEvent,
    HostEvents,
)
from canopy_features.windows import workspace_state_contract as contracts
from canopy_features.windows.window_state_capabilities import (
    WindowStateAction,
    WindowStateFeature,
    negotiate,
)
from canopy_features.windows.workspace_behavior_contract import (
    CAPABILITIES_TOPIC,
    DEFER,
    DEFAULT_SOURCE,
    FALLBACK,
    MAX_DRAIN,
    MAX_HISTORY,
    MAX_PENDING,
    MAX_SEQUENCE,
    NO_FACTS,
    OBSERVED,
    SWITCH_OFFER,
    WINDOW_EMPTY,
    WINDOW_TOPIC,
    WorkspaceBehaviorBoundary,
    WorkspaceBehaviorClosed,
    WorkspaceBehaviorError,
    WorkspaceEventObservation,
    from_host_event,
)
from canopy_features.windows.workspace_inventory import WorkspaceInventory, Workspace


def _inventory(*identifiers):
    return WorkspaceInventory(
        workspaces=tuple(Workspace(identifier, identifier, "trusted-host")
                         for identifier in identifiers),
        problems=(),
    )


def _negotiation(backend="x11"):
    return negotiate(backend, [WindowStateFeature.MINIMIZE])


def _event(sequence=1, **fields):
    return HostEvent(PROTOCOL_VERSION, WINDOW_TOPIC, sequence,
                     tuple(sorted(fields.items())))


class _BoundaryCase(unittest.TestCase):
    def setUp(self):
        self.inventory = _inventory("one", "two", "three")
        self.boundary = WorkspaceBehaviorBoundary(
            workspace=self.inventory,
            active="one",
            negotiation=_negotiation(),
            capabilities=frozenset({contracts.CAPABILITY_SWITCH}),
        )


class TestProjections(unittest.TestCase):
    def test_window_target_observation(self):
        observation = from_host_event(_event(state="two", window_count=2))
        self.assertIsInstance(observation, WorkspaceEventObservation)
        self.assertEqual(observation.kind, OBSERVED)
        self.assertEqual(observation.target, "two")
        self.assertEqual(observation.window_count, 2)
        self.assertEqual(observation.sequence, 1)
        self.assertEqual(observation.source, DEFAULT_SOURCE)

    def test_missing_facts_observation(self):
        observation = from_host_event(_event())
        self.assertEqual(observation.kind, NO_FACTS)
        self.assertEqual(observation.target, "")
        self.assertEqual(observation.window_count, 0)

    def test_empty_windows_observation(self):
        observation = from_host_event(_event(window_count=0))
        self.assertEqual(observation.kind, WINDOW_EMPTY)

    def test_explicit_source_accepted(self):
        observation = from_host_event(
            _event(state="two", window_count=1, source="classic-host"),
            source="classic-host",
        )
        self.assertEqual(observation.source, "classic-host")

    def test_contradictory_source_rejected(self):
        with self.assertRaises(WorkspaceBehaviorError):
            from_host_event(_event(state="two", window_count=1,
                                   source="other-host"))

    def test_contradictory_zero_windows_with_target_rejected(self):
        with self.assertRaises(WorkspaceBehaviorError):
            from_host_event(_event(state="two", window_count=0))

    def test_unknown_window_field_rejected(self):
        with self.assertRaises(WorkspaceBehaviorError):
            from_host_event(_event(state="two", window_count=1, pid=42))

    def test_capability_topic_rejected(self):
        event = HostEvent(PROTOCOL_VERSION, CAPABILITIES_TOPIC, 1,
                          (("status", "CAPABILITY_REPORT"),))
        with self.assertRaises(WorkspaceBehaviorError):
            from_host_event(event)

    def test_wrong_protocol_version_rejected(self):
        event = HostEvent(1, WINDOW_TOPIC, 1, (("window_count", 1),))
        with self.assertRaises(WorkspaceBehaviorError):
            from_host_event(event)

    def test_wrong_event_type_rejected(self):
        with self.assertRaises(WorkspaceBehaviorError):
            from_host_event({"topic": WINDOW_TOPIC})

    def test_hostile_window_count_types_rejected(self):
        for value in (True, -1, "1", 1.0, None, [], {}):
            with self.subTest(value=value), self.assertRaises(WorkspaceBehaviorError):
                from_host_event(_event(window_count=value))

    def test_hostile_state_types_rejected(self):
        for value in (True, 2, "", "Two", "two/three", "x" * 65):
            with self.subTest(value=value), self.assertRaises(WorkspaceBehaviorError):
                from_host_event(_event(state=value, window_count=1))

    def test_hostile_source_rejected(self):
        for value in (True, "", "Host!", "x" * 65):
            with self.subTest(value=value), self.assertRaises(WorkspaceBehaviorError):
                from_host_event(_event(state="two", window_count=1,
                                       source=value))

    def test_event_from_existing_bus(self):
        seen = []

        def collector(event):
            seen.append(event)

        bus = HostEvents({WINDOW_TOPIC: [collector]})
        token = bus.subscribe(WINDOW_TOPIC, collector)
        result = bus.emit(WINDOW_TOPIC, {"state": "two", "window_count": 1})
        self.assertEqual((result.delivered, result.callback_failures), (1, 0))
        observation = from_host_event(seen[0])
        self.assertEqual((observation.kind, observation.target), (OBSERVED, "two"))
        self.assertTrue(bus.unsubscribe(token))
        bus.close()


class TestBoundaryDecisions(_BoundaryCase):
    def _decide(self, **fields):
        self.boundary.ingest(_event(**fields))
        return self.boundary.drain()[0]

    def test_native_switch_offer(self):
        decision = self._decide(state="two", window_count=2)
        self.assertEqual(decision.outcome, SWITCH_OFFER)
        self.assertEqual(decision.status, contracts.STATUS_NATIVE)
        self.assertEqual(decision.reason, contracts.REASON_NATIVE_READY)
        self.assertEqual(decision.target, "two")
        self.assertEqual(decision.wm_requests, 0)
        self.assertIs(decision.polling, False)
        self.assertEqual(decision.acceptance, contracts.ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(decision.observation, contracts.OBSERVATION_NOT_PERFORMED)

    def test_wayland_fallback(self):
        boundary = WorkspaceBehaviorBoundary(
            workspace=self.inventory, active="one",
            negotiation=_negotiation("wayland"),
            capabilities=frozenset({contracts.CAPABILITY_SWITCH}),
        )
        boundary.ingest(_event(state="two", window_count=1))
        decision = boundary.drain()[0]
        self.assertEqual(decision.outcome, FALLBACK)
        self.assertEqual(decision.reason, contracts.REASON_BACKEND_UNSUPPORTED)

    def test_missing_capability_fallback(self):
        boundary = WorkspaceBehaviorBoundary(
            workspace=self.inventory, active="one",
            negotiation=_negotiation(), capabilities=frozenset(),
        )
        boundary.ingest(_event(state="two", window_count=1))
        decision = boundary.drain()[0]
        self.assertEqual(decision.outcome, FALLBACK)
        self.assertEqual(decision.reason, contracts.REASON_CAPABILITY_NOT_GRANTED)

    def test_unknown_target_fallback(self):
        decision = self._decide(state="missing", window_count=1)
        self.assertEqual(decision.outcome, FALLBACK)
        self.assertEqual(decision.reason, contracts.REASON_UNKNOWN_TARGET)

    def test_already_active_fallback(self):
        decision = self._decide(state="one", window_count=1)
        self.assertEqual(decision.outcome, FALLBACK)
        self.assertEqual(decision.reason, contracts.REASON_ALREADY_ACTIVE)

    def test_no_facts_defers_without_switch(self):
        decision = self._decide()
        self.assertEqual(decision.outcome, DEFER)
        self.assertEqual(decision.reason, NO_FACTS)
        self.assertEqual(decision.status, "")

    def test_empty_windows_defers_without_switch(self):
        decision = self._decide(window_count=0)
        self.assertEqual(decision.outcome, DEFER)
        self.assertEqual(decision.reason, WINDOW_EMPTY)

    def test_decision_to_dict_is_read_only_and_ordered(self):
        decision = self._decide(state="two", window_count=1)
        view = decision.to_dict()
        self.assertEqual(tuple(view), (
            "schema", "outcome", "reason", "status", "kind", "sequence",
            "source", "active", "target", "window_count", "acceptance",
            "observation", "wm_requests", "polling",
        ))
        with self.assertRaises(TypeError):
            view["outcome"] = FALLBACK
        self.assertEqual(decision.to_dict(), view)

    def test_snapshot_negative_claims(self):
        self._decide(state="two", window_count=1)
        view = self.boundary.snapshot()
        self.assertEqual(view["wm_requests"], 0)
        self.assertIs(view["polling"], False)
        self.assertEqual(view["acceptance"], contracts.ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(view["observation"], contracts.OBSERVATION_NOT_PERFORMED)
        self.assertIs(view["mint_acceptance_proven"], False)
        self.assertIs(view["owner_visual_approval"], False)
        with self.assertRaises(TypeError):
            view["wm_requests"] = 1


class TestBoundaryBounds(_BoundaryCase):
    def test_duplicate_and_stale_sequences_rejected(self):
        self.boundary.ingest(_event(sequence=5))
        for sequence in (5, 4):
            with self.subTest(sequence=sequence):
                before = (self.boundary.pending, self.boundary.rejection_count)
                with self.assertRaises(WorkspaceBehaviorError):
                    self.boundary.ingest(_event(sequence=sequence))
                self.assertEqual((self.boundary.pending,
                                  self.boundary.rejection_count),
                                 (before[0], before[1] + 1))
        self.boundary.ingest(_event(sequence=6))
        self.assertEqual(self.boundary.pending, 2)

    def test_invalid_sequence_rejected(self):
        for sequence in (0, -1, True, MAX_SEQUENCE + 1, "1", None):
            with self.subTest(sequence=sequence), self.assertRaises(WorkspaceBehaviorError):
                self.boundary.ingest(_event(sequence=sequence))

    def test_pending_queue_bound(self):
        for sequence in range(1, MAX_PENDING + 1):
            self.boundary.ingest(_event(sequence=sequence))
        self.assertEqual(self.boundary.pending, MAX_PENDING)
        with self.assertRaises(WorkspaceBehaviorError):
            self.boundary.ingest(_event(sequence=MAX_PENDING + 1))
        self.assertEqual(self.boundary.pending, MAX_PENDING)
        self.assertEqual(self.boundary.last_rejection, "QUEUE_FULL")

    def test_drop_oldest_policy_stays_bounded(self):
        boundary = WorkspaceBehaviorBoundary(
            workspace=self.inventory, active="one",
            negotiation=_negotiation(),
            capabilities=frozenset({contracts.CAPABILITY_SWITCH}),
            overflow="drop_oldest",
        )
        for sequence in range(1, MAX_PENDING + 2):
            boundary.ingest(_event(sequence=sequence, state="two", window_count=1))
        self.assertEqual(boundary.pending, MAX_PENDING)
        decisions = boundary.drain()
        self.assertEqual(decisions[0].sequence, 2)
        self.assertEqual(len(decisions), MAX_DRAIN)

    def test_invalid_overflow_policy_rejected(self):
        with self.assertRaises(WorkspaceBehaviorError):
            WorkspaceBehaviorBoundary(
                workspace=self.inventory, active="one",
                negotiation=_negotiation(), capabilities=frozenset(),
                overflow="ignore",
            )

    def test_drain_bound_and_invalid_limit(self):
        for sequence in range(1, MAX_PENDING + 1):
            self.boundary.ingest(_event(sequence=sequence))
        self.assertEqual(len(self.boundary.drain()), MAX_DRAIN)
        self.assertEqual(self.boundary.pending, MAX_PENDING - MAX_DRAIN)
        self.assertEqual(len(self.boundary.drain(limit=2)), 2)
        for limit in (0, -1, True, MAX_DRAIN + 1, "2"):
            with self.subTest(limit=limit), self.assertRaises(WorkspaceBehaviorError):
                self.boundary.drain(limit=limit)

    def test_history_bound(self):
        for sequence in range(1, MAX_PENDING + 1):
            self.boundary.ingest(_event(sequence=sequence, state="two",
                                        window_count=1))
            self.boundary.drain()
        for sequence in range(MAX_PENDING + 1, MAX_PENDING + MAX_HISTORY + 2):
            self.boundary.ingest(_event(sequence=sequence, state="two",
                                        window_count=1))
            self.boundary.drain()
        self.assertEqual(len(self.boundary.history), MAX_HISTORY)

    def test_history_snapshot_is_immutable_and_cached(self):
        self.boundary.ingest(_event(state="two", window_count=1))
        self.boundary.drain()
        first = self.boundary.history
        self.assertIs(first, self.boundary.history)
        with self.assertRaises(AttributeError):
            first.append(None)
        self.boundary.ingest(_event(sequence=2, state="three", window_count=1))
        self.boundary.drain()
        self.assertIsNot(first, self.boundary.history)

    def test_close_fails_closed(self):
        self.boundary.ingest(_event(state="two", window_count=1))
        self.boundary.drain()
        self.boundary.close()
        self.assertTrue(self.boundary.closed)
        self.assertEqual(self.boundary.pending, 0)
        self.assertEqual(self.boundary.history, ())
        for action in (lambda: self.boundary.ingest(_event(sequence=2)),
                       self.boundary.drain,
                       self.boundary.snapshot):
            with self.assertRaises(WorkspaceBehaviorClosed):
                action()
        self.boundary.close()

    def test_hostile_context_types_rejected(self):
        for kwargs in (
            {"workspace": object()},
            {"active": True},
            {"active": "bad/id"},
            {"capabilities": ["switch"]},
            {"capabilities": frozenset({"unknown"})},
            {"negotiation": object()},
            {"max_pending": MAX_PENDING + 1},
            {"max_drain": 0},
            {"history_limit": 0},
            {"source": None},
        ):
            with self.subTest(kwargs=kwargs):
                values = dict(
                    workspace=self.inventory, active="one",
                    negotiation=_negotiation(),
                    capabilities=frozenset({contracts.CAPABILITY_SWITCH}),
                )
                values.update(kwargs)
                with self.assertRaises(WorkspaceBehaviorError):
                    WorkspaceBehaviorBoundary(**values)


if __name__ == "__main__":
    unittest.main()
