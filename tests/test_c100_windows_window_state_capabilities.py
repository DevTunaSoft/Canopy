"""Offline tests for window-state capability negotiation and transitions.

Pure in-process logic: no Qt, compositor, Mint session or Windows API is used
or claimed. Ground truth here is the policy in window_state_capabilities.py.
"""

import unittest
from dataclasses import FrozenInstanceError

from canopy_features.windows.window_state_capabilities import (
    ACTION_FEATURE,
    KNOWN_BACKENDS,
    VALID_TRANSITIONS,
    BackendProfile,
    Negotiation,
    TransitionResult,
    WindowState,
    WindowStateAction,
    WindowStateController,
    WindowStateFeature,
    negotiate,
    profile_for,
)

ALL = frozenset(WindowStateFeature)
MIN = WindowStateAction.MINIMIZE
MAX = WindowStateAction.MAXIMIZE
RES = WindowStateAction.RESTORE


class BackendProfileTests(unittest.TestCase):
    def test_known_profiles_are_registered(self):
        self.assertEqual(set(KNOWN_BACKENDS), {"x11", "wayland", "headless"})
        self.assertEqual(KNOWN_BACKENDS["x11"].supported, ALL)
        self.assertEqual(
            KNOWN_BACKENDS["wayland"].supported,
            frozenset({WindowStateFeature.MAXIMIZE, WindowStateFeature.RESTORE}),
        )
        self.assertEqual(KNOWN_BACKENDS["headless"].supported, frozenset())

    def test_wayland_profile_has_no_minimize(self):
        self.assertFalse(KNOWN_BACKENDS["wayland"].supports(WindowStateFeature.MINIMIZE))

    def test_unknown_backend_is_empty_and_fail_closed(self):
        profile = profile_for("some-unsupported-compositor")
        self.assertEqual(profile.name, "some-unsupported-compositor")
        self.assertEqual(profile.supported, frozenset())

    def test_unknown_backend_lookup_does_not_grow_registry(self):
        before = set(KNOWN_BACKENDS)
        for index in range(200):
            profile_for("unknown-compositor-%d" % index)
        self.assertEqual(set(KNOWN_BACKENDS), before)

    def test_profile_rejects_non_frozenset(self):
        with self.assertRaises(TypeError):
            BackendProfile("bad", {WindowStateFeature.MINIMIZE})

    def test_profile_rejects_unknown_advertised_feature(self):
        with self.assertRaises(TypeError):
            BackendProfile("bad", frozenset({"minimize"}))

    def test_profile_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            BackendProfile("", frozenset())

    def test_profile_for_rejects_non_string(self):
        with self.assertRaises(TypeError):
            profile_for(None)


class NegotiationTests(unittest.TestCase):
    def test_full_backend_negotiates_supported(self):
        result = negotiate("x11", ALL)
        self.assertEqual(result.status, "SUPPORTED")
        self.assertEqual(result.granted, ALL)
        self.assertEqual(result.backend, "x11")
        self.assertTrue(result.supported)

    def test_wayland_negotiates_partial_without_minimize(self):
        result = negotiate("wayland", ALL)
        self.assertEqual(result.status, "PARTIAL")
        self.assertEqual(
            result.granted,
            frozenset({WindowStateFeature.MAXIMIZE, WindowStateFeature.RESTORE}),
        )
        self.assertTrue(result.allows(MAX))
        self.assertFalse(result.allows(MIN))

    def test_headless_negotiates_unsupported(self):
        result = negotiate("headless", ALL)
        self.assertEqual(result.status, "UNSUPPORTED")
        self.assertEqual(result.granted, frozenset())
        self.assertFalse(result.supported)
        self.assertFalse(result.allows(MIN))
        self.assertFalse(result.allows(MAX))
        self.assertFalse(result.allows(RES))

    def test_unknown_compositor_negotiates_unsupported(self):
        result = negotiate("unsupported-mint-shell", ALL)
        self.assertEqual(result.status, "UNSUPPORTED")
        self.assertEqual(result.backend, "unsupported-mint-shell")
        self.assertEqual(result.granted, frozenset())

    def test_requested_set_is_intersected_not_widened(self):
        result = negotiate("wayland", {WindowStateFeature.MINIMIZE})
        self.assertEqual(result.status, "UNSUPPORTED")
        self.assertEqual(result.granted, frozenset())

    def test_explicit_profile_is_accepted(self):
        profile = BackendProfile(
            "custom", frozenset({WindowStateFeature.MINIMIZE})
        )
        result = negotiate(profile, {WindowStateFeature.MINIMIZE})
        self.assertEqual(result.status, "SUPPORTED")
        self.assertEqual(result.backend, "custom")

    def test_empty_request_is_rejected(self):
        with self.assertRaises(ValueError):
            negotiate("x11", [])

    def test_unknown_requested_feature_is_rejected(self):
        with self.assertRaises(TypeError):
            negotiate("x11", {WindowStateFeature.MINIMIZE, "maximize"})

    def test_string_request_is_rejected(self):
        with self.assertRaises(TypeError):
            negotiate("x11", "minimize")

    def test_non_iterable_request_is_rejected(self):
        with self.assertRaises(TypeError):
            negotiate("x11", 7)

    def test_invalid_backend_type_is_rejected(self):
        with self.assertRaises(TypeError):
            negotiate(object(), ALL)

    def test_allows_unhashable_action_is_false(self):
        result = negotiate("x11", ALL)
        self.assertFalse(result.allows(["minimize"]))

    def test_negotiation_is_immutable(self):
        result = negotiate("x11", ALL)
        with self.assertRaises(FrozenInstanceError):
            result.status = "SUPPORTED"


class ControllerHappyPathTests(unittest.TestCase):
    def controller(self, backend="x11"):
        return WindowStateController(negotiate(backend, ALL))

    def test_starts_normal(self):
        controller = self.controller()
        self.assertIs(controller.state, WindowState.NORMAL)

    def test_minimize_then_restore(self):
        controller = self.controller()
        self.assertIs(controller.apply(MIN).state, WindowState.MINIMIZED)
        self.assertIs(controller.state, WindowState.MINIMIZED)
        self.assertIs(controller.apply(RES).state, WindowState.NORMAL)
        self.assertIs(controller.state, WindowState.NORMAL)

    def test_maximize_then_restore(self):
        controller = self.controller()
        result = controller.apply(MAX)
        self.assertTrue(result.ok)
        self.assertEqual(result.status, "OK")
        self.assertIs(result.state, WindowState.MAXIMIZED)
        self.assertIs(controller.apply(RES).state, WindowState.NORMAL)

    def test_success_result_has_no_reason(self):
        controller = self.controller()
        self.assertEqual(controller.apply(MIN).reason, "")

    def test_allows_reflects_negotiated_features(self):
        controller = self.controller("wayland")
        self.assertTrue(controller.allows(MAX))
        self.assertFalse(controller.allows(MIN))

    def test_repeated_cycles_keep_bounded_state(self):
        controller = self.controller()
        for _ in range(1000):
            controller.apply(MIN)
            controller.apply(RES)
            controller.apply(MAX)
            controller.apply(RES)
        self.assertIs(controller.state, WindowState.NORMAL)
        self.assertEqual(set(controller.__slots__), {"_negotiation", "_state"})


class ControllerRejectionTests(unittest.TestCase):
    def controller(self, backend):
        return WindowStateController(negotiate(backend, ALL))

    def assert_rejected(self, result, reason, state):
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, reason)
        self.assertIs(result.state, state)

    def test_minimize_rejected_without_capability(self):
        controller = self.controller("wayland")
        self.assert_rejected(controller.apply(MIN), "FEATURE_NOT_GRANTED",
                             WindowState.NORMAL)

    def test_all_actions_rejected_on_unsupported_compositor(self):
        controller = self.controller("unsupported-compositor")
        for action in (MIN, MAX, RES):
            self.assert_rejected(controller.apply(action), "FEATURE_NOT_GRANTED",
                                 WindowState.NORMAL)
        self.assertIs(controller.state, WindowState.NORMAL)

    def test_invalid_transition_minimize_twice(self):
        controller = self.controller("x11")
        controller.apply(MIN)
        self.assert_rejected(controller.apply(MIN), "INVALID_TRANSITION",
                             WindowState.MINIMIZED)

    def test_invalid_transition_maximize_twice(self):
        controller = self.controller("x11")
        controller.apply(MAX)
        self.assert_rejected(controller.apply(MAX), "INVALID_TRANSITION",
                             WindowState.MAXIMIZED)

    def test_invalid_transition_restore_from_normal(self):
        controller = self.controller("x11")
        self.assert_rejected(controller.apply(RES), "INVALID_TRANSITION",
                             WindowState.NORMAL)

    def test_invalid_transition_maximize_from_minimized(self):
        controller = self.controller("x11")
        controller.apply(MIN)
        self.assert_rejected(controller.apply(MAX), "INVALID_TRANSITION",
                             WindowState.MINIMIZED)

    def test_invalid_transition_minimize_from_maximized(self):
        controller = self.controller("x11")
        controller.apply(MAX)
        self.assert_rejected(controller.apply(MIN), "INVALID_TRANSITION",
                             WindowState.MAXIMIZED)

    def test_invalid_transition_does_not_mutate_state(self):
        controller = self.controller("x11")
        controller.apply(MIN)
        controller.apply(MIN)
        self.assertIs(controller.state, WindowState.MINIMIZED)
        self.assertIs(controller.apply(RES).state, WindowState.NORMAL)

    def test_unknown_action_rejected(self):
        controller = self.controller("x11")
        self.assert_rejected(controller.apply("minimize"), "UNKNOWN_ACTION",
                             WindowState.NORMAL)

    def test_unhashable_action_rejected(self):
        controller = self.controller("x11")
        self.assert_rejected(controller.apply(["minimize"]), "UNKNOWN_ACTION",
                             WindowState.NORMAL)

    def test_controller_requires_negotiation(self):
        with self.assertRaises(TypeError):
            WindowStateController("x11")

    def test_result_is_immutable(self):
        result = TransitionResult("REJECTED", WindowState.NORMAL, "reason")
        with self.assertRaises(FrozenInstanceError):
            result.status = "OK"


class ContractConsistencyTests(unittest.TestCase):
    def test_every_action_maps_to_a_feature(self):
        self.assertEqual(set(ACTION_FEATURE), set(WindowStateAction))
        self.assertEqual(set(ACTION_FEATURE.values()), set(WindowStateFeature))

    def test_transition_table_targets_are_known_states(self):
        for target in VALID_TRANSITIONS.values():
            self.assertIsInstance(target, WindowState)
        self.assertEqual(len(VALID_TRANSITIONS), 4)

    def test_no_transition_from_minimized_to_maximized(self):
        pair = (WindowState.MINIMIZED, WindowStateAction.MAXIMIZE)
        self.assertNotIn(pair, VALID_TRANSITIONS)


if __name__ == "__main__":
    unittest.main()
