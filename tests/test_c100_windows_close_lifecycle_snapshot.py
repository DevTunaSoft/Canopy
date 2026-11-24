"""Tests for the bounded, immutable close/reopen lifecycle snapshot.

The snapshot composes value objects from ``window_close_intents``,
``switcher_state`` and ``focus_intents`` into one deterministic host-facing
record. These tests pin the contract: pure composition, bounded embedded
collections, immutable views, deterministic bytes, explicit status derivation,
fixed negative claims and fail-closed input validation.
"""

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.windows import focus_intents as focus
from canopy_features.windows import switcher_state as switcher
from canopy_features.windows import window_close_intents as close


def _m():
    from canopy_features.windows import close_lifecycle_snapshot as module
    return module


def _plain(value):
    if isinstance(value, MappingProxyType):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def _encode(record):
    return json.dumps(_plain(record.to_dict()), sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _close_model():
    model = close.CloseIntentModel()
    model.register("files.win", "shell.owner", state={"page": "home"})
    return model


def _close_decisions():
    return (_close_model().request_close("files.win", "shell.owner"),)


def _switcher():
    state = switcher.SwitcherState([10, 20, 30], current=10)
    state.begin()
    state.next()
    return state.snapshot()


def _quiet_focus():
    return focus.FocusBroker(lambda *_: True)


def _focus_with_history():
    policy = focus.PermissionPolicy()
    policy.grant("shell", "files")
    broker = focus.FocusBroker(policy.authorize)
    ref = broker.register_window("files", 10)
    broker.request_focus(focus.FocusIntent("shell", ref))
    return broker, policy


def _compose_clean():
    broker, policy = _focus_with_history()
    return _m().compose(_close_model(), _switcher(), broker,
                        _close_decisions(), policy)


class CloseLifecycleSnapshotTests(unittest.TestCase):
    def test_composes_real_value_objects(self):
        record = _compose_clean()
        self.assertIsInstance(record, _m().CloseLifecycleSnapshot)
        self.assertEqual(record.schema, _m().SCHEMA)
        self.assertEqual(record.close.registered_count, 1)
        self.assertEqual(record.close.decision_count, 1)
        self.assertEqual(record.close.window_ids, ("files.win",))
        self.assertEqual(record.close.statuses, (close.CLOSED,))
        self.assertEqual(record.close.notes, ("window parked; state preserved",))
        self.assertEqual(record.switcher.current, 10)
        self.assertEqual(record.switcher.selected, 20)
        self.assertEqual(record.switcher.order, (10, 20, 30))
        self.assertEqual(record.focus.live_windows, 1)
        self.assertEqual(record.focus.grant_count, 1)
        self.assertEqual(record.focus.recent_statuses, ("GRANTED",))
        self.assertEqual(record.status, _m().STATUS_ATTENTION)

    def test_record_and_nested_views_are_frozen(self):
        record = _compose_clean()
        for target, field in ((record, "status"), (record.close, "notes"),
                              (record.switcher, "order"),
                              (record.focus, "grant_count")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(target, field, "mutated")

    def test_to_dict_is_fresh_read_only_view(self):
        record = _compose_clean()
        view = record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        again = record.to_dict()
        self.assertIsNot(view, again)
        for key in ("close", "switcher", "focus"):
            self.assertIsInstance(view[key], MappingProxyType)
            self.assertIsNot(view[key], again[key])
        with self.assertRaises(TypeError):
            view["status"] = "tampered"
        with self.assertRaises(TypeError):
            view["close"]["statuses"] = ()

    def test_to_dict_key_order_is_fixed(self):
        view = _compose_clean().to_dict()
        self.assertEqual(tuple(view), (
            "schema", "status", "acceptance", "observation",
            "close", "switcher", "focus"))
        self.assertEqual(tuple(view["close"]), (
            "registered_count", "decision_count", "window_ids", "statuses",
            "visible_flags", "notes"))
        self.assertEqual(tuple(view["switcher"]), (
            "active", "current", "selected", "window_count", "order"))
        self.assertEqual(tuple(view["focus"]), (
            "live_windows", "grant_count", "recent_statuses"))

    def test_deterministic_bytes_for_equal_inputs(self):
        self.assertEqual(_encode(_compose_clean()), _encode(_compose_clean()))

    def test_close_decision_cap(self):
        decisions = tuple(close.IntentResult("w%d.win" % i, close.CLOSED,
                                             False, close.NO_STATE, "")
                          for i in range(17))
        record = _m().compose(_close_model(), _switcher(), _quiet_focus(),
                              decisions)
        self.assertEqual(record.close.decision_count, 17)
        self.assertEqual(len(record.close.statuses), _m().MAX_DECISIONS)
        self.assertEqual(len(record.close.window_ids), _m().MAX_DECISIONS)

    def test_long_text_is_bounded(self):
        decision = close.IntentResult("files.win", close.CLOSED, False,
                                      close.NO_STATE, "x" * 500)
        record = _m().compose(_close_model(), _switcher(), _quiet_focus(),
                              (decision,))
        self.assertEqual(record.close.notes, ("x" * _m().MAX_CHARS,))

    def test_status_ok_for_quiet_state(self):
        record = _m().compose(_close_model(), _switcher(), _quiet_focus())
        self.assertEqual(record.status, _m().STATUS_OK)
        self.assertFalse(record.is_blocked)

    def test_status_attention_for_soft_noop(self):
        decisions = (close.IntentResult("files.win", close.ALREADY_OPEN, True,
                                        close.NO_STATE, ""),)
        record = _m().compose(_close_model(), _switcher(), _quiet_focus(),
                              decisions)
        self.assertEqual(record.status, _m().STATUS_ATTENTION)

    def test_status_blocked_for_hard_close_denial(self):
        for status in (close.UNKNOWN_WINDOW, close.OWNERSHIP_DENIED,
                       close.GUARDED):
            with self.subTest(status=status):
                decision = close.IntentResult("files.win", status, None,
                                              close.NO_STATE, "")
                record = _m().compose(_close_model(), _switcher(),
                                      _quiet_focus(), (decision,))
                self.assertEqual(record.status, _m().STATUS_BLOCKED)
                self.assertTrue(record.is_blocked)

    def test_blocking_decision_beyond_embedding_cap_still_blocks(self):
        # The record embeds only the newest MAX_DECISIONS entries, but a hard
        # refusal in the supplied history must still decide the status.
        for status in (close.UNKNOWN_WINDOW, close.OWNERSHIP_DENIED,
                       close.GUARDED):
            with self.subTest(status=status):
                blocking = close.IntentResult("files.win", status, None,
                                              close.NO_STATE, "")
                soft = tuple(
                    close.IntentResult("w%d.win" % i, close.CLOSED, False,
                                       close.NO_STATE, "")
                    for i in range(_m().MAX_DECISIONS))
                decisions = (blocking,) + soft
                record = _m().compose(_close_model(), _switcher(),
                                      _quiet_focus(), decisions)
                self.assertEqual(record.close.decision_count,
                                 _m().MAX_DECISIONS + 1)
                self.assertEqual(len(record.close.statuses),
                                 _m().MAX_DECISIONS)
                self.assertNotIn(status, record.close.statuses)
                self.assertEqual(record.status, _m().STATUS_BLOCKED)
                self.assertTrue(record.is_blocked)

    def test_status_blocked_for_focus_failure(self):
        broker = focus.FocusBroker(lambda *_: False)
        ref = broker.register_window("files", 10)
        broker.request_focus(focus.FocusIntent("shell", ref))
        record = _m().compose(_close_model(), _switcher(), broker)
        self.assertEqual(record.status, _m().STATUS_BLOCKED)

    def test_fixed_negative_claims_under_adversarial_input(self):
        decision = close.IntentResult("files.win", close.CLOSED, False,
                                      close.NO_STATE, "ACCEPTED PASS MINT")
        record = _m().compose(_close_model(), _switcher(), _quiet_focus(),
                              (decision,))
        self.assertEqual(record.acceptance, _m().ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(record.observation, _m().OBSERVATION_NOT_PERFORMED)
        self.assertNotIn("PASS", (record.acceptance, record.observation))

    def test_optional_policy_records_none_grant_count(self):
        record = _m().compose(_close_model(), _switcher(), _quiet_focus())
        self.assertIsNone(record.focus.grant_count)

    def test_fail_closed_wrong_components(self):
        for args in ((None, _switcher(), _quiet_focus()),
                     (_close_model(), None, _quiet_focus()),
                     (_close_model(), _switcher(), None),
                     (_close_model(), _switcher(), _quiet_focus(), (object(),))):
            with self.subTest(args=len(args)):
                with self.assertRaises(_m().SnapshotError):
                    _m().compose(*args)

    def test_fail_closed_unknown_statuses(self):
        bad_close = close.IntentResult("files.win", "FORGED", False,
                                       close.NO_STATE, "")
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_close_model(), _switcher(), _quiet_focus(),
                         (bad_close,))
        broker = focus.FocusBroker(lambda *_: True)
        object.__setattr__(broker, "_history",
                           (focus.FocusDecision("FORGED", None),))
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_close_model(), _switcher(), broker)

    def test_fail_closed_switcher_bool_id(self):
        state = switcher.SwitchState(False, 10, None, (10, 20))
        object.__setattr__(state, "current", True)
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_close_model(), state, _quiet_focus())

    def test_cross_call_independence_no_mutable_alias(self):
        decisions = [close.IntentResult("files.win", close.CLOSED, False,
                                        close.NO_STATE, "original")]
        broker, policy = _focus_with_history()
        record = _m().compose(_close_model(), _switcher(), broker,
                              decisions, policy)
        before = _encode(record)
        decisions.clear()
        object.__setattr__(policy, "_grants", set())
        broker.register_window("shell", 99)
        self.assertEqual(_encode(record), before)
        view = record.to_dict()
        for field in ("window_ids", "statuses", "visible_flags", "notes"):
            self.assertIsInstance(view["close"][field], tuple)
        self.assertIsInstance(view["switcher"]["order"], tuple)
        self.assertIsInstance(view["focus"]["recent_statuses"], tuple)

    def test_no_partial_record_on_rejection(self):
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_close_model(), _switcher(), _quiet_focus(),
                         [close.IntentResult("files.win", close.CLOSED, False,
                                             close.NO_STATE, "ok"),
                          object()])

    def test_close_decisions_accept_list(self):
        decisions = [close.IntentResult("files.win", close.CLOSED, False,
                                        close.NO_STATE, "")]
        record = _m().compose(_close_model(), _switcher(), _quiet_focus(),
                              decisions)
        self.assertEqual(record.close.statuses, (close.CLOSED,))

    def test_purity_ast(self):
        source = Path(_m().__file__).read_text(encoding="utf-8")
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
