"""Offline unit tests for trusted window-role mapping.

No Qt, compositor, Mint session or real window is exercised here. Windows-host
pure-Python behaviour is verified; Linux Mint and compiled Qt remain NOT RUN.
"""
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from canopy_features.windows.window_roles import (
    MAX_WINDOWS, ROLE_POLICIES, TRUSTED_ROLES, DockGroup, ResolvedRole,
    RolePolicy, WindowRecord, WindowRoleError, build_dock_groups, classify,
    policy_for, switch_order,
)


def _window(wid, app, role=(), parent=None):
    return WindowRecord(wid, app, tuple(role), parent)


class TrustedRoleTests(unittest.TestCase):
    def test_fixed_allowlist_and_policies_are_immutable(self):
        self.assertIn("app", TRUSTED_ROLES)
        self.assertIn("dialog", TRUSTED_ROLES)
        self.assertIn("unknown", TRUSTED_ROLES)
        self.assertNotIn("root-shell", TRUSTED_ROLES)
        self.assertTrue(ROLE_POLICIES["app"].dock_group)
        self.assertTrue(ROLE_POLICIES["app"].switchable)
        self.assertFalse(ROLE_POLICIES["app"].transient)
        self.assertTrue(ROLE_POLICIES["dialog"].transient)
        self.assertFalse(ROLE_POLICIES["dialog"].switchable)
        with self.assertRaises(TypeError):
            ROLE_POLICIES["app"] = RolePolicy("x", True, True, False)
        with self.assertRaises(WindowRoleError):
            policy_for("not-a-role")
        with self.assertRaises(WindowRoleError):
            policy_for(True)

    def test_classify_single_trusted_hint(self):
        for role in TRUSTED_ROLES - {"unknown"}:
            with self.subTest(role=role):
                result = classify(_window(1, "org.example.App", (role,)))
                self.assertEqual(result, ResolvedRole(role, True, False))

    def test_no_hint_and_unrecognized_hint_fail_closed(self):
        self.assertEqual(classify(_window(1, "org.example.App")),
                         ResolvedRole("unknown", False, False))
        self.assertEqual(classify(_window(1, "org.example.App", ("root-shell",))),
                         ResolvedRole("unknown", False, False))
        self.assertFalse(ROLE_POLICIES["unknown"].dock_group)
        self.assertFalse(ROLE_POLICIES["unknown"].switchable)


class AmbiguousRoleTests(unittest.TestCase):
    def test_ambiguous_role_is_resolved_to_unknown_not_guessed(self):
        record = _window(1, "org.example.App", ("dialog", "utility"))
        result = classify(record)
        self.assertEqual(result, ResolvedRole("unknown", False, True))
        self.assertTrue(result.ambiguous)
        # Ambiguous windows must not create groups or enter switch order.
        self.assertEqual(build_dock_groups([record]), ())
        self.assertEqual(switch_order([record]), ())

    def test_ambiguous_transient_does_not_hijack_parent_group(self):
        parent = _window(10, "org.example.Files", ("app",))
        ambiguous = _window(11, "org.example.Other", ("menu", "dialog"), 10)
        groups = build_dock_groups([parent, ambiguous])
        self.assertEqual(groups,
                         (DockGroup(("app", "org.example.Files"), (10,)),))
        self.assertEqual(switch_order([parent, ambiguous]), (10,))

    def test_repeated_identical_hint_is_not_ambiguous(self):
        result = classify(_window(1, "org.example.App", ("app", "app")))
        self.assertEqual(result, ResolvedRole("app", True, False))
        self.assertFalse(result.ambiguous)


class MissingParentTests(unittest.TestCase):
    def test_missing_parent_degrades_to_orphan_group(self):
        for parent in (None, 999):
            with self.subTest(parent=parent):
                record = _window(2, "org.example.Editor", ("dialog",), parent)
                groups = build_dock_groups([record])
                self.assertEqual(groups, (DockGroup(("orphan", "org.example.Editor"),
                                                   (2,)),))
                self.assertEqual(switch_order([record]), ())

    def test_orphan_and_real_app_groups_stay_separate(self):
        records = [
            _window(10, "org.example.Files", ("app",)),
            _window(11, "org.example.Files", ("dialog",), 999),
        ]
        self.assertEqual(build_dock_groups(records), (
            DockGroup(("app", "org.example.Files"), (10,)),
            DockGroup(("orphan", "org.example.Files"), (11,)),
        ))

    def test_parent_cycle_is_bounded(self):
        records = [
            _window(1, "org.example.A", ("dialog",), 2),
            _window(2, "org.example.B", ("utility",), 1),
        ]
        groups = build_dock_groups(records)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].window_ids, (1, 2))
        self.assertIn(groups[0].key,
                      {("orphan", "org.example.A"),
                       ("orphan", "org.example.B")})


class GroupingAndSwitchingTests(unittest.TestCase):
    def test_transient_dialog_joins_parent_app_group(self):
        records = [
            _window(10, "org.example.Files", ("app",)),
            _window(11, "org.example.Dialog", ("dialog",), 10),
            _window(12, "org.example.Files", ("splash",), 11),
        ]
        self.assertEqual(build_dock_groups(records), (
            DockGroup(("app", "org.example.Files"), (10, 11, 12)),
        ))
        self.assertEqual(switch_order(records), (10,))

    def test_non_groupable_roles_are_excluded(self):
        records = [
            _window(1, "org.example.Desktop", ("desktop",)),
            _window(2, "org.example.Dock", ("dock",)),
            _window(3, "org.example.Notify", ("notification",)),
        ]
        self.assertEqual(build_dock_groups(records), ())
        self.assertEqual(switch_order(records), ())

    def test_switch_order_preserves_caller_order_and_is_deterministic(self):
        records = [
            _window(30, "org.example.C", ("app",)),
            _window(10, "org.example.A", ("dialog",), 30),
            _window(20, "org.example.B", ("app",)),
        ]
        expected = (30, 20)
        self.assertEqual(switch_order(records), expected)
        self.assertEqual(switch_order(tuple(reversed(records))), (20, 30))
        self.assertEqual(build_dock_groups(records), build_dock_groups(records))

    def test_results_are_immutable(self):
        record = _window(1, "org.example.App", ("app",))
        with self.assertRaises(FrozenInstanceError):
            record.app_id = "org.example.Other"
        group = build_dock_groups([record])[0]
        with self.assertRaises(FrozenInstanceError):
            group.key = ("app", "x")


class ValidationTests(unittest.TestCase):
    def test_invalid_records_are_rejected(self):
        bad = [
            None,
            [1],
            _window(True, "org.example.App"),
            _window(0, "org.example.App"),
            _window(1, ""),
            WindowRecord(1, "org.example.App", ["app"]),
            _window(1, "org.example.App", (1,)),
            _window(1, "org.example.App", ("app",), True),
        ]
        for record in bad:
            with self.subTest(record=repr(record)):
                with self.assertRaises(WindowRoleError):
                    build_dock_groups([record])
                with self.assertRaises(WindowRoleError):
                    switch_order([record])

    def test_duplicate_ids_and_oversized_input_rejected(self):
        duplicate = [_window(1, "org.example.A"), _window(1, "org.example.B")]
        with self.assertRaises(WindowRoleError):
            build_dock_groups(duplicate)
        oversized = [_window(i + 1, "org.example.App") for i in range(MAX_WINDOWS + 1)]
        with self.assertRaises(WindowRoleError):
            build_dock_groups(oversized)

    def test_no_polling_threads_network_or_qt_imports(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/windows/window_roles.py").read_text(encoding="utf-8")
        for forbidden in ("QTimer", "PyQt", "PySide", "subprocess",
                          "import socket", "Thread(", "asyncio",
                          "time.sleep", "import os"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
