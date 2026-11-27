"""Offline tests for window-reference gating in the window state decision layer.

No Qt, compositor, X11/Wayland, Windows API, socket, subprocess or session
access is used or claimed. A trusted caller registers a window instance and
passes the resulting reference to a state decision; stale, unknown and
unauthorized references must never change window state.
"""

import unittest

from canopy_features.windows import window_state_capabilities as wsc

ALL_FEATURES = frozenset(wsc.WindowStateFeature)
MIN = wsc.WindowStateAction.MINIMIZE
MAX = wsc.WindowStateAction.MAXIMIZE
RES = wsc.WindowStateAction.RESTORE


def make_controller(registry=None, backend="x11"):
    negotiation = wsc.negotiate(backend, ALL_FEATURES)
    if registry is None:
        return wsc.WindowStateController(negotiation)
    return wsc.WindowStateController(negotiation, registry)


class ReferenceValueTests(unittest.TestCase):
    def test_registry_returns_a_bounded_reference(self):
        registry = wsc.WindowStateRegistry()
        ref = registry.register(42, "files.app")
        self.assertEqual(ref.window_id, 42)
        self.assertEqual(ref.owner, "files.app")
        self.assertEqual(ref.serial, 1)
        self.assertEqual(registry.status(ref), "LIVE")

    def test_reference_is_frozen(self):
        from dataclasses import FrozenInstanceError
        ref = wsc.WindowStateRegistry().register(1, "files.app")
        with self.assertRaises(FrozenInstanceError):
            ref.serial = 99

    def test_hostile_reference_fields_fail_closed(self):
        bad = (
            (True, 1, "files.app"),
            (0, 1, "files.app"),
            (-1, 1, "files.app"),
            ("42", 1, "files.app"),
            (1, True, "files.app"),
            (1, 0, "files.app"),
            (1, "1", "files.app"),
            (1, 1, ""),
            (1, 1, "bad owner"),
            (1, 1, ["files.app"]),
            (1, 1, None),
        )
        for window_id, serial, owner in bad:
            with self.subTest(window_id=window_id, serial=serial, owner=owner):
                with self.assertRaises(wsc.WindowReferenceError):
                    wsc.WindowStateRef(window_id, serial, owner)

    def test_reference_serial_is_bounded(self):
        with self.assertRaises(wsc.WindowReferenceError):
            wsc.WindowStateRef(1, wsc.MAX_SERIAL + 1, "files.app")


class RegistryBoundTests(unittest.TestCase):
    def test_duplicate_id_is_rejected_without_mutating_live_set(self):
        registry = wsc.WindowStateRegistry()
        registry.register(7, "files.app")
        with self.assertRaises(wsc.WindowReferenceError):
            registry.register(7, "other.app")
        self.assertEqual(registry.live_count, 1)
        self.assertEqual(registry.status(wsc.WindowStateRef(7, 1, "files.app")),
                         "LIVE")

    def test_live_window_bound_is_enforced(self):
        registry = wsc.WindowStateRegistry(max_windows=1)
        registry.register(1, "files.app")
        with self.assertRaises(wsc.WindowReferenceError):
            registry.register(2, "files.app")
        self.assertEqual(registry.live_count, 1)

    def test_invalid_bound_is_rejected(self):
        for bound in (0, -1, True, 65, "1", None):
            with self.subTest(bound=bound):
                with self.assertRaises(wsc.WindowReferenceError):
                    wsc.WindowStateRegistry(max_windows=bound)

    def test_unknown_id_status(self):
        registry = wsc.WindowStateRegistry()
        self.assertEqual(registry.status(wsc.WindowStateRef(9, 1, "files.app")),
                         "UNKNOWN")

    def test_reused_id_yields_fresh_serial_and_marks_old_ref_stale(self):
        registry = wsc.WindowStateRegistry()
        old = registry.register(7, "files.app")
        self.assertTrue(registry.unregister(7, "files.app"))
        fresh = registry.register(7, "files.app")
        self.assertNotEqual(fresh.serial, old.serial)
        self.assertEqual(registry.status(old), "STALE")
        self.assertEqual(registry.status(fresh), "LIVE")

    def test_wrong_owner_cannot_unregister(self):
        registry = wsc.WindowStateRegistry()
        ref = registry.register(7, "files.app")
        self.assertFalse(registry.unregister(7, "other.app"))
        self.assertEqual(registry.status(ref), "LIVE")

    def test_matching_id_and_serial_with_wrong_owner_is_unauthorized(self):
        registry = wsc.WindowStateRegistry()
        registry.register(7, "files.app")
        forged = wsc.WindowStateRef(7, 1, "other.app")
        self.assertEqual(registry.status(forged), "UNAUTHORIZED")

    def test_hostile_unregistration_inputs_do_not_mutate_live_set(self):
        registry = wsc.WindowStateRegistry()
        ref = registry.register(7, "files.app")
        for window_id, owner in ((True, "files.app"), (7, None),
                                 (7, ["files.app"]), ("7", "files.app")):
            with self.subTest(window_id=window_id, owner=owner):
                with self.assertRaises(wsc.WindowReferenceError):
                    registry.unregister(window_id, owner)
        self.assertEqual(registry.status(ref), "LIVE")

    def test_registry_is_bounded_and_has_no_dynamic_attributes(self):
        registry = wsc.WindowStateRegistry()
        self.assertEqual(set(registry.__slots__),
                         {"_live", "_next_serial", "_max_windows"})
        self.assertFalse(hasattr(registry, "__dict__"))
        for index in range(wsc.MAX_LIVE_WINDOWS):
            registry.register(index + 1, "files.app")
            registry.unregister(index + 1, "files.app")
            registry.register(index + 1, "files.app")
        self.assertEqual(registry.live_count, wsc.MAX_LIVE_WINDOWS)
        self.assertEqual(len(registry._live), wsc.MAX_LIVE_WINDOWS)

    def test_equal_operations_produce_equal_references_and_statuses(self):
        def build():
            registry = wsc.WindowStateRegistry()
            ref = registry.register(11, "files.app")
            return registry, ref
        first_registry, first = build()
        second_registry, second = build()
        self.assertEqual(first, second)
        self.assertEqual(first_registry.status(first),
                         second_registry.status(second))


class ReferenceGatedDecisionTests(unittest.TestCase):
    def test_legacy_controller_without_registry_is_unchanged(self):
        controller = make_controller()
        self.assertTrue(controller.apply(MIN).ok)
        self.assertIs(controller.state, wsc.WindowState.MINIMIZED)
        self.assertTrue(controller.apply(RES).ok)

    def test_bound_controller_requires_a_reference(self):
        controller = make_controller(wsc.WindowStateRegistry())
        result = controller.apply(MIN)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "INVALID_REFERENCE")
        self.assertIs(result.state, wsc.WindowState.NORMAL)
        self.assertFalse(controller.allows(MIN))

    def test_fresh_reference_permits_a_valid_transition(self):
        registry = wsc.WindowStateRegistry()
        ref = registry.register(7, "files.app")
        controller = make_controller(registry)
        self.assertTrue(controller.allows(MAX, ref))
        result = controller.apply(MAX, ref)
        self.assertTrue(result.ok)
        self.assertIs(controller.state, wsc.WindowState.MAXIMIZED)

    def test_stale_reference_is_rejected_without_state_change(self):
        registry = wsc.WindowStateRegistry()
        old = registry.register(7, "files.app")
        controller = make_controller(registry)
        self.assertTrue(controller.apply(MIN, old).ok)
        registry.unregister(7, "files.app")
        fresh = registry.register(7, "files.app")
        self.assertNotEqual(fresh.serial, old.serial)
        result = controller.apply(RES, old)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reason, "STALE_REFERENCE")
        self.assertIs(result.state, wsc.WindowState.MINIMIZED)
        self.assertIs(controller.state, wsc.WindowState.MINIMIZED)
        self.assertFalse(controller.allows(RES, old))
        self.assertTrue(controller.apply(RES, fresh).ok)

    def test_unauthorized_reference_is_rejected_without_state_change(self):
        registry = wsc.WindowStateRegistry()
        registry.register(7, "files.app")
        forged = wsc.WindowStateRef(7, 1, "other.app")
        controller = make_controller(registry)
        result = controller.apply(MAX, forged)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "UNAUTHORIZED_REFERENCE")
        self.assertIs(controller.state, wsc.WindowState.NORMAL)
        self.assertFalse(controller.allows(MAX, forged))

    def test_unknown_reference_is_rejected(self):
        registry = wsc.WindowStateRegistry()
        unknown = wsc.WindowStateRef(99, 1, "files.app")
        controller = make_controller(registry)
        result = controller.apply(MIN, unknown)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "UNKNOWN_REFERENCE")
        self.assertFalse(controller.allows(MIN, unknown))

    def test_malformed_reference_is_a_decision_not_an_exception(self):
        registry = wsc.WindowStateRegistry()
        registry.register(7, "files.app")
        controller = make_controller(registry)
        for hostile in ("7", 7, {"window_id": 7}, [], object(), True):
            with self.subTest(reference=repr(hostile)):
                result = controller.apply(MIN, hostile)
                self.assertFalse(result.ok)
                self.assertEqual(result.reason, "INVALID_REFERENCE")
                self.assertFalse(controller.allows(MIN, hostile))
        self.assertIs(controller.state, wsc.WindowState.NORMAL)

    def test_reference_without_registry_cannot_be_validated(self):
        registry = wsc.WindowStateRegistry()
        ref = registry.register(7, "files.app")
        controller = make_controller()
        result = controller.apply(MIN, ref)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "UNVALIDATED_REFERENCE")
        self.assertFalse(controller.allows(MIN, ref))

    def test_invalid_registry_type_is_rejected(self):
        with self.assertRaises(TypeError):
            wsc.WindowStateController(
                wsc.negotiate("x11", ALL_FEATURES), "registry")

    def test_stale_reference_cannot_bypass_a_capability_decision(self):
        registry = wsc.WindowStateRegistry()
        old = registry.register(7, "files.app")
        registry.unregister(7, "files.app")
        registry.register(7, "files.app")
        # Wayland cannot minimize at all, but a stale reference must be
        # rejected for reference reasons before any feature grant is consulted.
        controller = make_controller(registry, "wayland")
        result = controller.apply(MIN, old)
        self.assertEqual(result.reason, "STALE_REFERENCE")
        self.assertIs(controller.state, wsc.WindowState.NORMAL)
        self.assertFalse(controller.apply(MAX, old).ok)

    def test_rejected_references_do_not_grow_the_registry(self):
        registry = wsc.WindowStateRegistry()
        ref = registry.register(7, "files.app")
        controller = make_controller(registry)
        for _ in range(200):
            controller.apply(MIN, wsc.WindowStateRef(7, 2, "files.app"))
            controller.apply(MIN, wsc.WindowStateRef(7, 1, "other.app"))
            controller.apply(MIN, wsc.WindowStateRef(999, 1, "files.app"))
        self.assertEqual(registry.live_count, 1)
        self.assertEqual(registry.status(ref), "LIVE")
        self.assertIs(controller.state, wsc.WindowState.NORMAL)

    def test_decision_module_stays_offline(self):
        source = wsc.__doc__ or ""
        self.assertIn("does NOT talk to Qt", source)
        module_source = open(wsc.__file__, "r", encoding="utf-8").read()
        for banned in ("import os", "import socket", "import subprocess",
                       "import ctypes", "PyQt", "PySide"):
            self.assertNotIn(banned, module_source)


if __name__ == "__main__":
    unittest.main()
