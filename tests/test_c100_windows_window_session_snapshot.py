"""Tests for the bounded, immutable host-facing window/session snapshot.

The snapshot composes the already-tested value objects from ``switcher_state``,
``workspace_inventory``, ``wayland_portal_capabilities`` and
``window_state_capabilities`` into one deterministic, host-facing record.
These tests pin the contract: pure composition, bounded embedded collections,
immutable views, deterministic bytes, explicit status derivation and
fail-closed input validation.
"""

import ast
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.windows import switcher_state as switcher
from canopy_features.windows import wayland_portal_capabilities as portal
from canopy_features.windows import window_state_capabilities as wsc
from canopy_features.windows import workspace_inventory as inventory
from canopy_features.windows import window_session_snapshot as snapshot

FEATURES = wsc.WindowStateFeature


def _plain(value):
    """Recursively turn MappingProxyType views into plain dicts for JSON."""
    if isinstance(value, MappingProxyType):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def _clean_switcher():
    state = switcher.SwitcherState([10, 20, 30], current=10)
    state.begin()
    state.next()
    return state.snapshot()


def _clean_workspace():
    return inventory.build_inventory(
        [
            {"source": "test", "name": "Alpha", "identifier": "alpha"},
            {"source": "test", "name": "Beta", "identifier": "beta"},
        ],
        permitted_sources=frozenset({"test"}),
    )


def _clean_portal(session="wayland"):
    present = ("remote_desktop", "screen_cast") if session == "wayland" else ()
    grants = ({"remote_desktop": "granted", "screen_cast": "granted"}
              if session == "wayland" else {})
    return portal.describe(session, present, grants)


def _clean_negotiation():
    return wsc.negotiate(
        "x11", [FEATURES.MINIMIZE, FEATURES.MAXIMIZE, FEATURES.RESTORE])


def _compose_clean():
    return snapshot.compose(
        _clean_switcher(), _clean_workspace(), _clean_portal(),
        _clean_negotiation())


def _encode(record):
    return json.dumps(_plain(record.to_dict()), sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


class WindowSessionSnapshotTests(unittest.TestCase):
    def test_composes_real_value_objects(self):
        record = _compose_clean()
        self.assertIsInstance(record, snapshot.WindowSessionSnapshot)
        self.assertEqual(record.schema, snapshot.SCHEMA)
        self.assertTrue(record.switcher.active)
        self.assertEqual(record.switcher.current, 10)
        self.assertEqual(record.switcher.selected, 20)
        self.assertEqual(record.switcher.window_count, 3)
        self.assertEqual(record.switcher.order, (10, 20, 30))
        self.assertEqual(record.workspace.workspace_count, 2)
        self.assertEqual(record.workspace.identifiers, ("alpha", "beta"))
        self.assertEqual(record.workspace.problem_count, 0)
        self.assertEqual(record.portal.session_type, "wayland")
        self.assertTrue(record.portal.wayland)
        self.assertEqual(record.portal.window_enumeration, "NOT_PERFORMED")
        self.assertEqual(record.portal.capability_count, 2)
        self.assertEqual(record.portal.usable,
                         ("remote_desktop", "screen_cast"))
        self.assertEqual(record.portal.denied, ())
        self.assertEqual(record.negotiation.backend, "x11")
        self.assertEqual(record.negotiation.status, "SUPPORTED")
        self.assertEqual(record.negotiation.granted,
                         ("maximize", "minimize", "restore"))
        self.assertTrue(record.negotiation.supported)
        self.assertEqual(record.status, snapshot.STATUS_OK)

    def test_record_and_nested_views_are_frozen(self):
        record = _compose_clean()
        with self.assertRaises(FrozenInstanceError):
            record.status = snapshot.STATUS_BLOCKED
        with self.assertRaises(FrozenInstanceError):
            record.switcher.order = ()
        with self.assertRaises(FrozenInstanceError):
            record.workspace.identifiers = ()
        with self.assertRaises(FrozenInstanceError):
            record.portal.usable = ()
        with self.assertRaises(FrozenInstanceError):
            record.negotiation.granted = ()

    def test_to_dict_is_a_read_only_view(self):
        record = _compose_clean()
        view = record.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        with self.assertRaises(TypeError):
            view["status"] = "tampered"
        with self.assertRaises(TypeError):
            view["switcher"]["window_count"] = 99
        with self.assertRaises(TypeError):
            view["negotiation"]["granted"] = ()
        self.assertEqual(view["switcher"]["order"], (10, 20, 30))

    def test_deterministic_bytes_for_equal_inputs(self):
        self.assertEqual(_encode(_compose_clean()), _encode(_compose_clean()))
        self.assertIn(b'"schema":1', _encode(_compose_clean()))

    def test_order_invariant_projections(self):
        portal_a = portal.describe(
            "wayland", ["remote_desktop", "screen_cast"],
            {"remote_desktop": "granted", "screen_cast": "granted"})
        portal_b = portal.describe(
            "wayland", ["screen_cast", "remote_desktop"],
            {"screen_cast": "granted", "remote_desktop": "granted"})
        negotiation_a = wsc.negotiate(
            "x11", [FEATURES.MINIMIZE, FEATURES.MAXIMIZE, FEATURES.RESTORE])
        negotiation_b = wsc.negotiate(
            "x11", [FEATURES.RESTORE, FEATURES.MINIMIZE, FEATURES.MAXIMIZE])
        record_a = snapshot.compose(
            _clean_switcher(), _clean_workspace(), portal_a, negotiation_a)
        record_b = snapshot.compose(
            _clean_switcher(), _clean_workspace(), portal_b, negotiation_b)
        self.assertEqual(_encode(record_a), _encode(record_b))

    def test_switcher_order_is_bounded_even_for_oversized_view(self):
        oversized = switcher.SwitchState(False, None, None, tuple(range(1, 101)))
        record = snapshot.compose(
            oversized, _clean_workspace(), _clean_portal(),
            _clean_negotiation())
        self.assertEqual(record.switcher.window_count, 100)
        self.assertEqual(len(record.switcher.order), snapshot.MAX_WINDOWS)
        self.assertEqual(record.switcher.order,
                         tuple(range(1, snapshot.MAX_WINDOWS + 1)))

    def test_workspace_identifiers_are_bounded(self):
        workspaces = tuple(
            inventory.Workspace("id" + str(index), "Name " + str(index), "test")
            for index in range(100))
        oversized = inventory.WorkspaceInventory(workspaces, ())
        record = snapshot.compose(
            _clean_switcher(), oversized, _clean_portal(),
            _clean_negotiation())
        self.assertEqual(record.workspace.workspace_count, 100)
        self.assertEqual(len(record.workspace.identifiers),
                         snapshot.MAX_WORKSPACES)

    def test_problem_notes_are_bounded(self):
        problems = tuple(
            inventory.WorkspaceProblem("record[" + str(index) + "]", "x" * 5000)
            for index in range(50))
        oversized = inventory.WorkspaceInventory((), problems)
        record = snapshot.compose(
            _clean_switcher(), oversized, _clean_portal(),
            _clean_negotiation())
        self.assertEqual(record.workspace.problem_count, 50)
        self.assertEqual(len(record.workspace.problem_reasons),
                         snapshot.MAX_PROBLEMS)
        self.assertTrue(all(len(reason) == snapshot.MAX_CHARS
                            for reason in record.workspace.problem_reasons))

    def test_status_blocked_on_unsupported_negotiation(self):
        negotiation = wsc.negotiate("headless", [FEATURES.MINIMIZE])
        record = snapshot.compose(
            _clean_switcher(), _clean_workspace(), _clean_portal(),
            negotiation)
        self.assertEqual(record.status, snapshot.STATUS_BLOCKED)
        self.assertTrue(record.is_blocked)

    def test_status_blocked_on_portal_denial(self):
        report = portal.describe(
            "wayland", ("remote_desktop",), {"remote_desktop": "denied"})
        record = snapshot.compose(
            _clean_switcher(), _clean_workspace(), report,
            _clean_negotiation())
        self.assertEqual(record.portal.denied, ("remote_desktop",))
        self.assertEqual(record.status, snapshot.STATUS_BLOCKED)

    def test_status_attention_on_partial_negotiation(self):
        negotiation = wsc.negotiate(
            "wayland", [FEATURES.MINIMIZE, FEATURES.MAXIMIZE])
        record = snapshot.compose(
            _clean_switcher(), _clean_workspace(), _clean_portal(),
            negotiation)
        self.assertEqual(record.negotiation.status, "PARTIAL")
        self.assertEqual(record.status, snapshot.STATUS_ATTENTION)

    def test_status_attention_on_missing_portal(self):
        report = portal.describe("wayland", (), {})
        record = snapshot.compose(
            _clean_switcher(), _clean_workspace(), report,
            _clean_negotiation())
        self.assertEqual(record.portal.missing,
                         ("remote_desktop", "screen_cast"))
        self.assertEqual(record.status, snapshot.STATUS_ATTENTION)

    def test_status_attention_on_workspace_problems(self):
        workspaces = _clean_workspace()
        report = inventory.build_inventory(
            [{"source": "test", "name": "Ok", "identifier": "ok"},
             {"source": "test", "name": "Bad\u0007Name"}],
            permitted_sources=frozenset({"test"}))
        self.assertGreater(len(report.problems), 0)
        record = snapshot.compose(
            _clean_switcher(), report, _clean_portal(),
            _clean_negotiation())
        self.assertGreater(record.workspace.problem_count, 0)
        self.assertEqual(record.status, snapshot.STATUS_ATTENTION)

    def test_status_attention_on_empty_switcher(self):
        empty = switcher.SwitcherState([]).snapshot()
        record = snapshot.compose(
            empty, _clean_workspace(), _clean_portal(),
            _clean_negotiation())
        self.assertEqual(record.switcher.window_count, 0)
        self.assertEqual(record.status, snapshot.STATUS_ATTENTION)

    def test_status_attention_on_x11_session(self):
        record = snapshot.compose(
            _clean_switcher(), _clean_workspace(), _clean_portal("x11"),
            _clean_negotiation())
        self.assertEqual(record.portal.session_type, "x11")
        self.assertFalse(record.portal.wayland)
        self.assertEqual(record.status, snapshot.STATUS_ATTENTION)

    def test_wrong_component_types_fail_closed(self):
        good = (_clean_switcher(), _clean_workspace(), _clean_portal(),
                _clean_negotiation())
        bad_values = (None, 7, "token", [], {})
        for index in range(4):
            for bad in bad_values:
                args = list(good)
                args[index] = bad
                with self.subTest(index=index, bad=type(bad).__name__):
                    with self.assertRaises(snapshot.SnapshotError):
                        snapshot.compose(*args)

    def test_malformed_portal_report_fails_closed(self):
        good = _clean_portal()
        bad_reports = (
            replace(good, window_enumeration="PERFORMED"),
            replace(good, schema_version=99),
            replace(good, session_type="solaris"),
            replace(good, wayland=False),
            replace(good, usable=frozenset({"bogus"})),
            replace(good, denied=["remote_desktop"]),
        )
        for bad in bad_reports:
            with self.subTest(bad=bad):
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.compose(_clean_switcher(), _clean_workspace(),
                                     bad, _clean_negotiation())

    def test_malformed_negotiation_fails_closed(self):
        bad_negotiations = (
            wsc.Negotiation("x11", "BOGUS", frozenset({FEATURES.MINIMIZE})),
            wsc.Negotiation("x11", "SUPPORTED", frozenset({"minimize"})),
            wsc.Negotiation("", "SUPPORTED", frozenset({FEATURES.MINIMIZE})),
            wsc.Negotiation("x11", "SUPPORTED", ["minimize"]),
        )
        for bad in bad_negotiations:
            with self.subTest(bad=bad):
                with self.assertRaises(snapshot.SnapshotError):
                    snapshot.compose(_clean_switcher(), _clean_workspace(),
                                     _clean_portal(), bad)

    def test_no_acceptance_or_enumeration_claim(self):
        record = _compose_clean()
        self.assertEqual(record.acceptance, snapshot.ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(record.portal.window_enumeration, "NOT_PERFORMED")
        encoded = json.dumps(_plain(record.to_dict())).lower()
        for forbidden in ("approved", "mint_ran", "qt_accepted",
                          "enumeration_performed"):
            self.assertNotIn(forbidden, encoded)

    def test_module_is_pure(self):
        source = Path(snapshot.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = {"time", "datetime", "random", "subprocess", "socket",
                     "threading", "asyncio", "os", "tempfile"}
        self.assertFalse(imported & forbidden)
        self.assertNotIn("open(", source)


if __name__ == "__main__":
    unittest.main()
