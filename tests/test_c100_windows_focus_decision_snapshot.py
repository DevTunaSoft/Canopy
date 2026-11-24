"""Tests for the bounded, immutable host-facing focus-decision snapshot."""

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.windows import focus_intents as focus
from canopy_features.windows import switcher_state as switcher
from canopy_features.windows import workspace_inventory as inventory


def _m():
    from canopy_features.windows import focus_decision_snapshot as module
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


def _focus(grant=True, activate=True, decisions=1):
    policy = focus.PermissionPolicy()
    if grant:
        policy.grant("shell", "files")
    broker = focus.FocusBroker(
        policy.authorize,
        activate=(lambda *_: True) if activate else None)
    ref = broker.register_window("files", 10)
    for _ in range(decisions):
        broker.request_focus(focus.FocusIntent("shell", ref))
    return broker, policy


def _workspace():
    return inventory.build_inventory(
        [{"source": "test", "name": "Alpha", "identifier": "alpha"},
         {"source": "test", "name": "Beta", "identifier": "beta"}],
        permitted_sources=frozenset({"test"}))


def _switcher():
    state = switcher.SwitcherState([10, 20, 30], current=10)
    state.begin()
    state.next()
    return state.snapshot()


def _compose_clean():
    broker, policy = _focus()
    return _m().compose(broker, _workspace(), _switcher(), policy)


class FocusDecisionSnapshotTests(unittest.TestCase):
    def test_composes_real_value_objects(self):
        record = _compose_clean()
        m = _m()
        self.assertIsInstance(record, m.FocusDecisionSnapshot)
        self.assertEqual(record.schema, m.SCHEMA)
        self.assertEqual(record.focus.live_windows, 1)
        self.assertEqual(record.focus.grant_count, 1)
        self.assertEqual(record.focus.decision_count, 1)
        self.assertEqual(record.focus.statuses, ("GRANTED",))
        self.assertEqual(record.focus.target_apps, ("files",))
        self.assertEqual(record.workspace.workspace_count, 2)
        self.assertEqual(record.workspace.identifiers, ("alpha", "beta"))
        self.assertEqual(record.workspace.problem_count, 0)
        self.assertEqual(record.switcher.current, 10)
        self.assertEqual(record.switcher.selected, 20)
        self.assertEqual(record.switcher.order, (10, 20, 30))
        self.assertEqual(record.status, m.STATUS_ATTENTION)

    def test_record_and_nested_views_are_frozen(self):
        record = _compose_clean()
        for target, field in ((record, "status"), (record.focus, "statuses"),
                              (record.workspace, "identifiers"),
                              (record.switcher, "order")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(target, field, "mutated")

    def test_to_dict_is_fresh_read_only_view(self):
        record = _compose_clean()
        view = record.to_dict()
        again = record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        self.assertIsNot(view, again)
        for key in ("focus", "workspace", "switcher"):
            self.assertIsNot(view[key], again[key])
        with self.assertRaises(TypeError):
            view["status"] = "tampered"
        with self.assertRaises(TypeError):
            view["focus"]["statuses"] = ()

    def test_to_dict_key_order_is_fixed(self):
        view = _compose_clean().to_dict()
        self.assertEqual(tuple(view), (
            "schema", "status", "acceptance", "observation",
            "focus", "workspace", "switcher"))
        self.assertEqual(tuple(view["focus"]), (
            "live_windows", "grant_count", "decision_count", "statuses",
            "target_apps", "reasons"))
        self.assertEqual(tuple(view["workspace"]), (
            "workspace_count", "identifiers", "problem_count",
            "problem_reasons"))
        self.assertEqual(tuple(view["switcher"]), (
            "active", "current", "selected", "window_count", "order"))

    def test_deterministic_bytes_for_equal_inputs(self):
        self.assertEqual(_encode(_compose_clean()), _encode(_compose_clean()))

    def test_decision_history_is_bounded(self):
        broker, policy = _focus(decisions=22)
        record = _m().compose(broker, _workspace(), _switcher(), policy)
        self.assertEqual(record.focus.decision_count, 22)
        self.assertEqual(len(record.focus.statuses), _m().MAX_DECISIONS)
        self.assertEqual(len(record.focus.reasons), _m().MAX_DECISIONS)

    def test_workspace_collections_are_bounded(self):
        workspaces = tuple(inventory.Workspace("w%d" % i, "W%d" % i, "test")
                           for i in range(70))
        problems = tuple(inventory.WorkspaceProblem("p%d" % i, "reason")
                         for i in range(40))
        inv = inventory.WorkspaceInventory(workspaces, problems)
        record = _m().compose(_focus()[0], inv, _switcher())
        self.assertEqual(record.workspace.workspace_count, 70)
        self.assertEqual(record.workspace.problem_count, 40)
        self.assertEqual(len(record.workspace.identifiers), _m().MAX_WORKSPACES)
        self.assertEqual(len(record.workspace.problem_reasons),
                         _m().MAX_PROBLEMS)

    def test_long_text_is_bounded(self):
        broker = focus.FocusBroker(lambda *_: True)
        ref = broker.register_window("files", 10)
        broker.request_focus(focus.FocusIntent("shell", ref))
        object.__setattr__(broker, "_history", (
            focus.FocusDecision(focus.GRANTED, None, "files", "x" * 500),))
        record = _m().compose(broker, _workspace(), _switcher())
        self.assertEqual(record.focus.reasons, ("x" * _m().MAX_CHARS,))

    def test_status_ok_for_quiet_state(self):
        empty_inv = inventory.WorkspaceInventory((), ())
        state = switcher.SwitchState(False, None, None, (10, 20))
        record = _m().compose(focus.FocusBroker(lambda *_: True),
                              empty_inv, state)
        self.assertEqual(record.status, _m().STATUS_OK)
        self.assertFalse(record.is_blocked)

    def test_status_blocked_for_failed_focus(self):
        broker, policy = _focus(grant=False)
        record = _m().compose(broker, _workspace(), _switcher(), policy)
        self.assertEqual(record.status, _m().STATUS_BLOCKED)
        self.assertTrue(record.is_blocked)

    def test_fixed_negative_claims_under_adversarial_input(self):
        broker, policy = _focus(grant=False)
        record = _m().compose(broker, _workspace(), _switcher(), policy)
        self.assertEqual(record.acceptance, _m().ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(record.observation, _m().OBSERVATION_NOT_PERFORMED)

    def test_optional_policy_records_none_grant_count(self):
        record = _m().compose(_focus()[0], _workspace(), _switcher())
        self.assertIsNone(record.focus.grant_count)

    def test_fail_closed_wrong_components(self):
        for args in ((None, _workspace(), _switcher()),
                     (_focus()[0], None, _switcher()),
                     (_focus()[0], _workspace(), None),
                     (_focus()[0], _workspace(), _switcher(), object())):
            with self.subTest(args=len(args)):
                with self.assertRaises(_m().SnapshotError):
                    _m().compose(*args)

    def test_fail_closed_unknown_focus_status(self):
        broker = focus.FocusBroker(lambda *_: True)
        object.__setattr__(broker, "_history", (
            focus.FocusDecision("FORGED", None),))
        with self.assertRaises(_m().SnapshotError):
            _m().compose(broker, _workspace(), _switcher())

    def test_fail_closed_switcher_bool_id(self):
        state = switcher.SwitchState(False, 10, None, (10, 20))
        object.__setattr__(state, "current", True)
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_focus()[0], _workspace(), state)

    def test_fail_closed_bad_workspace_record(self):
        inv = inventory.WorkspaceInventory((object(),), ())
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_focus()[0], inv, _switcher())

    def test_cross_call_independence_no_mutable_alias(self):
        broker, policy = _focus()
        record = _m().compose(broker, _workspace(), _switcher(), policy)
        before = _encode(record)
        object.__setattr__(policy, "_grants", set())
        broker.register_window("shell", 99)
        self.assertEqual(_encode(record), before)
        view = record.to_dict()
        for field in ("statuses", "target_apps", "reasons"):
            self.assertIsInstance(view["focus"][field], tuple)
        self.assertIsInstance(view["workspace"]["identifiers"], tuple)
        self.assertIsInstance(view["switcher"]["order"], tuple)

    def test_no_partial_record_on_rejection(self):
        inv = inventory.WorkspaceInventory((object(),), ())
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_focus()[0], inv, _switcher())

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
