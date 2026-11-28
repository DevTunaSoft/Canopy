#!/usr/bin/env python3
"""Scoped tests for the M3 native window-management decision boundary.

Ownership is limited to scratch/native_windows/ (tests/ is owned by another
workstream), so these are run explicitly with the worktree root on PYTHONPATH
rather than through Foundation's tests/ discovery.
"""
import unittest

from canopy_features.windows.native_window_management import (
    EWMH_ACTIVE_WINDOW, FACILITY_EWMH, FACILITY_KWIN,
    NativeCommand, NativeWindowManager, RecoveryPlan, SnapshotError,
    ManagerClosed, parse_snapshot,
)


def snapshot(*, current="code", active="0x10", windows=None):
    return parse_snapshot({
        "source": "kwin-dbus+ewmh",
        "workspaces": [
            {"identifier": "code", "ordinal": 1, "name": "Code"},
            {"identifier": "docs", "ordinal": 2, "name": "Docs"},
        ],
        "windows": [
            {"window_id": "0x10", "workspace": "code", "title": "Editor"},
            {"window_id": "0x11", "workspace": "code", "title": "Terminal"},
            {"window_id": "0x20", "workspace": "docs", "title": "Reader"},
        ] if windows is None else windows,
        "current_workspace": current,
        "active_window": active,
    })


class SnapshotTests(unittest.TestCase):
    def test_valid_snapshot_and_inventory_order(self):
        manager = NativeWindowManager(snapshot())
        self.assertEqual(manager.workspace_inventory(),
                         (("code", 1, "Code"), ("docs", 2, "Docs")))
        self.assertEqual(manager.snapshot_state()["window_count"], 3)

    def test_rejects_unordered_and_scalar_collections(self):
        for bad in ("code", b"code", {"identifier": "code"}, {1, 2}, 7):
            with self.subTest(bad=bad):
                record = {
                    "source": "kwin-dbus+ewmh",
                    "workspaces": bad,
                    "windows": (),
                    "current_workspace": "code",
                    "active_window": "",
                }
                with self.assertRaises(SnapshotError):
                    parse_snapshot(record)

    def test_rejects_duplicate_workspace_and_window_ids(self):
        with self.assertRaises(SnapshotError):
            parse_snapshot({
                "source": "kwin-dbus+ewmh",
                "workspaces": [{"identifier": "a", "ordinal": 1, "name": "A"},
                               {"identifier": "a", "ordinal": 2, "name": "B"}],
                "windows": (), "current_workspace": "a", "active_window": "",
            })
        with self.assertRaises(SnapshotError):
            snapshot(windows=[
                {"window_id": "0x10", "workspace": "code", "title": "A"},
                {"window_id": "0x10", "workspace": "code", "title": "B"},
            ])

    def test_rejects_cross_field_contradictions(self):
        with self.assertRaises(SnapshotError):
            snapshot(current="absent")
        with self.assertRaises(SnapshotError):
            snapshot(active="0x999")
        with self.assertRaises(SnapshotError):
            snapshot(active="0x20")  # on docs, not current code

    def test_rejects_unsafe_control_and_bool_ordinal(self):
        with self.assertRaises(SnapshotError):
            parse_snapshot({
                "source": "kwin-dbus+ewmh", "workspaces": [], "windows": [],
                "current_workspace": "co\u200bde", "active_window": "",
            })
        with self.assertRaises(SnapshotError):
            parse_snapshot({
                "source": "kwin-dbus+ewmh",
                "workspaces": [{"identifier": "a", "ordinal": True, "name": "A"}],
                "windows": (), "current_workspace": "a", "active_window": "",
            })

    def test_lookup_is_type_safe(self):
        manager = NativeWindowManager(snapshot())
        with self.assertRaises(SnapshotError):
            manager.snapshot.window(["0x10"])
        with self.assertRaises(SnapshotError):
            manager.snapshot.workspace(None)


class PlanTests(unittest.TestCase):
    def test_workspace_switch_uses_allowlisted_kwin_dbus_call(self):
        manager = NativeWindowManager(snapshot())
        plan = manager.plan_workspace_switch("docs")
        self.assertEqual(plan.outcome, "planned")
        self.assertEqual(plan.command.facility, FACILITY_KWIN)
        self.assertEqual(plan.command.operation, "setCurrentDesktop")
        self.assertEqual(plan.command.arguments, (2,))
        self.assertEqual(plan.command.verify_property, "currentDesktop")
        self.assertFalse(plan.command.to_dict()["executed"])
        self.assertEqual(plan.runtime, "NOT_RUN")
        self.assertEqual(plan.screen_reader, "NOT_RUN")

    def test_workspace_switch_noop_and_unknown(self):
        manager = NativeWindowManager(snapshot())
        self.assertEqual(manager.plan_workspace_switch("code").reason,
                         "already_on_workspace")
        self.assertIsNone(manager.plan_workspace_switch("missing").command)

    def test_activation_uses_ewmh_and_readback(self):
        manager = NativeWindowManager(snapshot())
        plan = manager.plan_activation("0x11")
        self.assertEqual(plan.command.facility, FACILITY_EWMH)
        self.assertEqual(plan.command.operation, EWMH_ACTIVE_WINDOW)
        self.assertEqual(plan.command.arguments, ("0x11",))
        self.assertEqual(plan.command.verify_property, EWMH_ACTIVE_WINDOW)
        self.assertEqual(manager.plan_activation("0x20").reason,
                         "off_workspace_window")
        self.assertEqual(manager.plan_activation("0x99").reason,
                         "unknown_window")
        with self.assertRaises(SnapshotError):
            manager.plan_activation(16)

    def test_focus_recovery_excludes_lost_window_and_other_workspace(self):
        manager = NativeWindowManager(snapshot())
        plan = manager.plan_focus_recovery("0x10")
        self.assertEqual(plan.outcome, "planned")
        self.assertEqual(plan.command.arguments, ("0x11",))
        self.assertEqual(plan.reason, "fallback_from_snapshot")
        self.assertEqual(manager.plan_focus_recovery("0x11").command.arguments,
                         ("0x10",))

    def test_focus_recovery_without_eligible_fallback_is_empty(self):
        manager = NativeWindowManager(snapshot(windows=[
            {"window_id": "0x10", "workspace": "code", "title": "Editor"},
            {"window_id": "0x20", "workspace": "docs", "title": "Reader"},
        ]))
        plan = manager.plan_focus_recovery("0x10")
        self.assertEqual(plan.outcome, "no_command")
        self.assertEqual(plan.reason, "no_eligible_fallback")
        self.assertIsNone(plan.command)

    def test_command_allowlists_fail_closed(self):
        with self.assertRaises(SnapshotError):
            NativeCommand("activate", "shell-exec", "rm", (), "x")
        with self.assertRaises(SnapshotError):
            NativeCommand("activate", FACILITY_KWIN, "killWindow", (), "currentDesktop")
        with self.assertRaises(SnapshotError):
            NativeCommand("activate", FACILITY_EWMH, "_NET_WM_NAME", (), EWMH_ACTIVE_WINDOW)
        with self.assertRaises(SnapshotError):
            NativeCommand("planned", FACILITY_EWMH, EWMH_ACTIVE_WINDOW, (), EWMH_ACTIVE_WINDOW)
        with self.assertRaises(SnapshotError):
            RecoveryPlan("planned", "x", None)


class StateTests(unittest.TestCase):
    def test_observe_updates_one_authoritative_state(self):
        manager = NativeWindowManager(snapshot())
        manager.observe(current_workspace="docs", active_window="0x20")
        state = manager.snapshot_state()
        self.assertEqual(state["current_workspace"], "docs")
        self.assertEqual(state["active_window"], "0x20")
        self.assertEqual(state["observation"], "NOT_PERFORMED")
        self.assertEqual(state["duplicate_compositors"], 0)

    def test_observe_rejects_hostile_readback_without_mutation(self):
        manager = NativeWindowManager(snapshot())
        for kwargs in ({"current_workspace": "other"},
                       {"active_window": "0x20"},
                       {"active_window": ["0x10"]},
                       {"current_workspace": 2}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SnapshotError):
                manager.observe(**kwargs)
        self.assertEqual(manager.snapshot.active_window, "0x10")
        self.assertEqual(manager.rejections, 4)

    def test_history_is_bounded_and_immutable(self):
        manager = NativeWindowManager(snapshot(), history_limit=2)
        manager.plan_workspace_switch("docs")
        manager.plan_activation("0x11")
        manager.plan_focus_recovery("0x10")
        self.assertEqual(len(manager.history), 2)
        with self.assertRaises(TypeError):
            manager.history[0] = None

    def test_no_snapshot_and_close_fail_closed(self):
        manager = NativeWindowManager()
        with self.assertRaises(SnapshotError):
            manager.workspace_inventory()
        manager.ingest(snapshot())
        manager.close()
        with self.assertRaises(ManagerClosed):
            manager.workspace_inventory()
        manager.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
