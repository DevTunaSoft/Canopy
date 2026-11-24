"""Regression tests for hostile-but-bounded labels in the parsed source record.

The composer treats ``parse_desktop_actions`` output as a supplied source
record. A deserialized or fault-injected scan with wrong-type labels currently
escapes as a raw ``TypeError`` from the allowlist membership test; repeated
ids currently produce a READY preview whose counts claim distinct actions
that do not exist. Both outcomes must fail closed with the existing
``invalid_actions`` denial, with no raw exception and no fixed safe claims.
Pure data only: no process, I/O, geometry or desktop change.
"""
import unittest
from unittest.mock import patch

from canopy_features.apps import desktop_action_launch_preview as preview_mod
from canopy_features.apps.desktop_action_launch_preview import (
    REASON_INVALID_ACTIONS,
    REASON_OK,
    STATUS_DENIED,
    STATUS_READY,
    compose_desktop_action_launch_preview,
)
from canopy_features.apps.desktop_actions import DesktopAction, DesktopActionScan

TEXT = "[Desktop Entry]\nType=Application\nName=Example\nActions=NewWindow;\n"
OPTIONS = dict(
    allowed_action_ids=("NewWindow",),
    executable="/usr/bin/example",
    allowed_executables=("/usr/bin/example",),
    arguments=("--new-window",),
)
ACTION = DesktopAction("NewWindow", "name", "/usr/bin/example --new-window", "icon")


def compose_with(scan):
    with patch.object(preview_mod, "parse_desktop_actions", return_value=scan):
        return compose_desktop_action_launch_preview(TEXT, **OPTIONS)


class HostileParsedSourceTests(unittest.TestCase):
    def assert_terse_denial(self, result):
        self.assertEqual(result.status, STATUS_DENIED)
        self.assertEqual(result.reason, REASON_INVALID_ACTIONS)
        self.assertFalse(result.ready)
        self.assertEqual(result.declared_count, 0)
        self.assertEqual(result.action_count, 0)
        self.assertEqual(result.argv_length, 0)
        self.assertEqual(result.claims, ())

    def test_unhashable_declared_label_denied_without_raw_exception(self):
        self.assert_terse_denial(
            compose_with(DesktopActionScan((["NewWindow"],), (ACTION,), ())))

    def test_unhashable_action_label_denied_without_raw_exception(self):
        hostile = DesktopAction({"NewWindow": 1}, "name",
                                "/usr/bin/example --new-window", "icon")
        self.assert_terse_denial(
            compose_with(DesktopActionScan(("NewWindow",), (hostile,), ())))

    def test_wrong_type_label_container_denied(self):
        self.assert_terse_denial(
            compose_with(DesktopActionScan(["NewWindow"], (ACTION,), ())))

    def test_duplicate_declared_id_denied(self):
        self.assert_terse_denial(compose_with(
            DesktopActionScan(("NewWindow", "NewWindow"), (ACTION,), ())))

    def test_duplicate_action_id_denied(self):
        self.assert_terse_denial(compose_with(
            DesktopActionScan(("NewWindow",), (ACTION, ACTION), ())))

    def test_well_formed_scan_still_ready(self):
        result = compose_with(DesktopActionScan(("NewWindow",), (ACTION,), ()))
        self.assertEqual(result.status, STATUS_READY)
        self.assertEqual(result.reason, REASON_OK)
        self.assertEqual(result.declared_count, 1)
        self.assertEqual(result.action_count, 1)
        self.assertTrue(result.claims)


if __name__ == "__main__":
    unittest.main()
