"""Tests for the bounded window/topology recovery snapshot composition."""

import ast
import pathlib
import unittest
from dataclasses import FrozenInstanceError
from types import MappingProxyType

from canopy_features.reliability.screen_topology_change import (
    Monitor, Topology, RecoveryAction, RecoveryResult, ScreenTopologyModel,
    ACTION_SUSPEND,
)
from canopy_features.windows.window_state_capabilities import (
    WindowStateAction, WindowState, WindowStateFeature,
    Negotiation, TransitionResult, WindowStateController, negotiate,
)
from canopy_features.windows.window_close_intents import (
    IntentResult, CloseIntentModel, NO_STATE,
)


def _m():
    from canopy_features.windows import window_topology_snapshot as module
    return module


def _normal_recovery(model=None, connector="eDP-1", width=1920, height=1080):
    model = model or ScreenTopologyModel()
    return model.apply(Topology([Monitor(connector, width, height, True)]))


def _supported():
    negotiation = negotiate("x11", [
        WindowStateFeature.MINIMIZE,
        WindowStateFeature.MAXIMIZE,
        WindowStateFeature.RESTORE,
    ])
    transition = WindowStateController(negotiation).apply(
        WindowStateAction.MAXIMIZE)
    return negotiation, transition


def _normal_close():
    model = CloseIntentModel()
    model.register("files.win", "shell.owner", state={"page": "home"})
    return (model.request_close("files.win", "shell.owner"),)


class WindowTopologySnapshotTests(unittest.TestCase):
    def test_compose_real_value_objects(self):
        m = _m()
        recovery = _normal_recovery()
        negotiation, transition = _supported()
        snap = m.compose(recovery, negotiation, transition, _normal_close())
        self.assertEqual(snap.schema, 1)
        self.assertEqual(snap.display.sequence, 1)
        self.assertEqual(snap.display.monitor_count, 1)
        self.assertEqual(snap.display.connectors, ("eDP-1",))
        self.assertFalse(snap.display.suspended)
        self.assertIn("reanchor_primary", snap.display.action_kinds)
        self.assertEqual(snap.state.backend, "x11")
        self.assertEqual(snap.state.negotiation_status, "SUPPORTED")
        self.assertEqual(snap.state.granted,
                         ("maximize", "minimize", "restore"))
        self.assertEqual(snap.state.window_state, "maximized")
        self.assertEqual(snap.state.transition_status, "OK")
        self.assertEqual(snap.close.decision_count, 1)
        self.assertEqual(snap.close.statuses, ("CLOSED",))
        self.assertEqual(snap.close.visible_flags, (False,))
        self.assertEqual(snap.close.window_ids, ("files.win",))

    def test_record_and_nested_views_are_frozen(self):
        m = _m()
        negotiation, transition = _supported()
        snap = m.compose(_normal_recovery(), negotiation, transition)
        for target, field in ((snap, "schema"), (snap.display, "sequence"),
                              (snap.state, "backend"), (snap.close, "notes")):
            with self.subTest(field=field):
                with self.assertRaises(FrozenInstanceError):
                    setattr(target, field, None)

    def test_to_dict_is_fresh_read_only_and_ordered(self):
        m = _m()
        negotiation, transition = _supported()
        snap = m.compose(_normal_recovery(), negotiation, transition)
        view = snap.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        self.assertEqual(list(view), [
            "schema", "status", "acceptance", "observation",
            "display", "state", "close",
        ])
        with self.assertRaises(TypeError):
            view["schema"] = 2
        other = snap.to_dict()
        self.assertIsNot(view, other)
        self.assertEqual(view, other)

    def test_deterministic_bytes_and_grant_order(self):
        m = _m()
        negotiation, transition = _supported()
        first = m.compose(_normal_recovery(), negotiation, transition,
                          _normal_close())
        second = m.compose(_normal_recovery(), negotiation, transition,
                           _normal_close())
        self.assertEqual(repr(first.to_dict()), repr(second.to_dict()))
        reversed_grants = Negotiation(
            "x11", "SUPPORTED",
            frozenset({WindowStateFeature.RESTORE,
                       WindowStateFeature.MINIMIZE,
                       WindowStateFeature.MAXIMIZE}),
        )
        third = m.compose(_normal_recovery(), reversed_grants, transition)
        self.assertEqual(third.state.granted, first.state.granted)
        self.assertEqual(repr(third.to_dict()), repr(
            m.compose(_normal_recovery(), reversed_grants, transition).to_dict()))

    def test_close_decision_cap(self):
        m = _m()
        # Build 17 real IntentResult values directly: CloseIntentModel itself
        # caps registrations at 16, so a model cannot produce the 17th input.
        results = [IntentResult("w%s.win" % index, "CLOSED", False,
                                NO_STATE, "") for index in range(17)]
        negotiation, transition = _supported()
        snap = m.compose(_normal_recovery(), negotiation, transition, results)
        self.assertEqual(snap.close.decision_count, 17)
        self.assertEqual(len(snap.close.statuses), 16)
        self.assertEqual(len(snap.close.window_ids), 16)

    def test_long_text_is_bounded(self):
        m = _m()
        negotiation = Negotiation("x" * 200, "PARTIAL",
                                  frozenset({WindowStateFeature.MAXIMIZE}))
        transition = TransitionResult("REJECTED", WindowState.NORMAL,
                                      "r" * 200)
        decision = IntentResult("files.win", "CLOSED", False, NO_STATE,
                                "n" * 200)
        snap = m.compose(_normal_recovery(), negotiation, transition,
                         (decision,))
        self.assertEqual(len(snap.state.backend), 160)
        self.assertEqual(len(snap.state.transition_reason), 160)
        self.assertEqual(len(snap.close.notes[0]), 160)

    def test_status_ok(self):
        m = _m()
        negotiation, transition = _supported()
        snap = m.compose(_normal_recovery(), negotiation, transition,
                         _normal_close())
        self.assertEqual(snap.status, "OK")
        self.assertFalse(snap.is_blocked)

    def test_status_blocked_suspended(self):
        m = _m()
        recovery = ScreenTopologyModel().apply(Topology(()))
        self.assertTrue(recovery.action_kinds == (ACTION_SUSPEND,))
        negotiation, _ = _supported()
        transition = TransitionResult("OK", WindowState.NORMAL)
        snap = m.compose(recovery, negotiation, transition)
        self.assertTrue(snap.display.suspended)
        self.assertEqual(snap.status, "BLOCKED")

    def test_status_blocked_unsupported_negotiation(self):
        m = _m()
        negotiation = negotiate("headless", [WindowStateFeature.MINIMIZE])
        transition = WindowStateController(negotiation).apply(
            WindowStateAction.MINIMIZE)
        self.assertEqual(transition.reason, "FEATURE_NOT_GRANTED")
        snap = m.compose(_normal_recovery(), negotiation, transition)
        self.assertEqual(snap.status, "BLOCKED")

    def test_status_blocked_hard_close(self):
        m = _m()
        model = CloseIntentModel()
        model.register("files.win", "shell.owner", guarded=True)
        decision = model.request_close("files.win", "shell.owner")
        self.assertEqual(decision.status, "GUARDED")
        negotiation, transition = _supported()
        snap = m.compose(_normal_recovery(), negotiation, transition,
                         (decision,))
        self.assertEqual(snap.status, "BLOCKED")

    def test_status_blocked_invalid_transition(self):
        m = _m()
        negotiation, _ = _supported()
        controller = WindowStateController(negotiation)
        controller.apply(WindowStateAction.MAXIMIZE)
        transition = controller.apply(WindowStateAction.MINIMIZE)
        self.assertEqual(transition.reason, "INVALID_TRANSITION")
        snap = m.compose(_normal_recovery(), negotiation, transition)
        self.assertEqual(snap.status, "BLOCKED")

    def test_status_attention_clamp(self):
        m = _m()
        recovery = _normal_recovery(width=1000, height=700)
        self.assertIn("clamp_resolution", recovery.action_kinds)
        negotiation, transition = _supported()
        snap = m.compose(recovery, negotiation, transition)
        self.assertEqual(snap.status, "ATTENTION")

    def test_status_attention_partial(self):
        m = _m()
        negotiation = negotiate("wayland", [
            WindowStateFeature.MINIMIZE, WindowStateFeature.MAXIMIZE,
        ])
        self.assertEqual(negotiation.status, "PARTIAL")
        transition = WindowStateController(negotiation).apply(
            WindowStateAction.MAXIMIZE)
        snap = m.compose(_normal_recovery(), negotiation, transition)
        self.assertEqual(snap.status, "ATTENTION")

    def test_status_attention_soft_close(self):
        m = _m()
        model = CloseIntentModel()
        model.register("files.win", "shell.owner")
        model.request_close("files.win", "shell.owner")
        decision = model.request_close("files.win", "shell.owner")
        self.assertEqual(decision.status, "ALREADY_CLOSED")
        negotiation, transition = _supported()
        snap = m.compose(_normal_recovery(), negotiation, transition,
                         (decision,))
        self.assertEqual(snap.status, "ATTENTION")

    def test_status_attention_other_rejection(self):
        m = _m()
        negotiation, _ = _supported()
        transition = TransitionResult("REJECTED", WindowState.NORMAL,
                                      "UNKNOWN_ACTION")
        snap = m.compose(_normal_recovery(), negotiation, transition)
        self.assertEqual(snap.status, "ATTENTION")

    def test_wrong_component_types_fail_closed(self):
        m = _m()
        negotiation, transition = _supported()
        bad = [None, 7, "x", [], {}, object()]
        for value in bad:
            with self.subTest(position="display", value=repr(value)):
                with self.assertRaises(m.SnapshotError):
                    m.compose(value, negotiation, transition)
            with self.subTest(position="negotiation", value=repr(value)):
                with self.assertRaises(m.SnapshotError):
                    m.compose(_normal_recovery(), value, transition)
            with self.subTest(position="transition", value=repr(value)):
                with self.assertRaises(m.SnapshotError):
                    m.compose(_normal_recovery(), negotiation, value)

    def test_wrong_close_sequence_types_fail_closed(self):
        m = _m()
        negotiation, transition = _supported()
        for value in (None, 7, "x", {}, ("x",), [1]):
            with self.subTest(value=repr(value)):
                with self.assertRaises(m.SnapshotError):
                    m.compose(_normal_recovery(), negotiation, transition,
                              value)

    def test_contradiction_unsupported_plus_ok(self):
        m = _m()
        negotiation = Negotiation("headless", "UNSUPPORTED", frozenset())
        transition = TransitionResult("OK", WindowState.NORMAL)
        with self.assertRaises(m.SnapshotError):
            m.compose(_normal_recovery(), negotiation, transition)

    def test_contradiction_supported_empty_granted(self):
        m = _m()
        negotiation = Negotiation("x11", "SUPPORTED", frozenset())
        transition = TransitionResult("REJECTED", WindowState.NORMAL, "X")
        with self.assertRaises(m.SnapshotError):
            m.compose(_normal_recovery(), negotiation, transition)

    def test_contradiction_suspended_with_monitors(self):
        m = _m()
        recovery = RecoveryResult(
            1, (), (RecoveryAction(ACTION_SUSPEND),),
            Topology([Monitor("eDP-1", 1920, 1080, True)]),
        )
        negotiation, transition = _supported()
        with self.assertRaises(m.SnapshotError):
            m.compose(recovery, negotiation, transition)

    def test_unknown_action_kind_rejected(self):
        m = _m()
        recovery = RecoveryResult(1, (), (RecoveryAction("bogus"),),
                                  Topology([Monitor("eDP-1", 1920, 1080)]))
        negotiation, transition = _supported()
        with self.assertRaises(m.SnapshotError):
            m.compose(recovery, negotiation, transition)

    def test_no_acceptance_or_observation_claim(self):
        m = _m()
        negotiation, transition = _supported()
        snap = m.compose(_normal_recovery(), negotiation, transition)
        self.assertEqual(snap.acceptance, "NOT_ESTABLISHED")
        self.assertEqual(snap.observation, "NOT_PERFORMED")
        self.assertEqual(snap.to_dict()["acceptance"], "NOT_ESTABLISHED")
        self.assertEqual(snap.to_dict()["observation"], "NOT_PERFORMED")

    def test_purity_ast(self):
        m = _m()
        source = pathlib.Path(m.__file__).read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0]
                               for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        forbidden = {"os", "sys", "socket", "subprocess", "threading",
                     "time", "datetime", "random", "asyncio", "PySide6",
                     "PyQt6"}
        self.assertFalse(imports & forbidden)


if __name__ == "__main__":
    unittest.main()
