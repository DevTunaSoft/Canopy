"""Resource cleanup contract for ShellHost lifecycle shutdown.

`stop()` must release the host's single focus-adapter slot and the host-supplied
authorize callback it retains. The host object may legitimately stay alive
after shutdown (diagnostics, logging, audit), so retained adapters/callbacks
would keep arbitrary host resources alive with no bound and no eviction.

Run: python -m unittest tests.test_core_shell_host_resource_cleanup -v
"""
import gc
from pathlib import Path
import unittest
import weakref

from canopy_core.registry import PackScan, ShellPackInfo
from canopy_core.shell_host import ShellHost


def host():
    pack = ShellPackInfo(
        pack_id="com.example.classic", name="classic", description="test pack",
        directory=Path("/nonexecuted/classic"), entrypoint="ui/Main.qml",
        shell_api=1, ui_engine="qt-qml", capabilities=frozenset({"dock"}))
    return ShellHost(PackScan((pack,), (), 1), {}, frozenset({"dock"}))


class Authorize:
    """A host callback object whose liveness can be observed."""

    def __call__(self, origin, target):
        return True


class FocusAdapterCleanupTests(unittest.TestCase):
    def test_stop_releases_focus_adapter_while_host_stays_alive(self):
        h = host()
        adapter = h.make_focus_adapter(Authorize())
        reference = weakref.ref(adapter)
        del adapter
        gc.collect()
        self.assertIsNotNone(reference(), "precondition: adapter held by host")
        h.stop()
        gc.collect()
        self.assertIsNone(reference(), "stop() must release the adapter slot")

    def test_stop_releases_host_authorize_callback(self):
        h = host()
        callback = Authorize()
        callback_ref = weakref.ref(callback)
        h.make_focus_adapter(callback)
        del callback
        gc.collect()
        self.assertIsNotNone(callback_ref(), "precondition: callback held by adapter")
        h.stop()
        gc.collect()
        self.assertIsNone(callback_ref(), "stop() must release the host callback")

    def test_audit_snapshot_after_stop_has_no_adapter_counts(self):
        h = host()
        adapter = h.make_focus_adapter(Authorize())
        handle = adapter.observe_window("app.a", 7)
        adapter.decide(adapter.issue_request("app.b", handle))
        self.assertEqual(h.audit_snapshot().focus_decision_count, 1)
        h.stop()
        snap = h.audit_snapshot()
        self.assertEqual(snap.focus_decision_count, 0)
        self.assertEqual(snap.focus_rejection_count, 0)
        self.assertEqual(snap.focus_replay_count, 0)

    def test_stop_is_idempotent_for_cleanup(self):
        h = host()
        adapter = h.make_focus_adapter(Authorize())
        reference = weakref.ref(adapter)
        del adapter
        h.stop()
        h.stop()
        gc.collect()
        self.assertIsNone(reference())

    def test_many_stopped_hosts_retain_no_adapters(self):
        hosts = []
        adapters = []
        for _ in range(32):
            h = host()
            hosts.append(h)
            adapters.append(weakref.ref(h.make_focus_adapter(Authorize())))
        for h in hosts:
            h.stop()
        gc.collect()
        self.assertEqual(sum(ref() is not None for ref in adapters), 0)


class ControlTests(unittest.TestCase):
    """Controls proving the fix does not change pre-shutdown behavior."""

    def test_adapter_works_before_stop(self):
        h = host()
        adapter = h.make_focus_adapter(Authorize())
        handle = adapter.observe_window("app.a", 7)
        self.assertTrue(adapter.decide(adapter.issue_request("app.b", handle)).allowed)
        self.assertEqual(h.audit_snapshot().focus_decision_count, 1)

    def test_single_slot_replacement_unchanged(self):
        h = host()
        first = h.make_focus_adapter(Authorize())
        second = h.make_focus_adapter(Authorize())
        self.assertIsNot(first, second)
        self.assertEqual(h.audit_snapshot().focus_decision_count, 0)

    def test_stop_still_returns_stopped(self):
        h = host()
        self.assertEqual(h.stop().status, "STOPPED")

    def test_stop_without_adapter_is_safe(self):
        h = host()
        h.stop()
        self.assertEqual(h.audit_snapshot().focus_decision_count, 0)


if __name__ == "__main__":
    unittest.main()
