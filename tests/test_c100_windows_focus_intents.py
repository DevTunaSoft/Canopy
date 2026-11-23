"""Offline unit tests for window focus intents; no real OS/Qt/Mint claims."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.windows.focus_intents import (
    ACTIVATION_FAILED, DENIED, GRANTED, MAX_GRANTS, MAX_HISTORY,
    MAX_LIVE_WINDOWS, STALE_TARGET, UNKNOWN_TARGET, FocusBroker,
    FocusIntent, FocusIntentError, PermissionPolicy, WindowRef,
)


def broker_with(policy=None, activate=None, **kwargs):
    """Build a broker with a trackable authorize backend for tests."""
    calls = []

    def authorize(origin, target):
        calls.append((origin, target))
        return True if policy is None else policy.authorize(origin, target)

    return FocusBroker(authorize, activate, **kwargs), calls


class FocusIntentTests(unittest.TestCase):
    def test_same_app_focus_is_authorized_and_activated(self):
        activated = []
        broker, calls = broker_with(activate=activated.append)
        ref = broker.register_window("com.canopy.files", 101)
        decision = broker.request_focus(
            FocusIntent("com.canopy.files", ref))
        self.assertEqual(decision.status, GRANTED)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.target_app, "com.canopy.files")
        self.assertEqual(calls, [("com.canopy.files", "com.canopy.files")])
        self.assertEqual(activated, [101])

    def test_cross_app_focus_denied_without_explicit_grant(self):
        activated = []
        broker, calls = broker_with(PermissionPolicy(), activated.append)
        ref = broker.register_window("com.canopy.editor", 202)
        decision = broker.request_focus(
            FocusIntent("com.canopy.files", ref))
        self.assertEqual(decision.status, DENIED)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.target_app, "com.canopy.editor")
        self.assertEqual(calls, [("com.canopy.files", "com.canopy.editor")])
        self.assertEqual(activated, [])

    def test_cross_app_focus_allowed_after_explicit_grant(self):
        activated = []
        policy = PermissionPolicy()
        policy.grant("com.canopy.files", "com.canopy.editor")
        broker, _ = broker_with(policy, activated.append)
        ref = broker.register_window("com.canopy.editor", 203)
        decision = broker.request_focus(
            FocusIntent("com.canopy.files", ref))
        self.assertEqual(decision.status, GRANTED)
        self.assertEqual(activated, [203])
        policy.revoke("com.canopy.files", "com.canopy.editor")
        self.assertEqual(broker.request_focus(
            FocusIntent("com.canopy.files", ref)).status, DENIED)

    def test_grant_is_directional(self):
        policy = PermissionPolicy([("app.a", "app.b")])
        self.assertTrue(policy.authorize("app.a", "app.b"))
        self.assertFalse(policy.authorize("app.b", "app.a"))

    def test_stale_target_rejected_and_fresh_serial_accepted(self):
        policy = PermissionPolicy([("app.a", "app.b")])
        broker, calls = broker_with(policy)
        old_ref = broker.register_window("app.b", 300)
        self.assertTrue(broker.unregister_window(300))
        new_ref = broker.register_window("app.b", 300)
        self.assertNotEqual(old_ref.serial, new_ref.serial)

        stale = broker.request_focus(FocusIntent("app.a", old_ref))
        self.assertEqual(stale.status, STALE_TARGET)
        self.assertEqual(stale.target_app, "app.b")
        self.assertEqual(calls, [])  # fail closed before backend
        fresh = broker.request_focus(FocusIntent("app.a", new_ref))
        self.assertEqual(fresh.status, GRANTED)
        self.assertEqual(len(calls), 1)

    def test_unknown_target_fails_closed_before_backend(self):
        activated = []
        broker, calls = broker_with(activate=activated.append)
        ref = broker.register_window("app.b", 400)
        broker.unregister_window(400)
        decision = broker.request_focus(FocusIntent("app.a", ref))
        self.assertEqual(decision.status, UNKNOWN_TARGET)
        self.assertIsNone(decision.target_app)
        self.assertEqual(calls, [])
        self.assertEqual(activated, [])

    def test_backend_must_return_exact_true(self):
        for answer in (False, None, 1, "yes", [], True):
            with self.subTest(answer=answer):
                broker, _ = broker_with()
                broker._authorize = lambda o, t, a=answer: a
                ref = broker.register_window("app.b", 500)
                status = broker.request_focus(
                    FocusIntent("app.a", ref)).status
                self.assertEqual(status, GRANTED if answer is True else DENIED)

    def test_backend_exception_denies_without_leaking_message(self):
        def explode(origin, target):
            raise RuntimeError("secret token in backend")

        broker = FocusBroker(explode)
        ref = broker.register_window("app.b", 501)
        decision = broker.request_focus(FocusIntent("app.a", ref))
        self.assertEqual(decision.status, DENIED)
        self.assertNotIn("secret", decision.reason)
        self.assertIn("RuntimeError", decision.reason)

    def test_activation_failure_is_reported_not_raised(self):
        def bad_activate(window_id):
            raise OSError("device busy")

        broker, _ = broker_with(activate=bad_activate)
        ref = broker.register_window("app.b", 502)
        decision = broker.request_focus(FocusIntent("app.b", ref))
        self.assertEqual(decision.status, ACTIVATION_FAILED)
        self.assertIn("OSError", decision.reason)
        self.assertNotIn("device busy", decision.reason)

    def test_activation_returning_false_fails(self):
        broker, _ = broker_with(activate=lambda wid: False)
        ref = broker.register_window("app.b", 503)
        self.assertEqual(broker.request_focus(
            FocusIntent("app.b", ref)).status, ACTIVATION_FAILED)

    def test_history_is_bounded_immutable_snapshot(self):
        broker, _ = broker_with()
        ref = broker.register_window("app.b", 600)
        for _ in range(MAX_HISTORY + 10):
            broker.request_focus(FocusIntent("app.b", ref))
        self.assertEqual(len(broker.history), MAX_HISTORY)
        with self.assertRaises(TypeError):
            broker.history[0] = None

    def test_live_window_registry_is_bounded(self):
        broker, _ = broker_with(max_live_windows=2)
        broker.register_window("app.b", 700)
        broker.register_window("app.b", 701)
        with self.assertRaisesRegex(FocusIntentError, "limit"):
            broker.register_window("app.b", 702)
        self.assertEqual(broker.live_window_count, 2)

    def test_grant_set_is_bounded(self):
        policy = PermissionPolicy()
        for i in range(MAX_GRANTS):
            policy.grant("src.%d" % i, "dst.%d" % i)
        self.assertEqual(policy.grant_count, MAX_GRANTS)
        with self.assertRaisesRegex(FocusIntentError, "limit"):
            policy.grant("one.too.many", "dst.app")

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(FocusIntentError):
            FocusBroker(None)
        with self.assertRaises(FocusIntentError):
            FocusBroker(lambda o, t: True, activate="not callable")
        for bad in ("bad app!", "", "has space", "x" * 129, 7, None, True):
            with self.subTest(app=bad):
                with self.assertRaises(FocusIntentError):
                    FocusIntent(bad, WindowRef(1, 1))
        for bad in (0, -1, True, 2_147_483_648, "1", None):
            with self.subTest(window=bad):
                with self.assertRaises(FocusIntentError):
                    WindowRef(bad, 1)
        with self.assertRaises(FocusIntentError):
            FocusIntent("app.a", (1, 1))
        broker, _ = broker_with()
        with self.assertRaises(FocusIntentError):
            broker.request_focus("not an intent")
        with self.assertRaises(FocusIntentError):
            broker.register_window("app.b", 800)
            broker.register_window("app.b", 800)

    def test_decision_and_ref_are_frozen(self):
        ref = WindowRef(900, 1)
        intent = FocusIntent("app.a", ref)
        with self.assertRaises(FrozenInstanceError):
            ref.window_id = 901
        with self.assertRaises(FrozenInstanceError):
            intent.origin_app = "other"

    def test_no_poll_thread_or_network_imports(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/windows/focus_intents.py").read_text(
                    encoding="utf-8")
        for forbidden in ("QTimer", "asyncio", "import subprocess",
                          "import socket", "Thread(", "importlib",
                          "time.sleep", "import ctypes", "import requests"):
            self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
