"""Read-only, bounded ShellHost audit snapshot contract.

A host must be able to answer "what is my current coordination state?" without
performing any lifecycle action, importing a feature module or mutating state.
The snapshot is one frozen record combining the active presentation id,
recovery flag, host-allowed capability names and focus-adapter decision counts.
"""
from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from canopy_core import capabilities
from canopy_core.registry import PackScan, ShellPackInfo
from canopy_core.shell_host import HostAuditSnapshot, ShellHost

PACK_ID = "com.example.classic"


def scan(caps=frozenset({"dock"})):
    pack = ShellPackInfo(
        pack_id=PACK_ID, name="classic", description="test pack",
        directory=Path("/nonexecuted/classic"), entrypoint="ui/Main.qml",
        shell_api=1, ui_engine="qt-qml", capabilities=caps)
    return PackScan((pack,), (), 1)


class QuietView:
    def prepare(self): pass
    def activate(self): pass
    def deactivate(self): pass
    def dispose(self): pass


class BrokenPrepareView:
    def prepare(self): raise ValueError("prepare failed")
    def activate(self): pass
    def deactivate(self): pass
    def dispose(self): raise ValueError("dispose failed")


class HostAuditSnapshotTests(unittest.TestCase):
    def host(self, factories=None, allow=frozenset({"dock"})):
        return ShellHost(scan(), factories or {}, allow)

    def test_snapshot_record_is_frozen(self):
        snap = self.host().audit_snapshot()
        self.assertIsInstance(snap, HostAuditSnapshot)
        with self.assertRaises(FrozenInstanceError):
            snap.active_pack_id = "tampered"

    def test_empty_host_snapshot_defaults(self):
        snap = self.host().audit_snapshot()
        self.assertIsNone(snap.active_pack_id)
        self.assertIs(snap.needs_recovery, False)
        self.assertEqual(snap.focus_decision_count, 0)
        self.assertEqual(snap.focus_rejection_count, 0)
        self.assertEqual(snap.focus_replay_count, 0)

    def test_capability_names_are_host_allowlist_subset(self):
        allow = frozenset({"dock"})
        snap = self.host(allow=allow).audit_snapshot()
        expected = tuple(n for n in capabilities.names() if n in allow)
        self.assertEqual(snap.capability_names, expected)
        self.assertIsInstance(snap.capability_names, tuple)
        self.assertTrue(all(type(n) is str for n in snap.capability_names))

    def test_empty_allowlist_yields_no_capability_names(self):
        snap = self.host(allow=frozenset()).audit_snapshot()
        self.assertEqual(snap.capability_names, ())

    def test_snapshot_reflects_active_pack(self):
        host = self.host({PACK_ID: QuietView})
        self.assertEqual(host.switch(PACK_ID).status, "SWITCHED")
        snap = host.audit_snapshot()
        self.assertEqual(snap.active_pack_id, PACK_ID)
        self.assertIs(snap.needs_recovery, False)

    def test_snapshot_reflects_recovery_state(self):
        host = self.host({PACK_ID: BrokenPrepareView})
        result = host.switch(PACK_ID)
        self.assertEqual(result.status, "RECOVERY_REQUIRED")
        snap = host.audit_snapshot()
        self.assertIs(snap.needs_recovery, True)
        self.assertIsNone(snap.active_pack_id)

    def test_snapshot_reflects_focus_decision_counts(self):
        host = self.host()
        adapter = host.make_focus_adapter(lambda origin, target: True)
        handle = adapter.observe_window("app.a", 7)
        request = adapter.issue_request("app.b", handle)
        adapter.decide(request)            # GRANTED
        adapter.decide(request)            # REPLAYED
        adapter.decide("garbage")          # REJECTED
        snap = host.audit_snapshot()
        self.assertEqual(snap.focus_decision_count, 3)
        self.assertEqual(snap.focus_rejection_count, 1)
        self.assertEqual(snap.focus_replay_count, 1)

    def test_snapshot_is_read_only_and_stable(self):
        host = self.host({PACK_ID: QuietView})
        host.switch(PACK_ID)
        adapter = host.make_focus_adapter(lambda origin, target: True)
        before = (host.active_id, host.needs_recovery, adapter.decision_count)
        first = host.audit_snapshot()
        second = host.audit_snapshot()
        self.assertEqual(first, second)
        after = (host.active_id, host.needs_recovery, adapter.decision_count)
        self.assertEqual(before, after)

    def test_snapshot_does_not_import_policy_module(self):
        host = self.host()
        adapter = host.make_focus_adapter(lambda origin, target: True)
        self.assertFalse(adapter.module_loaded)
        host.audit_snapshot()
        self.assertFalse(adapter.module_loaded)

    def test_snapshot_tracks_only_latest_adapter(self):
        host = self.host()
        first = host.make_focus_adapter(lambda o, t: True)
        second = host.make_focus_adapter(lambda o, t: True)
        handle = first.observe_window("app.a", 3)
        first.decide(first.issue_request("app.b", handle))
        handle2 = second.observe_window("app.a", 4)
        second.decide(second.issue_request("app.b", handle2))
        second.decide(second.issue_request("app.b", handle2))
        snap = host.audit_snapshot()
        # Bounded single-slot tracking: only the most recent adapter counts.
        self.assertEqual(snap.focus_decision_count, 2)
        self.assertEqual(first.decision_count, 1)
        self.assertEqual(second.decision_count, 2)


if __name__ == "__main__":
    unittest.main()
