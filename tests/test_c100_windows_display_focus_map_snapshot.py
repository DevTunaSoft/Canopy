"""Tests for the bounded immutable display/workspace/focus map snapshot."""

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.reliability import screen_topology_change as topology
from canopy_features.windows import focus_intents as focus
from canopy_features.windows import workspace_inventory as inventory


def _m():
    from canopy_features.windows import display_focus_map_snapshot as module
    return module


def _plain(value):
    if isinstance(value, MappingProxyType):
        return {k: _plain(item) for k, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def _encode(record):
    return json.dumps(_plain(record.to_dict()), sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _display():
    return topology.ScreenTopologyModel().apply(topology.Topology(
        [topology.Monitor("eDP-1", 1920, 1080, True)]))


def _workspace():
    return inventory.build_inventory(
        [{"source": "test", "name": "Alpha", "identifier": "alpha"}],
        permitted_sources=frozenset({"test"}))


def _focus(grant=True):
    policy = focus.PermissionPolicy()
    if grant:
        policy.grant("shell", "files")
    broker = focus.FocusBroker(policy.authorize)
    ref = broker.register_window("files", 10)
    broker.request_focus(focus.FocusIntent("shell", ref))
    return broker


def _compose_clean():
    return _m().compose(_display(), _workspace(), _focus())


class DisplayFocusMapSnapshotTests(unittest.TestCase):
    def test_composes_real_value_objects(self):
        record = _compose_clean()
        self.assertIsInstance(record, _m().DisplayFocusMapSnapshot)
        self.assertEqual(record.schema, _m().SCHEMA)
        self.assertEqual(record.display.monitor_count, 1)
        self.assertEqual(record.display.connectors, ("eDP-1",))
        self.assertEqual(record.workspace.identifiers, ("alpha",))
        self.assertEqual(record.focus.live_windows, 1)
        self.assertEqual(record.focus.statuses, ("GRANTED",))
        self.assertEqual(record.status, _m().STATUS_ATTENTION)

    def test_record_and_nested_views_are_frozen(self):
        record = _compose_clean()
        for target, field in ((record, "status"), (record.display, "connectors"),
                              (record.workspace, "identifiers"),
                              (record.focus, "statuses")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(target, field, "mutated")

    def test_to_dict_is_fresh_read_only_view(self):
        record = _compose_clean()
        view, again = record.to_dict(), record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        self.assertIsNot(view, again)
        for key in ("display", "workspace", "focus"):
            self.assertIsNot(view[key], again[key])
        with self.assertRaises(TypeError):
            view["status"] = "tampered"

    def test_to_dict_key_order_is_fixed(self):
        view = _compose_clean().to_dict()
        self.assertEqual(tuple(view), (
            "schema", "status", "acceptance", "observation",
            "display", "workspace", "focus"))
        self.assertEqual(tuple(view["display"]), (
            "sequence", "monitor_count", "connectors", "action_kinds",
            "suspended"))
        self.assertEqual(tuple(view["workspace"]), (
            "workspace_count", "identifiers", "problem_count",
            "problem_reasons"))
        self.assertEqual(tuple(view["focus"]), (
            "live_windows", "decision_count", "statuses", "target_apps"))

    def test_deterministic_bytes_for_equal_inputs(self):
        self.assertEqual(_encode(_compose_clean()), _encode(_compose_clean()))

    def test_collections_are_bounded(self):
        workspaces = tuple(inventory.Workspace("w%d" % i, "W%d" % i, "test")
                           for i in range(70))
        inv = inventory.WorkspaceInventory(workspaces, ())
        record = _m().compose(_display(), inv, _focus())
        self.assertEqual(record.workspace.workspace_count, 70)
        self.assertEqual(len(record.workspace.identifiers), _m().MAX_WORKSPACES)

    def test_status_ok_for_quiet_state(self):
        empty = inventory.WorkspaceInventory((), ())
        record = _m().compose(_display(), empty,
                              focus.FocusBroker(lambda *_: True))
        self.assertEqual(record.status, _m().STATUS_OK)
        self.assertFalse(record.is_blocked)

    def test_status_blocked_for_suspended_display(self):
        suspended = topology.ScreenTopologyModel().apply(topology.Topology([]))
        record = _m().compose(suspended, _workspace(),
                              focus.FocusBroker(lambda *_: True))
        self.assertEqual(record.status, _m().STATUS_BLOCKED)

    def test_status_blocked_for_failed_focus(self):
        record = _m().compose(_display(), _workspace(), _focus(grant=False))
        self.assertEqual(record.status, _m().STATUS_BLOCKED)

    def test_fixed_negative_claims(self):
        record = _m().compose(_display(), _workspace(), _focus(grant=False))
        self.assertEqual(record.acceptance, _m().ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(record.observation, _m().OBSERVATION_NOT_PERFORMED)

    def test_fail_closed_wrong_components(self):
        for args in ((None, _workspace(), _focus()),
                     (_display(), None, _focus()),
                     (_display(), _workspace(), None)):
            with self.subTest(args=len(args)):
                with self.assertRaises(_m().SnapshotError):
                    _m().compose(*args)

    def test_fail_closed_unknown_focus_status(self):
        broker = focus.FocusBroker(lambda *_: True)
        object.__setattr__(broker, "_history",
                           (focus.FocusDecision("FORGED", None),))
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_display(), _workspace(), broker)

    def test_cross_call_independence(self):
        broker = _focus()
        record = _m().compose(_display(), _workspace(), broker)
        before = _encode(record)
        broker.register_window("shell", 99)
        self.assertEqual(_encode(record), before)

    def test_no_partial_record_on_rejection(self):
        inv = inventory.WorkspaceInventory((object(),), ())
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_display(), inv, _focus())

    def test_purity_ast(self):
        source = Path(_m().__file__).read_text(encoding="utf-8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertFalse(imports & {"os", "sys", "socket", "subprocess",
                                    "threading", "time", "datetime", "random",
                                    "asyncio", "PySide6", "PyQt6"})


if __name__ == "__main__":
    unittest.main()
