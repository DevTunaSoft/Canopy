"""Tests for the bounded immutable boot/backend capability snapshot."""

import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest
from types import MappingProxyType

from canopy_features.reliability import startup_checkpoints as cp
from canopy_features.windows import wayland_portal_capabilities as portal
from canopy_features.windows import window_state_capabilities as wsc


def _m():
    from canopy_features.windows import boot_backend_snapshot as module
    return module


def _plain(v):
    if isinstance(v, MappingProxyType):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, tuple):
        return tuple(_plain(x) for x in v)
    return v


def _enc(r):
    return json.dumps(_plain(r.to_dict()), sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _startup():
    return cp.RecoveryDecision(cp.READY, ("shell",), (), None, "durable")


def _portal():
    return portal.describe("wayland", ("remote_desktop", "screen_cast"),
                           {"remote_desktop": "granted",
                            "screen_cast": "granted"})


def _neg():
    return wsc.negotiate("x11", [wsc.WindowStateFeature.MINIMIZE])


def _clean():
    return _m().compose(_startup(), _portal(), _neg())


class BootBackendSnapshotTests(unittest.TestCase):
    def test_composes_real_value_objects(self):
        r = _clean()
        self.assertIsInstance(r, _m().BootBackendSnapshot)
        self.assertEqual(r.startup.action, cp.READY)
        self.assertEqual(r.startup.completed_count, 1)
        self.assertEqual(r.portal.usable, ("remote_desktop", "screen_cast"))
        self.assertEqual(r.negotiation.granted, ("minimize",))
        self.assertEqual(r.status, _m().STATUS_OK)

    def test_record_and_nested_views_frozen(self):
        r = _clean()
        for target, field in ((r, "status"), (r.startup, "reason"),
                              (r.portal, "usable"), (r.negotiation, "granted")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(target, field, "mutated")

    def test_to_dict_fresh_read_only_ordered(self):
        r = _clean()
        a, b = r.to_dict(), r.to_dict()
        self.assertIsInstance(a, MappingProxyType)
        self.assertIsNot(a, b)
        for key in ("startup", "portal", "negotiation"):
            self.assertIsNot(a[key], b[key])
        self.assertEqual(tuple(a), ("schema", "status", "acceptance",
                                    "observation", "startup", "portal",
                                    "negotiation"))
        with self.assertRaises(TypeError):
            a["status"] = "tampered"

    def test_deterministic_bytes(self):
        self.assertEqual(_enc(_clean()), _enc(_clean()))

    def test_long_text_bounded(self):
        decision = cp.RecoveryDecision(cp.READY, (), (), None, "x" * 500)
        r = _m().compose(decision, _portal(), _neg())
        self.assertEqual(r.startup.reason, "x" * _m().MAX_CHARS)

    def test_status_blocked_for_fail_closed(self):
        decision = cp.RecoveryDecision(cp.FAIL_CLOSED, (), (), None, "unsafe")
        r = _m().compose(decision, _portal(), _neg())
        self.assertEqual(r.status, _m().STATUS_BLOCKED)
        self.assertTrue(r.is_blocked)

    def test_status_blocked_for_portal_denial(self):
        report = portal.describe("wayland", ("remote_desktop", "screen_cast"),
                                 {"remote_desktop": "denied",
                                  "screen_cast": "granted"})
        r = _m().compose(_startup(), report, _neg())
        self.assertEqual(r.status, _m().STATUS_BLOCKED)

    def test_status_blocked_for_unsupported_negotiation(self):
        report = portal.describe("x11", (), {})
        negotiation = wsc.Negotiation("x11", "UNSUPPORTED", frozenset())
        r = _m().compose(_startup(), report, negotiation)
        self.assertEqual(r.status, _m().STATUS_BLOCKED)

    def test_fixed_negative_claims(self):
        decision = cp.RecoveryDecision(cp.ROLLBACK, (), (), None, "r")
        r = _m().compose(decision, _portal(), _neg())
        self.assertEqual(r.acceptance, _m().ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(r.observation, _m().OBSERVATION_NOT_PERFORMED)

    def test_fail_closed_wrong_components(self):
        for args in ((None, _portal(), _neg()), (_startup(), None, _neg()),
                     (_startup(), _portal(), None)):
            with self.subTest(args=len(args)):
                with self.assertRaises(_m().SnapshotError):
                    _m().compose(*args)

    def test_fail_closed_unknown_action(self):
        decision = cp.RecoveryDecision("FORGED", (), (), None, "r")
        with self.assertRaises(_m().SnapshotError):
            _m().compose(decision, _portal(), _neg())

    def test_cross_call_independence(self):
        decision, report, negotiation = _startup(), _portal(), _neg()
        r = _m().compose(decision, report, negotiation)
        before = _enc(r)
        object.__setattr__(decision, "reason", "changed")
        self.assertEqual(_enc(r), before)

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
