"""Shell Host owns a decision-only focus advisory adapter."""
from __future__ import annotations

import unittest
from pathlib import Path

from canopy_core.registry import PackScan, ShellPackInfo
from canopy_core.shell_host import ShellHost
from canopy_core.window_focus_adapter import (
    GRANTED, AdapterInputError, AdapterTrustError, WindowFocusAdapter)


def scan():
    pack = ShellPackInfo(
        pack_id="com.example.classic", name="classic", description="test pack",
        directory=Path("/nonexecuted/classic"), entrypoint="ui/Main.qml",
        shell_api=1, ui_engine="qt-qml", capabilities=frozenset({"dock"}))
    return PackScan((pack,), (), 1)


class ShellHostFocusAdapterTests(unittest.TestCase):
    def host(self):
        return ShellHost(scan(), {}, frozenset({"dock"}))

    def test_factory_returns_decision_only_adapter(self):
        adapter = self.host().make_focus_adapter(lambda origin, target: True)
        self.assertIsInstance(adapter, WindowFocusAdapter)
        self.assertFalse(adapter.module_loaded)
        self.assertFalse(hasattr(adapter, "activate"))

    def test_noncallable_backend_is_rejected(self):
        with self.assertRaises(AdapterTrustError):
            self.host().make_focus_adapter("not callable")

    def test_adapter_can_grant_without_changing_host_state(self):
        host = self.host()
        adapter = host.make_focus_adapter(lambda origin, target: True)
        handle = adapter.observe_window("app.a", 7)
        request = adapter.issue_request("app.b", handle)
        decision = adapter.decide(request)
        self.assertEqual(decision.status, GRANTED)
        self.assertTrue(decision.allowed)
        self.assertEqual((host.active_id, host.needs_recovery), (None, False))
        self.assertEqual(adapter.decision_count, 1)

    def test_each_host_mints_its_own_authority(self):
        first = self.host()
        second = self.host()
        self.assertIsNot(first._focus_authority, second._focus_authority)

    def test_foreign_handle_is_refused(self):
        first = self.host().make_focus_adapter(lambda o, t: True)
        second = self.host().make_focus_adapter(lambda o, t: True)
        handle = first.observe_window("app.a", 9)
        with self.assertRaises(AdapterInputError):
            second.issue_request("app.b", handle)

    def test_repeated_factory_calls_do_not_load_policy_early(self):
        host = self.host()
        for _ in range(3):
            self.assertFalse(host.make_focus_adapter(lambda o, t: True).module_loaded)


if __name__ == "__main__":
    unittest.main()
