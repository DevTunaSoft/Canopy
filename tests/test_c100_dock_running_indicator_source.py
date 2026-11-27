"""Offline regression tests for the dock running-indicator source contract."""
from __future__ import annotations

import ast
import dataclasses
import inspect
import unittest

from canopy_features.dock import dock_running_indicators as indicators
from canopy_features.dock import dock_running_indicator_source as source
from canopy_features.windows.window_state_capabilities import (
    REF_LIVE, REF_STALE, REF_UNKNOWN, REF_UNAUTHORIZED,
)


def event(sequence, status=REF_LIVE, app_id="nemo", pid=101,
          window_id=7, opened=True):  # noqa: ANN001 - hostile fixtures need loose types
    return source.WindowStateEvent(sequence, status, app_id, pid,
                                   window_id, opened)


class ProjectionTests(unittest.TestCase):
    def test_empty_batch_leaves_state_unchanged(self):
        state = indicators.empty_state()
        result = source.project(state, [])
        self.assertEqual(result.sequence, -1)
        self.assertEqual(result.events, ())
        self.assertEqual(result.ignored, 0)
        self.assertIs(result.indicators, state)
        self.assertEqual(result.indicator_ids(), ())

    def test_live_open_then_close_drives_indicator(self):
        state = indicators.empty_state()
        opened = source.project(state, [event(0)])
        self.assertEqual(opened.ignored, 0)
        self.assertEqual(opened.indicator_ids(), ("nemo",))
        self.assertEqual(len(opened.events), 1)
        closed = source.project(opened.indicators, [event(1, opened=False)])
        self.assertEqual(closed.indicator_ids(), ())
        self.assertEqual(closed.sequence, 1)

    def test_stale_ref_is_ignored_but_advances_sequence(self):
        stale = event(0, REF_STALE, "nemo", 100)
        live = event(1, REF_LIVE, "terminal", 101, window_id=8)
        result = source.project(indicators.empty_state(), [stale, live])
        self.assertEqual(result.ignored, 1)
        self.assertEqual(result.sequence, 1)
        self.assertEqual(result.indicator_ids(), ("terminal",))
        self.assertFalse(indicators.has_indicator(result.indicators, "nemo"))

    def test_unknown_and_unauthorized_refs_are_ignored(self):
        events = [
            event(0, REF_UNKNOWN, "nemo", 100),
            event(1, REF_UNAUTHORIZED, "terminal", 101),
            event(2, REF_LIVE, "files", 102, window_id=9),
        ]
        result = source.project(indicators.empty_state(), events)
        self.assertEqual(result.ignored, 2)
        self.assertEqual(result.indicator_ids(), ("files",))

    def test_live_event_after_stale_ref_still_applies(self):
        state = source.project(
            indicators.empty_state(),
            [event(0, REF_STALE), event(1, REF_LIVE, pid=202)]).indicators
        self.assertEqual(source.project(
            state, [event(2, REF_LIVE, opened=False, pid=202)]).indicator_ids(),
            ())

    def test_out_of_order_event_cannot_clear_indicator(self):
        state = source.project(indicators.empty_state(), [event(5)]).indicators
        result = source.project(state, [event(4, opened=False)])
        self.assertEqual(result.ignored, 1)
        self.assertEqual(result.sequence, 5)
        self.assertEqual(result.indicator_ids(), ("nemo",))

    def test_duplicate_sequence_is_idempotent(self):
        state = source.project(indicators.empty_state(), [event(3)]).indicators
        result = source.project(state, [event(3, opened=False)])
        self.assertEqual(result.ignored, 1)
        self.assertIs(result.indicators, state)

    def test_close_for_unknown_app_cannot_manufacture_indicator(self):
        result = source.project(
            indicators.empty_state(), [event(0, opened=False)])
        self.assertEqual(result.indicator_ids(), ())
        self.assertEqual(result.sequence, 0)
        self.assertEqual(len(result.events), 1)

    def test_per_app_pid_cap_is_inherited(self):
        events = [event(i, pid=300 + i)
                  for i in range(indicators.MAX_PIDS_PER_APP + 3)]
        result = source.project(indicators.empty_state(), events)
        self.assertEqual(indicators.running_pid_count(result.indicators, "nemo"),
                         indicators.MAX_PIDS_PER_APP)

    def test_apply_window_events_returns_state_only(self):
        state = source.apply_window_events(indicators.empty_state(), [event(0)])
        self.assertIsInstance(state, indicators.IndicatorState)
        self.assertEqual(indicators.indicator_ids(state), ("nemo",))

    def test_projection_is_immutable(self):
        result = source.project(indicators.empty_state(), [event(0)])
        with self.assertRaises(dataclasses.FrozenInstanceError):
            setattr(result, "ignored", 9)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            setattr(result, "events", ())

    def test_source_identity(self):
        self.assertEqual(source.SOURCE, "window-state")
        self.assertEqual(source.VALID_STATUSES,
                         frozenset({REF_LIVE, REF_STALE, REF_UNKNOWN,
                                    REF_UNAUTHORIZED}))


class ValidationTests(unittest.TestCase):
    def test_wrong_event_type_fails_closed(self):
        for bad in (None, "event", {"sequence": 0},
                    indicators.AppStarted(0, "nemo", 101)):
            with self.subTest(bad=bad), self.assertRaises(source.SourceContractError):
                source.project(indicators.empty_state(), [bad])

    def test_hostile_event_fields_fail_closed(self):
        bad_events = [
            event(-1),
            event(source.MAX_SEQUENCE + 1),
            event(True),
            event(0, "OTHER"),
            event(0, []),  # unhashable status must not leak TypeError
            event(0, REF_LIVE, ""),
            event(0, REF_LIVE, "bad app"),
            event(0, REF_LIVE, "x" * (source.MAX_APP_ID_LENGTH + 1)),
            event(0, REF_LIVE, "nemo", 0),
            event(0, REF_LIVE, "nemo", source.MAX_PID + 1),
            event(0, REF_LIVE, "nemo", 101, 0),
            event(0, REF_LIVE, "nemo", 101, source.MAX_WINDOW_ID + 1),
            event(0, REF_LIVE, "nemo", 101, 7, 1),
        ]
        for bad in bad_events:
            with self.subTest(bad=bad), self.assertRaises(source.SourceContractError):
                source.project(indicators.empty_state(), [bad])

    def test_wrong_batch_types_fail_closed(self):
        for bad in ("events", b"events", {"0": 1}, {1, 2}, (x for x in [])):
            with self.subTest(bad=type(bad)), self.assertRaises(source.SourceContractError):
                source.project(indicators.empty_state(), bad)

    def test_oversized_finite_batch_is_rejected(self):
        events = [event(i, pid=400 + i) for i in range(source.MAX_EVENTS + 1)]
        with self.assertRaises(source.SourceContractError):
            source.project(indicators.empty_state(), events)

    def test_rejected_batch_leaves_caller_state_unchanged(self):
        state = source.project(indicators.empty_state(), [event(0)]).indicators
        with self.assertRaises(source.SourceContractError):
            source.project(state, [event(1, opened=False), event(2, REF_LIVE, "")])
        self.assertEqual(indicators.indicator_ids(state), ("nemo",))
        self.assertEqual(state.sequence, 0)

    def test_wrong_state_type_fails_closed(self):
        with self.assertRaises(ValueError):
            source.project(None, [event(0)])


class BoundaryTests(unittest.TestCase):
    def test_no_os_or_ui_imports(self):
        tree = ast.parse(inspect.getsource(source))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {"os", "sys", "subprocess", "socket", "threading", "time",
                     "datetime", "PyQt5", "PySide6", "shutil", "pathlib"}
        self.assertEqual(imported & forbidden, set())

    def test_event_shape_is_exactly_six_fields(self):
        names = [field.name for field in dataclasses.fields(source.WindowStateEvent)]
        self.assertEqual(names, ["sequence", "status", "app_id", "pid",
                                 "window_id", "opened"])


if __name__ == "__main__":
    unittest.main()
