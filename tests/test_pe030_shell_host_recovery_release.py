"""PE-030: bounded cleanup of the focus adapter on terminal recovery stop.

The ShellHost keeps a single focus-adapter slot and documents shutdown as
terminal. A host already frozen by ``needs_recovery`` must still release that
slot (and the host-supplied ``authorize`` callback it holds) on ``stop()``;
otherwise every retained host for diagnostics also retains one adapter and
one callback after shutdown. No Qt, process, VM or visual code is involved.
"""

import gc
import unittest
import weakref
from pathlib import Path

from canopy_core.registry import PackScan, ShellPackInfo
from canopy_core.shell_host import ShellHost

PACK_ID = "com.example.classic"


class _Authorize:
    """Weakref-able host callback; never called on these stop paths."""

    def __call__(self, origin_app, target_app):
        return True


class _View:
    def __init__(self, failures):
        self.failures = failures

    def prepare(self):
        pass

    def activate(self):
        pass

    def deactivate(self):
        if "deactivate" in self.failures:
            raise RuntimeError("dummy failure; no detail is exposed")

    def dispose(self):
        pass


def _recovery_host():
    """Return (host, adapter weakref, callback weakref) after a frozen stop."""
    info = ShellPackInfo(
        pack_id=PACK_ID, name="classic", description="test presentation",
        directory=Path("/nonexecuted/classic"), entrypoint="ui/Main.qml",
        shell_api=1, ui_engine="qt-qml", capabilities=frozenset({"dock"}),
    )
    failures = {"deactivate": True}
    views = []

    def factory():
        view = _View(failures)
        views.append(view)
        return view

    host = ShellHost(
        PackScan((info,), (), 1), {PACK_ID: factory}, frozenset({"dock"}))
    authorize = _Authorize()
    adapter = host.make_focus_adapter(authorize)
    host.switch(PACK_ID)
    first = host.stop()
    assert first.status == "RECOVERY_REQUIRED" and host.needs_recovery
    adapter_ref = weakref.ref(adapter)
    callback_ref = weakref.ref(authorize)
    return host, adapter_ref, callback_ref


class FocusAdapterRecoveryCleanupTests(unittest.TestCase):
    def test_recovery_stop_releases_adapter_and_authorize_callback(self):
        host, adapter_ref, callback_ref = _recovery_host()
        result = host.stop()
        gc.collect()

        self.assertEqual(result.status, "RECOVERY_REQUIRED")
        self.assertTrue(host.needs_recovery)
        self.assertIsNone(host._focus_adapter)
        self.assertIsNone(adapter_ref())
        self.assertIsNone(callback_ref())

    def test_repeated_frozen_stop_cycles_do_not_retain_adapters(self):
        hosts = []
        adapters = []
        callbacks = []
        for _ in range(16):
            host, adapter_ref, callback_ref = _recovery_host()
            self.assertEqual(host.stop().status, "RECOVERY_REQUIRED")
            hosts.append(host)  # diagnostics keep the host, not its adapter
            adapters.append(adapter_ref)
            callbacks.append(callback_ref)
        gc.collect()

        self.assertEqual(len(hosts), 16)
        self.assertEqual(sum(ref() is not None for ref in adapters), 0)
        self.assertEqual(sum(ref() is not None for ref in callbacks), 0)

    def test_recovery_stop_keeps_recovery_flag_and_audit_counts(self):
        host, adapter_ref, callback_ref = _recovery_host()
        before = host.audit_snapshot()
        self.assertGreater(before.focus_decision_count, -1)
        result = host.stop()
        after = host.audit_snapshot()
        gc.collect()

        self.assertEqual(result.status, "RECOVERY_REQUIRED")
        self.assertFalse(result.success)
        self.assertTrue(host.needs_recovery)
        self.assertEqual(after.focus_decision_count, 0)
        self.assertEqual(after.focus_rejection_count, 0)
        self.assertEqual(after.focus_replay_count, 0)
        self.assertIsNone(adapter_ref())
        self.assertIsNone(callback_ref())


if __name__ == "__main__":
    unittest.main()
