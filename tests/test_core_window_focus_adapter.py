"""Offline regression tests for the lazy, read-only focus adapter.

No Qt, compositor, D-Bus, network or real window is involved. All decisions
come from the already-validated in-memory policy module.
"""
from dataclasses import FrozenInstanceError, replace
import ast
from pathlib import Path
import subprocess
import sys
import unittest

from canopy_features.windows.focus_intents import PermissionPolicy

from canopy_core import window_focus_adapter as adapter_module
from canopy_core.window_focus_adapter import (
    ADAPTER_VERSION, DENIED, GRANTED, REJECTED, REPLAYED, STALE_TARGET,
    UNKNOWN_TARGET, AdapterInputError, AdapterTrustError, FocusDecisionView,
    FocusRequest, WindowFocusAdapter, WindowHandle, issue_host_authority,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "canopy_core" / "window_focus_adapter.py"


def new_adapter(policy=None, **kwargs):
    """Build a trusted adapter whose backend tracks every authorization."""
    calls = []

    def authorize(origin, target):
        calls.append((origin, target))
        return True if policy is None else policy.authorize(origin, target)

    return WindowFocusAdapter(issue_host_authority(), authorize, **kwargs), calls


class WindowFocusAdapterTests(unittest.TestCase):
    def test_construction_is_capability_gated(self):
        for bad in (None, "trusted", object(), WindowHandle(1, 1, None)):
            with self.subTest(authority=bad):
                with self.assertRaises(AdapterTrustError):
                    WindowFocusAdapter(bad, lambda o, t: True)
        with self.assertRaises(AdapterTrustError):
            WindowFocusAdapter(issue_host_authority(), "not callable")  # type: ignore[arg-type]
        with self.assertRaises(AdapterInputError):
            new_adapter(max_live_windows=0)
        good, _ = new_adapter(max_live_windows=1)
        self.assertEqual(good.protocol_version, ADAPTER_VERSION)
        self.assertEqual(good.live_window_count, 0)

    def test_lazy_import_only_on_first_use(self):
        script = """
import sys
from canopy_core import window_focus_adapter as a
key = 'canopy_features.windows.focus_intents'
assert key not in sys.modules, 'module import at adapter import time'
host = a.WindowFocusAdapter(a.issue_host_authority(), lambda o, t: True)
assert host.module_loaded is False
assert key not in sys.modules, 'module import at adapter construction time'
host.observe_window('app.a', 1)
assert host.module_loaded is True
assert key in sys.modules, 'module not imported on first use'
print('LAZY_OK')
"""
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=str(ROOT),
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LAZY_OK", result.stdout)

    def test_no_top_level_policy_import(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("focus_intents", node.module or "")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("focus_intents", alias.name)
        self.assertTrue(any(
            isinstance(node, ast.Import) and
            any(alias.name == "importlib" for alias in node.names)
            for node in tree.body
        ))

    def test_same_app_focus_allowed_by_validated_policy(self):
        policy = PermissionPolicy()
        host, calls = new_adapter(policy)
        handle = host.observe_window("com.canopy.files", 101)
        request = host.issue_request("com.canopy.files", handle)
        decision = host.decide(request)
        self.assertEqual(decision.status, GRANTED)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.target_app, "com.canopy.files")
        self.assertEqual(decision.target_window_id, 101)
        self.assertEqual(decision.origin_app, "com.canopy.files")
        self.assertEqual(calls, [("com.canopy.files", "com.canopy.files")])
        self.assertEqual(host.decision_count, 1)

    def test_cross_app_denied_without_grant_then_allowed(self):
        policy = PermissionPolicy()
        host, calls = new_adapter(policy)
        handle = host.observe_window("com.canopy.editor", 202)
        denied = host.decide(host.issue_request("com.canopy.files", handle))
        self.assertEqual(denied.status, DENIED)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.target_app, "com.canopy.editor")
        policy.grant("com.canopy.files", "com.canopy.editor")
        allowed = host.decide(host.issue_request("com.canopy.files", handle))
        self.assertEqual(allowed.status, GRANTED)
        self.assertEqual(calls, [
            ("com.canopy.files", "com.canopy.editor"),
            ("com.canopy.files", "com.canopy.editor"),
        ])

    def test_authorize_must_return_exact_true(self):
        for answer in (False, None, 1, "yes", [], True):
            with self.subTest(answer=answer):
                host, calls = new_adapter()
                setattr(host, "_authorize", lambda o, t, a=answer: a)
                handle = host.observe_window("app.b", 300)
                decision = host.decide(host.issue_request("app.a", handle))
                self.assertEqual(decision.status,
                                 GRANTED if answer is True else DENIED)
                self.assertEqual(len(calls), 0)  # calls go to the replaced fn

    def test_backend_exception_denies_without_secret_leak(self):
        def explode(origin, target):
            raise RuntimeError("secret token from backend")

        host = WindowFocusAdapter(issue_host_authority(), explode)
        handle = host.observe_window("app.b", 301)
        decision = host.decide(host.issue_request("app.a", handle))
        self.assertEqual(decision.status, DENIED)
        self.assertFalse(decision.allowed)
        self.assertIn("RuntimeError", decision.reason)
        self.assertNotIn("secret", decision.reason)

    def test_malformed_inputs_fail_closed(self):
        host, _ = new_adapter()
        for app, window in (("bad app!", 1), ("", 2), ("x" * 129, 3),
                            (7, 4), ("app.a", True), ("app.a", 0)):
            with self.subTest(app=app, window=window):
                with self.assertRaises(AdapterInputError):
                    host.observe_window(app, window)
        handle = host.observe_window("app.b", 400)
        with self.assertRaises(AdapterInputError):
            host.observe_window("app.b", 400)
        for bad_app in ("bad app!", None, 12):
            with self.subTest(origin=bad_app):
                with self.assertRaises(AdapterInputError):
                    host.issue_request(bad_app, handle)
        for bad_handle in (None, "handle", (400, 1),
                           WindowHandle(400, 1, None)):
            with self.subTest(handle=bad_handle):
                with self.assertRaises(AdapterInputError):
                    host.issue_request("app.a", bad_handle)
                with self.assertRaises(AdapterInputError):
                    host.forget_window(bad_handle)

    def test_unknown_and_stale_targets_fail_closed_before_backend(self):
        policy = PermissionPolicy([("app.a", "app.b")])
        host, calls = new_adapter(policy)
        old = host.observe_window("app.b", 500)
        self.assertTrue(host.forget_window(old))
        gone = host.decide(host.issue_request("app.a", old))
        self.assertEqual(gone.status, UNKNOWN_TARGET)
        self.assertIsNone(gone.target_app)
        self.assertEqual(calls, [])

        fresh = host.observe_window("app.b", 500)
        self.assertNotEqual(fresh.serial, old.serial)
        allowed = host.decide(host.issue_request("app.a", fresh))
        self.assertEqual(allowed.status, GRANTED)
        self.assertEqual(len(calls), 1)

        stale = host.decide(host.issue_request("app.a", old))
        self.assertEqual(stale.status, STALE_TARGET)
        self.assertEqual(stale.target_app, "app.b")
        self.assertEqual(len(calls), 1)

    def test_duplicate_request_is_replayed_without_backend_call(self):
        host, calls = new_adapter()
        handle = host.observe_window("app.b", 600)
        request = host.issue_request("app.a", handle)
        first = host.decide(request)
        second = host.decide(request)
        self.assertEqual(first.status, GRANTED)
        self.assertEqual(second.status, REPLAYED)
        self.assertFalse(second.allowed)
        self.assertIsNone(second.target_app)
        self.assertEqual(len(calls), 1)
        self.assertEqual(host.replay_count, 1)
        self.assertEqual(host.decision_count, 2)

    def test_replay_bookkeeping_is_bounded_and_deterministic(self):
        host, calls = new_adapter()
        handle = host.observe_window("app.b", 700)
        requests = [host.issue_request("app.a", handle) for _ in range(70)]
        statuses = [host.decide(request).status for request in requests]
        self.assertEqual(set(statuses), {GRANTED})
        self.assertEqual(len(host._consumed), 64)
        self.assertLessEqual(len(host._consumed_ids), 64)
        self.assertEqual(host.decide(requests[0]).status, REPLAYED)
        self.assertEqual(host.decide(requests[-1]).status, REPLAYED)
        self.assertEqual(host.replay_count, 2)
        self.assertEqual(len(calls), 70)

    def test_foreign_and_forged_requests_are_rejected(self):
        first, calls = new_adapter()
        second, _ = new_adapter()
        handle = second.observe_window("app.b", 800)
        foreign = second.issue_request("app.a", handle)
        decision = first.decide(foreign)
        self.assertEqual(decision.status, REJECTED)
        self.assertEqual(decision.reason, "untrusted request")
        self.assertEqual(calls, [])

        forged = replace(foreign, request_id=999)
        self.assertEqual(second.decide(forged).status, REJECTED)
        self.assertEqual(second.decide("not a request").status, REJECTED)

    def test_decision_view_is_frozen_and_read_only(self):
        host, _ = new_adapter()
        handle = host.observe_window("app.b", 900)
        decision = host.decide(host.issue_request("app.b", handle))
        self.assertIsInstance(decision, FocusDecisionView)
        self.assertIs(type(decision.allowed), bool)
        self.assertIs(type(decision.status), str)
        with self.assertRaises(FrozenInstanceError):
            setattr(decision, "status", DENIED)
        with self.assertRaises(FrozenInstanceError):
            setattr(handle, "window_id", 901)

    def test_no_execution_or_window_change_surface(self):
        code = SOURCE.read_text(encoding="utf-8")
        for forbidden in ("activate=", "activate(", "import subprocess",
                          "import socket", "Popen(", "os.system(",
                          "QTimer", "Thread(", "import ctypes",
                          "time.sleep", "eval(", "exec("):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
