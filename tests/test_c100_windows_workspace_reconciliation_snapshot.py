"""Tests for the bounded, immutable workspace-reconciliation snapshot."""

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.reliability import screen_topology_change as topology
from canopy_features.windows import window_close_intents as close
from canopy_features.windows import workspace_inventory as inventory


def _m():
    from canopy_features.windows import workspace_reconciliation_snapshot as module
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


def _inv(records):
    return inventory.build_inventory(records,
                                     permitted_sources=frozenset({"test"}))


def _reconciliation():
    previous = _inv([{"source": "test", "name": "Alpha",
                      "identifier": "alpha"}])
    current = _inv([{"source": "test", "name": "Alpha Renamed",
                     "identifier": "alpha"},
                    {"source": "test", "name": "Beta",
                     "identifier": "beta"}])
    return inventory.reconcile(previous, current)


def _quiet_reconciliation():
    inv = _inv([{"source": "test", "name": "Alpha", "identifier": "alpha"}])
    return inventory.reconcile(inv, inv)


def _recovery():
    return topology.ScreenTopologyModel().apply(topology.Topology(
        [topology.Monitor("eDP-1", 1920, 1080, True)]))


def _decisions():
    return (close.IntentResult("files.win", close.CLOSED, False,
                               close.NO_STATE, "window parked; state preserved"),)


def _compose_clean():
    return _m().compose(_reconciliation(), _recovery(), _decisions())


class WorkspaceReconciliationSnapshotTests(unittest.TestCase):
    def test_composes_real_value_objects(self):
        record = _compose_clean()
        m = _m()
        self.assertIsInstance(record, m.WorkspaceReconciliationSnapshot)
        self.assertEqual(record.schema, m.SCHEMA)
        self.assertEqual(record.workspace.workspace_count, 2)
        self.assertEqual(record.workspace.identifiers, ("alpha", "beta"))
        self.assertEqual(record.workspace.added, ("beta",))
        self.assertEqual(record.workspace.renamed, ("alpha",))
        self.assertEqual(record.workspace.removed, ())
        self.assertEqual(record.display.sequence, 1)
        self.assertEqual(record.display.monitor_count, 1)
        self.assertEqual(record.close.statuses, (close.CLOSED,))
        self.assertEqual(record.status, m.STATUS_ATTENTION)

    def test_record_and_nested_views_are_frozen(self):
        record = _compose_clean()
        for target, field in ((record, "status"), (record.workspace, "added"),
                              (record.display, "sequence"),
                              (record.close, "notes")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(target, field, "mutated")

    def test_to_dict_is_fresh_read_only_view(self):
        record = _compose_clean()
        view = record.to_dict()
        again = record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        self.assertIsNot(view, again)
        for key in ("workspace", "display", "close"):
            self.assertIsNot(view[key], again[key])
        with self.assertRaises(TypeError):
            view["status"] = "tampered"
        with self.assertRaises(TypeError):
            view["workspace"]["added"] = ()

    def test_to_dict_key_order_is_fixed(self):
        view = _compose_clean().to_dict()
        self.assertEqual(tuple(view), (
            "schema", "status", "acceptance", "observation",
            "workspace", "display", "close"))
        self.assertEqual(tuple(view["workspace"]), (
            "workspace_count", "identifiers", "problem_count",
            "problem_reasons", "added", "removed", "renamed", "reordered"))
        self.assertEqual(tuple(view["display"]), (
            "sequence", "monitor_count", "action_kinds", "suspended"))
        self.assertEqual(tuple(view["close"]), (
            "decision_count", "window_ids", "statuses", "notes"))

    def test_deterministic_bytes_for_equal_inputs(self):
        self.assertEqual(_encode(_compose_clean()), _encode(_compose_clean()))

    def test_close_decision_cap(self):
        decisions = tuple(close.IntentResult("w%d.win" % i, close.CLOSED,
                                             False, close.NO_STATE, "")
                          for i in range(22))
        record = _m().compose(_quiet_reconciliation(), _recovery(), decisions)
        self.assertEqual(record.close.decision_count, 22)
        self.assertEqual(len(record.close.statuses), _m().MAX_DECISIONS)

    def test_workspace_collections_are_bounded(self):
        inv = inventory.WorkspaceInventory(
            tuple(inventory.Workspace("w%d" % i, "W%d" % i, "test")
                  for i in range(70)), ())
        rec = inventory.Reconciliation(inv, tuple("a%d" % i for i in range(70)),
                                       (), (), ())
        record = _m().compose(rec, _recovery())
        self.assertEqual(record.workspace.workspace_count, 70)
        self.assertEqual(len(record.workspace.identifiers), _m().MAX_IDS)
        self.assertEqual(len(record.workspace.added), _m().MAX_IDS)

    def test_long_text_is_bounded(self):
        decision = close.IntentResult("files.win", close.CLOSED, False,
                                      close.NO_STATE, "x" * 500)
        record = _m().compose(_quiet_reconciliation(), _recovery(),
                              (decision,))
        self.assertEqual(record.close.notes, ("x" * _m().MAX_CHARS,))

    def test_status_ok_for_quiet_state(self):
        record = _m().compose(_quiet_reconciliation(), _recovery())
        self.assertEqual(record.status, _m().STATUS_OK)
        self.assertFalse(record.is_blocked)

    def test_status_blocked_for_suspended_display(self):
        model = topology.ScreenTopologyModel()
        suspended = model.apply(topology.Topology([]))
        record = _m().compose(_quiet_reconciliation(), suspended)
        self.assertEqual(record.status, _m().STATUS_BLOCKED)
        self.assertTrue(record.is_blocked)

    def test_status_blocked_for_hard_close_denial(self):
        for status in (close.UNKNOWN_WINDOW, close.OWNERSHIP_DENIED,
                       close.GUARDED):
            with self.subTest(status=status):
                decision = close.IntentResult("files.win", status, None,
                                              close.NO_STATE, "")
                record = _m().compose(_quiet_reconciliation(), _recovery(),
                                      (decision,))
                self.assertEqual(record.status, _m().STATUS_BLOCKED)

    def test_fixed_negative_claims_under_adversarial_input(self):
        decision = close.IntentResult("files.win", close.CLOSED, False,
                                      close.NO_STATE, "ACCEPTED PASS MINT")
        record = _m().compose(_reconciliation(), _recovery(), (decision,))
        self.assertEqual(record.acceptance, _m().ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(record.observation, _m().OBSERVATION_NOT_PERFORMED)

    def test_fail_closed_wrong_components(self):
        for args in ((None, _recovery()),
                     (_reconciliation(), None),
                     (_reconciliation(), _recovery(), (object(),))):
            with self.subTest(args=len(args)):
                with self.assertRaises(_m().SnapshotError):
                    _m().compose(*args)

    def test_fail_closed_unknown_close_status(self):
        decision = close.IntentResult("files.win", "FORGED", False,
                                      close.NO_STATE, "")
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_quiet_reconciliation(), _recovery(), (decision,))

    def test_fail_closed_unknown_action_kind(self):
        recovery = _recovery()
        object.__setattr__(recovery, "actions",
                           (topology.RecoveryAction("FORGED"),))
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_quiet_reconciliation(), recovery)

    def test_cross_call_independence_no_mutable_alias(self):
        decisions = [close.IntentResult("files.win", close.CLOSED, False,
                                        close.NO_STATE, "original")]
        record = _m().compose(_reconciliation(), _recovery(), decisions)
        before = _encode(record)
        decisions.clear()
        self.assertEqual(_encode(record), before)
        view = record.to_dict()
        for field in ("identifiers", "added", "removed", "renamed", "reordered"):
            self.assertIsInstance(view["workspace"][field], tuple)
        self.assertIsInstance(view["display"]["action_kinds"], tuple)
        self.assertIsInstance(view["close"]["statuses"], tuple)

    def test_no_partial_record_on_rejection(self):
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_quiet_reconciliation(), _recovery(),
                         [close.IntentResult("files.win", close.CLOSED, False,
                                             close.NO_STATE, "ok"), object()])

    def test_close_decisions_accept_list(self):
        decisions = [close.IntentResult("files.win", close.CLOSED, False,
                                        close.NO_STATE, "")]
        record = _m().compose(_quiet_reconciliation(), _recovery(), decisions)
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
