"""Targeted tests for the pure workspace-switch decision contract.

The contract consumes trusted, already-negotiated window-state records and a
trusted workspace inventory. It makes a decision only: no window manager is
started, no window is activated and no desktop state is observed.
"""

import unittest
from dataclasses import FrozenInstanceError
from types import MappingProxyType

from canopy_features.windows.window_state_capabilities import (
    KNOWN_BACKENDS, Negotiation, WindowStateFeature, negotiate)
from canopy_features.windows.workspace_inventory import build_inventory
from canopy_features.windows.workspace_state_contract import (
    ACCEPTANCE_NOT_ESTABLISHED, CAPABILITIES, CAPABILITY_ENUMERATE,
    CAPABILITY_SWITCH, NATIVE_SWITCH_BACKENDS, OBSERVATION_NOT_PERFORMED,
    REASON_ALREADY_ACTIVE, REASON_BACKEND_UNSUPPORTED,
    REASON_CAPABILITY_NOT_GRANTED, REASON_UNKNOWN_TARGET,
    STATUS_FALLBACK, STATUS_NATIVE, WorkspaceContractError, decide)

ALL_FEATURES = frozenset(WindowStateFeature)
SWITCH = frozenset({CAPABILITY_SWITCH})


def _inventory():
    return build_inventory(
        [
            {"source": "wm", "identifier": "one", "name": "One"},
            {"source": "wm", "identifier": "two", "name": "Two"},
        ],
        permitted_sources=frozenset({"wm"}),
    )


def _decide(backend="x11", target="two", active="one",
            capabilities=SWITCH, negotiation=None, workspace=None):
    if negotiation is None:
        negotiation = negotiate(backend, ALL_FEATURES)
    if workspace is None:
        workspace = _inventory()
    return decide(workspace, active, target,
                  negotiation=negotiation, capabilities=capabilities)


class WorkspaceStateContractTests(unittest.TestCase):
    def test_x11_with_switch_capability_allows_native_switch(self):
        decision = _decide()
        self.assertEqual(decision.status, STATUS_NATIVE)
        self.assertTrue(decision.native_allowed)
        self.assertEqual(decision.target, "two")

    def test_wayland_with_switch_capability_falls_back(self):
        decision = _decide(backend="wayland")
        self.assertEqual(decision.status, STATUS_FALLBACK)
        self.assertFalse(decision.native_allowed)
        self.assertEqual(decision.reason, REASON_BACKEND_UNSUPPORTED)

    def test_headless_with_switch_capability_falls_back(self):
        decision = _decide(backend="headless")
        self.assertEqual(decision.status, STATUS_FALLBACK)
        self.assertEqual(decision.reason, REASON_BACKEND_UNSUPPORTED)

    def test_unknown_backend_falls_back_without_claiming_native(self):
        decision = _decide(backend="not-a-wm")
        self.assertEqual(decision.backend, "not-a-wm")
        self.assertEqual(decision.status, STATUS_FALLBACK)
        self.assertEqual(decision.reason, REASON_BACKEND_UNSUPPORTED)

    def test_x11_without_switch_capability_falls_back(self):
        decision = _decide(capabilities=frozenset({CAPABILITY_ENUMERATE}))
        self.assertEqual(decision.status, STATUS_FALLBACK)
        self.assertEqual(decision.reason, REASON_CAPABILITY_NOT_GRANTED)

    def test_unsupported_negotiation_falls_back(self):
        decision = _decide(negotiation=negotiate("headless", ALL_FEATURES))
        self.assertEqual(decision.status, STATUS_FALLBACK)
        self.assertEqual(decision.reason, REASON_BACKEND_UNSUPPORTED)

    def test_unknown_target_falls_back(self):
        decision = _decide(target="missing")
        self.assertEqual(decision.status, STATUS_FALLBACK)
        self.assertEqual(decision.reason, REASON_UNKNOWN_TARGET)

    def test_target_equal_to_active_falls_back(self):
        decision = _decide(target="one", active="one")
        self.assertEqual(decision.status, STATUS_FALLBACK)
        self.assertEqual(decision.reason, REASON_ALREADY_ACTIVE)

    def test_forged_negotiation_without_grants_is_rejected(self):
        forged = Negotiation("x11", "SUPPORTED", frozenset())
        with self.assertRaises(WorkspaceContractError):
            _decide(negotiation=forged)

    def test_unknown_backend_cannot_advertise_grants(self):
        forged = Negotiation("not-a-wm", "SUPPORTED",
                             frozenset({WindowStateFeature.MAXIMIZE}))
        with self.assertRaises(WorkspaceContractError):
            _decide(negotiation=forged)

    def test_malformed_workspace_records_fail_closed(self):
        from dataclasses import replace
        broken = replace(_inventory(), workspaces=[])
        with self.assertRaises(WorkspaceContractError):
            _decide(workspace=broken)

    def test_hostile_capability_container_fails_closed(self):
        with self.assertRaises(WorkspaceContractError):
            _decide(capabilities=["switch"])

    def test_unknown_capability_fails_closed(self):
        with self.assertRaises(WorkspaceContractError):
            _decide(capabilities=frozenset({"switch-and-spawn-wm"}))

    def test_hostile_identifiers_fail_closed(self):
        for bad in (None, 7, b"two", "x" * 129):
            with self.subTest(bad=bad):
                with self.assertRaises(WorkspaceContractError):
                    _decide(target=bad)

    def test_native_backends_are_x11_only(self):
        self.assertEqual(NATIVE_SWITCH_BACKENDS, frozenset({"x11"}))
        self.assertEqual(KNOWN_BACKENDS["wayland"].name, "wayland")
        self.assertEqual(CAPABILITIES,
                         frozenset({CAPABILITY_ENUMERATE, CAPABILITY_SWITCH}))

    def test_decision_is_immutable_and_has_no_callback(self):
        decision = _decide()
        with self.assertRaises(FrozenInstanceError):
            decision.status = STATUS_FALLBACK
        view = decision.to_dict()
        self.assertIsInstance(view, MappingProxyType)
        with self.assertRaises(TypeError):
            view["status"] = STATUS_FALLBACK
        self.assertFalse(any(callable(value) for value in decision.__dict__.values()))

    def test_decision_is_deterministic_without_observation(self):
        first = _decide().to_dict()
        second = _decide().to_dict()
        self.assertEqual(dict(first), dict(second))
        self.assertEqual(first["acceptance"], ACCEPTANCE_NOT_ESTABLISHED)
        self.assertEqual(first["observation"], OBSERVATION_NOT_PERFORMED)
        self.assertEqual(first["wm_requests"], 0)
        self.assertFalse(first["polling"])


if __name__ == "__main__":
    unittest.main()
