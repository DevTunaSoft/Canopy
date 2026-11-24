"""Regression tests for single-allocation indicator event folding.

Run: python -m unittest tests.test_c100_dock_indicator_fold_allocation -v
"""
import random
import unittest
from unittest.mock import patch

from canopy_features.dock import dock_running_indicators as indicators_mod
from canopy_features.dock.dock_running_indicators import (
    AppExited,
    AppStarted,
    IndicatorState,
    apply_event,
    apply_events,
    empty_state,
)


def reference_events(state, events):
    """Original per-event algorithm, kept as an independent oracle."""
    current = state
    for event in events:
        current = apply_event_reference(current, event)
    return current


def apply_event_reference(state, event):
    if not isinstance(event, (AppStarted, AppExited)):
        raise ValueError("unsupported event type")
    if isinstance(event.sequence, bool) or not isinstance(event.sequence, int):
        raise ValueError("sequence must be an integer")
    if event.sequence < 0:
        raise ValueError("sequence must be non-negative")
    if not isinstance(event.app_id, str) or not event.app_id or len(event.app_id) > 128:
        raise ValueError("invalid app_id")
    if isinstance(event.pid, bool) or not isinstance(event.pid, int) or not 1 <= event.pid <= 2**31 - 1:
        raise ValueError("invalid pid")
    if not isinstance(state, IndicatorState):
        raise ValueError("state must be an IndicatorState")
    if event.sequence <= state.sequence:
        return state
    owners = dict(state.owners)
    if isinstance(event, AppStarted):
        previous = owners.get(event.pid)
        if previous is not None and previous != event.app_id:
            del owners[event.pid]
        elif previous == event.app_id:
            owners = dict(state.owners)
            return IndicatorState(sequence=event.sequence, owners=tuple(sorted(owners.items())))
        pid_count = sum(1 for owner in owners.values() if owner == event.app_id)
        app_count = len(set(owners.values()) | {event.app_id})
        if pid_count >= 8 or app_count > 64:
            return IndicatorState(sequence=event.sequence, owners=state.owners)
        owners[event.pid] = event.app_id
    else:
        if owners.get(event.pid) != event.app_id:
            return IndicatorState(sequence=event.sequence, owners=state.owners)
        del owners[event.pid]
    return IndicatorState(sequence=event.sequence, owners=tuple(sorted(owners.items())))


def make_events(seed):
    rng = random.Random(seed)
    events = []
    for index in range(180):
        sequence = max(1, index + 1 - rng.randint(0, 3))
        pid = 1000 + rng.randint(0, 20)
        app = "App%d" % rng.randint(0, 9)
        cls = AppStarted if rng.random() < 0.7 else AppExited
        events.append(cls(sequence=sequence, app_id=app, pid=pid))
    return tuple(events)


class AllocationTests(unittest.TestCase):
    def test_one_state_constructed_per_batch(self):
        events = tuple(AppStarted(sequence=i + 1, app_id="App%d" % (i % 8),
                                  pid=10000 + i) for i in range(256))
        state = empty_state()
        with patch.object(indicators_mod, "IndicatorState",
                          wraps=IndicatorState) as spy:
            apply_events(state, events)
        self.assertEqual(spy.call_count, 1)

    def test_empty_batch_returns_same_state(self):
        state = empty_state()
        self.assertIs(apply_events(state, ()), state)

    def test_stale_event_still_validated(self):
        state = IndicatorState(sequence=10, owners=())
        with self.assertRaises(ValueError):
            apply_events(state, (AppStarted(sequence=1, app_id="App", pid=True),))

    def test_wrong_events_type_still_rejected(self):
        for bad in ("events", {1: 2}, None, 7):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    apply_events(empty_state(), bad)

    def test_oversized_batch_still_rejected(self):
        events = tuple(AppStarted(sequence=i + 1, app_id="App", pid=100 + i)
                       for i in range(1025))
        with self.assertRaises(ValueError):
            apply_events(empty_state(), events)


class EquivalenceTests(unittest.TestCase):
    def test_matches_reference_for_mixed_batches(self):
        for seed in range(12):
            with self.subTest(seed=seed):
                events = make_events(seed)
                self.assertEqual(
                    apply_events(empty_state(), events),
                    reference_events(empty_state(), events))

    def test_capacity_and_pid_reuse_preserved(self):
        events = make_events(7)
        expected = reference_events(empty_state(), events)
        result = apply_events(empty_state(), events)
        self.assertEqual(result.sequence, expected.sequence)
        self.assertEqual(result.owners, expected.owners)

    def test_single_event_api_unchanged(self):
        state = IndicatorState(sequence=1, owners=((100, "App"),))
        self.assertEqual(
            apply_event(state, AppExited(sequence=2, app_id="App", pid=100)),
            IndicatorState(sequence=2, owners=()))


if __name__ == "__main__":
    unittest.main()
