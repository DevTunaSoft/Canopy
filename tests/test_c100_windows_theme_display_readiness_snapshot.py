"""Tests for the bounded, immutable theme/portal/display readiness snapshot."""

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.reliability import screen_topology_change as topology
from canopy_features.reliability import theme_transition_rollback as theme
from canopy_features.reliability.theme_transition_rollback import Snapshot
from canopy_features.windows import wayland_portal_capabilities as portal


def _m():
    from canopy_features.windows import theme_display_readiness_snapshot as module
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


def _theme():
    return theme.ThemeTransitionRollback()


def _portal():
    return portal.describe(
        "wayland", ("remote_desktop", "screen_cast"),
        {"remote_desktop": "granted", "screen_cast": "granted"})


def _display():
    return topology.ScreenTopologyModel().apply(topology.Topology(
        [topology.Monitor("eDP-1", 1920, 1080, True)]))


def _compose_clean():
    return _m().compose(_theme(), _portal(), _display())


class ThemeDisplayReadinessSnapshotTests(unittest.TestCase):
    def test_composes_real_value_objects(self):
        record = _compose_clean()
        m = _m()
        self.assertIsInstance(record, m.ThemeDisplayReadinessSnapshot)
        self.assertEqual(record.schema, m.SCHEMA)
        self.assertEqual(record.theme.state, theme.IDLE)
        self.assertTrue(record.theme.single_owner)
        self.assertEqual(record.portal.session_type, "wayland")
        self.assertEqual(record.portal.usable,
                         ("remote_desktop", "screen_cast"))
        self.assertEqual(record.portal.window_enumeration, "NOT_PERFORMED")
        self.assertEqual(record.display.monitor_count, 1)
        self.assertFalse(record.display.suspended)
        self.assertEqual(record.status, m.STATUS_OK)

    def test_record_and_nested_views_are_frozen(self):
        record = _compose_clean()
        for target, field in ((record, "status"), (record.theme, "abandoned"),
                              (record.portal, "usable"),
                              (record.display, "action_kinds")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(target, field, "mutated")

    def test_to_dict_is_fresh_read_only_view(self):
        record = _compose_clean()
        view = record.to_dict()
        again = record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        self.assertIsNot(view, again)
        for key in ("theme", "portal", "display"):
            self.assertIsNot(view[key], again[key])
        with self.assertRaises(TypeError):
            view["status"] = "tampered"
        with self.assertRaises(TypeError):
            view["portal"]["usable"] = ()

    def test_to_dict_key_order_is_fixed(self):
        view = _compose_clean().to_dict()
        self.assertEqual(tuple(view), (
            "schema", "status", "acceptance", "observation",
            "theme", "portal", "display"))
        self.assertEqual(tuple(view["theme"]), (
            "state", "active", "candidate", "single_owner",
            "live_resource_count", "abandoned"))
        self.assertEqual(tuple(view["portal"]), (
            "session_type", "wayland", "window_enumeration", "usable",
            "denied", "missing", "unknown_permission"))
        self.assertEqual(tuple(view["display"]), (
            "sequence", "monitor_count", "connectors", "action_kinds",
            "suspended"))

    def test_deterministic_bytes_for_equal_inputs(self):
        self.assertEqual(_encode(_compose_clean()), _encode(_compose_clean()))

    def test_portal_ids_are_sorted_and_bounded(self):
        report = portal.describe("wayland", ("screen_cast", "remote_desktop"),
                                 {"screen_cast": "granted",
                                  "remote_desktop": "granted"})
        record = _m().compose(_theme(), report, _display())
        self.assertEqual(record.portal.usable,
                         ("remote_desktop", "screen_cast"))

    def test_long_text_is_bounded(self):
        ledger = theme.ThemeTransitionRollback()
        ledger.prepare("x" * 500, {"r1"})
        record = _m().compose(ledger, _portal(), _display())
        self.assertEqual(record.theme.candidate, "x" * _m().MAX_CHARS)

    def test_status_blocked_for_uncommitted_theme(self):
        ledger = theme.ThemeTransitionRollback()
        ledger.prepare("candidate", {"r1"})
        record = _m().compose(ledger, _portal(), _display())
        self.assertEqual(record.status, _m().STATUS_BLOCKED)
        self.assertTrue(record.is_blocked)

    def test_status_blocked_for_portal_denial(self):
        report = portal.describe("wayland", ("remote_desktop", "screen_cast"),
                                 {"remote_desktop": "denied",
                                  "screen_cast": "granted"})
        record = _m().compose(_theme(), report, _display())
        self.assertEqual(record.status, _m().STATUS_BLOCKED)

    def test_status_blocked_for_suspended_display(self):
        suspended = topology.ScreenTopologyModel().apply(topology.Topology([]))
        record = _m().compose(_theme(), _portal(), suspended)
        self.assertEqual(record.status, _m().STATUS_BLOCKED)

    def test_status_attention_for_missing_portal(self):
        report = portal.describe("wayland", ("screen_cast",),
                                 {"screen_cast": "granted"})
        record = _m().compose(_theme(), report, _display())
        self.assertEqual(record.status, _m().STATUS_ATTENTION)

    def test_fixed_negative_claims_under_adversarial_input(self):
        ledger = theme.ThemeTransitionRollback()
        ledger.prepare("candidate", {"r1"})
        record = _m().compose(ledger, _portal(), _display())
        self.assertEqual(record.acceptance, _m().ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(record.observation, _m().OBSERVATION_NOT_PERFORMED)

    def test_fail_closed_wrong_components(self):
        for args in ((None, _portal(), _display()),
                     (_theme(), None, _display()),
                     (_theme(), _portal(), None)):
            with self.subTest(args=len(args)):
                with self.assertRaises(_m().SnapshotError):
                    _m().compose(*args)

    def test_fail_closed_theme_contradiction(self):
        class ContradictorySnapshot(Snapshot):
            @property
            def single_owner(self):
                return True

        ledger = theme.ThemeTransitionRollback()
        fake = ContradictorySnapshot(theme.IDLE, None, None,
                                     frozenset({"r1"}), frozenset({"r1"}))
        object.__setattr__(ledger, "snapshot", lambda: fake)
        with self.assertRaises(_m().SnapshotError):
            _m().compose(ledger, _portal(), _display())

    def test_fail_closed_idle_theme_with_pending_candidate(self):
        # The ledger invariant is: state == IDLE iff candidate is None.
        # prepare() sets the candidate and PREPARED together, and
        # _clear_candidate() clears both together. A hostile but bounded
        # snapshot that reports IDLE while still carrying a candidate label
        # must not be projected as a ready (STATUS_OK) theme.
        fake = Snapshot(theme.IDLE, "active-theme", "pending-theme",
                        frozenset({"live"}), frozenset())
        ledger = theme.ThemeTransitionRollback()
        object.__setattr__(ledger, "snapshot", lambda: fake)
        with self.assertRaises(_m().SnapshotError):
            _m().compose(ledger, _portal(), _display())

    def test_cross_call_independence_no_mutable_alias(self):
        ledger = theme.ThemeTransitionRollback()
        record = _m().compose(ledger, _portal(), _display())
        before = _encode(record)
        ledger.prepare("candidate", {"r1"})
        self.assertEqual(_encode(record), before)
        view = record.to_dict()
        for field in ("abandoned", "usable", "denied", "connectors",
                      "action_kinds"):
            key = "theme" if field == "abandoned" else (
                "portal" if field in ("usable", "denied") else "display")
            self.assertIsInstance(view[key][field], tuple)

    def test_no_partial_record_on_rejection(self):
        with self.assertRaises(_m().SnapshotError):
            _m().compose(_theme(), _portal(), object())

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
