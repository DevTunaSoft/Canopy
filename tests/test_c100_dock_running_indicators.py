"""Offline regression tests for bounded dock running-indicator state."""
from __future__ import annotations

import dataclasses
import inspect
import unittest

from canopy_features.dock import dock_running_indicators as indicators


class IndicatorStateTests(unittest.TestCase):
    def test_empty_state_has_no_indicators(self):
        state = indicators.empty_state()
        self.assertEqual(state.sequence, -1)
        self.assertEqual(indicators.indicator_ids(state), ())
        self.assertFalse(indicators.has_indicator(state, "nemo"))
        self.assertEqual(indicators.running_pid_count(state, "nemo"), 0)

    def test_start_creates_indicator_and_exit_removes_it(self):
        state = indicators.empty_state()
        state = indicators.apply_event(state, indicators.AppStarted(0, "nemo", 101))
        self.assertEqual(indicators.indicator_ids(state), ("nemo",))
        self.assertTrue(indicators.has_indicator(state, "nemo"))
        state = indicators.apply_event(state, indicators.AppExited(1, "nemo", 101))
        self.assertEqual(indicators.indicator_ids(state), ())

    def test_multiple_processes_keep_indicator_until_last_exit(self):
        state = indicators.empty_state()
        state = indicators.apply_events(state, [
            indicators.AppStarted(0, "firefox", 200),
            indicators.AppStarted(1, "firefox", 201),
        ])
        self.assertEqual(indicators.running_pid_count(state, "firefox"), 2)
        state = indicators.apply_event(state, indicators.AppExited(2, "firefox", 200))
        self.assertTrue(indicators.has_indicator(state, "firefox"))
        state = indicators.apply_event(state, indicators.AppExited(3, "firefox", 201))
        self.assertFalse(indicators.has_indicator(state, "firefox"))

    def test_out_of_order_events_are_ignored(self):
        state = indicators.apply_event(
            indicators.empty_state(), indicators.AppStarted(5, "nemo", 101))
        earlier = indicators.apply_event(state, indicators.AppExited(4, "nemo", 101))
        self.assertEqual(earlier, state)
        self.assertTrue(indicators.has_indicator(state, "nemo"))

    def test_duplicate_sequence_and_start_are_idempotent(self):
        state = indicators.apply_event(
            indicators.empty_state(), indicators.AppStarted(3, "nemo", 101))
        duplicate = indicators.apply_event(state, indicators.AppStarted(3, "nemo", 101))
        self.assertEqual(duplicate, state)
        repeated = indicators.apply_event(state, indicators.AppStarted(4, "nemo", 101))
        self.assertEqual(repeated.sequence, 4)
        self.assertEqual(indicators.running_pid_count(repeated, "nemo"), 1)

    def test_pid_reuse_transfers_ownership(self):
        state = indicators.apply_events(indicators.empty_state(), [
            indicators.AppStarted(0, "nemo", 777),
            indicators.AppStarted(1, "terminal", 777),
        ])
        self.assertEqual(indicators.indicator_ids(state), ("terminal",))
        self.assertEqual(indicators.running_pid_count(state, "nemo"), 0)

    def test_stale_exit_cannot_clear_new_pid_owner(self):
        state = indicators.apply_events(indicators.empty_state(), [
            indicators.AppStarted(0, "nemo", 777),
            indicators.AppStarted(1, "terminal", 777),
            indicators.AppExited(2, "nemo", 777),
        ])
        self.assertEqual(indicators.indicator_ids(state), ("terminal",))
        self.assertEqual(state.sequence, 2)

    def test_unknown_owner_exit_is_ignored_but_advances_sequence(self):
        state = indicators.apply_events(indicators.empty_state(), [
            indicators.AppStarted(0, "nemo", 101),
            indicators.AppExited(1, "terminal", 101),
        ])
        self.assertEqual(indicators.indicator_ids(state), ("nemo",))
        self.assertEqual(state.sequence, 1)

    def test_indicator_ids_are_sorted_and_unique(self):
        state = indicators.apply_events(indicators.empty_state(), [
            indicators.AppStarted(0, "terminal", 2),
            indicators.AppStarted(1, "nemo", 1),
            indicators.AppStarted(2, "terminal", 3),
        ])
        self.assertEqual(indicators.indicator_ids(state), ("nemo", "terminal"))

    def test_per_app_pid_cap_is_bounded(self):
        events = [indicators.AppStarted(i, "nemo", 100 + i)
                  for i in range(indicators.MAX_PIDS_PER_APP + 2)]
        state = indicators.apply_events(indicators.empty_state(), events)
        self.assertEqual(indicators.running_pid_count(state, "nemo"),
                         indicators.MAX_PIDS_PER_APP)
        self.assertEqual(state.sequence, events[-1].sequence)

    def test_app_cap_is_bounded(self):
        events = [indicators.AppStarted(i, f"app-{i}", 1000 + i)
                  for i in range(indicators.MAX_APPS + 4)]
        state = indicators.apply_events(indicators.empty_state(), events)
        self.assertEqual(len(indicators.indicator_ids(state)), indicators.MAX_APPS)

    def test_state_is_immutable(self):
        state = indicators.apply_event(
            indicators.empty_state(), indicators.AppStarted(0, "nemo", 101))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            state.sequence = 9

    def test_event_validation_is_bounded(self):
        bad_events = [
            indicators.AppStarted(-1, "nemo", 101),
            indicators.AppStarted(0, "", 101),
            indicators.AppStarted(0, "x" * (indicators.MAX_ID_LENGTH + 1), 101),
            indicators.AppStarted(0, "nemo", 0),
            indicators.AppStarted(0, "nemo", indicators.MAX_PID + 1),
            indicators.AppStarted(True, "nemo", 101),
            indicators.AppExited(0, "nemo", -3),
        ]
        for event in bad_events:
            with self.subTest(event=event), self.assertRaises(ValueError):
                indicators.apply_event(indicators.empty_state(), event)
        with self.assertRaises(ValueError):
            indicators.apply_event(indicators.empty_state(), object())

    def test_batches_are_bounded(self):
        with self.assertRaises(ValueError):
            indicators.apply_events(indicators.empty_state(), [object()] * 1025)
        with self.assertRaises(ValueError):
            indicators.apply_events(indicators.empty_state(), "not-a-batch")


class PurityTests(unittest.TestCase):
    def test_no_runtime_or_ui_dependencies(self):
        source = inspect.getsource(indicators)
        for token in ("subprocess", "socket", "threading", "PyQt", "PySide",
                      "QML", " open(", "time.", "requests"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_only_dataclasses_is_imported(self):
        imports = [line.strip() for line in inspect.getsource(indicators).splitlines()
                   if line.startswith(("import ", "from "))]
        self.assertEqual(imports, [
            "from __future__ import annotations",
            "from dataclasses import dataclass",
        ])


class DuplicateOwnerPidTests(unittest.TestCase):
    """A snapshot must never claim two live processes for one real PID.

    PR #482 denied duplicate pinned ids in the action preview but left a
    host-supplied ``IndicatorState(owners=((101, app), (101, app)))`` able to
    compose an APPROVED preview with ``running_pids=2``. One PID is one live
    process, so such a snapshot is malformed and must fail closed before any
    count, indicator or approval can be derived from it.
    """

    def assert_duplicate_pid_rejected(self, owners):
        with self.subTest(owners=owners), self.assertRaises(ValueError):
            indicators.IndicatorState(sequence=7, owners=owners)

    def test_duplicate_pid_same_app_is_rejected(self):
        self.assert_duplicate_pid_rejected(((101, "nemo"), (101, "nemo")))

    def test_duplicate_pid_conflicting_apps_is_rejected(self):
        self.assert_duplicate_pid_rejected(((101, "nemo"), (101, "mail")))

    def test_triple_duplicate_pid_is_rejected(self):
        self.assert_duplicate_pid_rejected(
            ((101, "nemo"), (101, "nemo"), (101, "nemo")))

    def test_duplicate_pid_rejected_through_replace(self):
        state = indicators.apply_event(
            indicators.empty_state(), indicators.AppStarted(0, "nemo", 101))
        with self.assertRaises(ValueError):
            dataclasses.replace(state, owners=((101, "nemo"), (101, "nemo")))

    def test_public_readers_reject_corrupt_snapshot(self):
        # Simulate a state that bypassed construction, so the guard is proved
        # at every reading boundary and not only in the dataclass constructor.
        state = indicators.empty_state()
        object.__setattr__(state, "owners", ((101, "nemo"), (101, "nemo")))
        for reader in (indicators.indicator_ids,
                       lambda s: indicators.has_indicator(s, "nemo"),
                       lambda s: indicators.running_pid_count(s, "nemo"),
                       lambda s: indicators.apply_event(
                           s, indicators.AppStarted(1, "nemo", 102)),
                       lambda s: indicators.apply_events(
                           s, (indicators.AppStarted(1, "nemo", 102),))):
            with self.subTest(reader=reader), self.assertRaises(ValueError):
                reader(state)

    def test_absent_pid_is_not_a_duplicate(self):
        state = indicators.IndicatorState(
            sequence=7, owners=((101, "nemo"), (102, "mail")))
        self.assertEqual(indicators.running_pid_count(state, "nemo"), 1)

    def test_distinct_pids_same_app_still_approved_by_count(self):
        state = indicators.apply_events(indicators.empty_state(), [
            indicators.AppStarted(0, "nemo", 101),
            indicators.AppStarted(1, "nemo", 102),
        ])
        self.assertEqual(indicators.running_pid_count(state, "nemo"), 2)

    def test_other_malformed_shapes_remain_constructible(self):
        # The preview already denies these with invalid_indicators; this guard
        # must not turn them into constructor errors.
        self.assertEqual(
            indicators.IndicatorState(sequence=3, owners=((101, "nemo", 9),)).owners,
            ((101, "nemo", 9),))
        self.assertTrue(
            indicators.IndicatorState(sequence=True, owners=()).sequence)


if __name__ == "__main__":
    unittest.main()
