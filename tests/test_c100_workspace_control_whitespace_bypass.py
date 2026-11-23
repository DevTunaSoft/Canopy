"""Regression tests: workspace names must reject Python-whitespace controls.

``str.split()`` treats VT, FF and U+001C-U+001F as whitespace and silently
rewrites them to spaces. The documented ``normalize_name`` contract rejects
control-laden names, so those controls must be checked before collapsing.
Pure Python only; no Qt, visual or desktop behavior is claimed here.
"""
import unittest

from canopy_features.windows.workspace_inventory import (
    WorkspaceInventoryError,
    build_inventory,
    normalize_name,
    normalize_workspace,
)

SOURCES = frozenset({"session-dbus", "saved-state"})


class ControlNameTests(unittest.TestCase):
    def test_whitespace_classified_c0_controls_rejected(self):
        for control in ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x1f"):
            with self.subTest(control=repr(control)):
                with self.assertRaises(WorkspaceInventoryError):
                    normalize_name("Dev" + control + "Ops")

    def test_del_and_c1_controls_rejected(self):
        for control in ("\x7f", "\x85", "\x9f"):
            with self.subTest(control=repr(control)):
                with self.assertRaises(WorkspaceInventoryError):
                    normalize_name("Dev" + control + "Ops")

    def test_escape_control_still_rejected(self):
        with self.assertRaises(WorkspaceInventoryError):
            normalize_name("Bad\x1bName")

    def test_documented_whitespace_controls_still_collapsed(self):
        for control in ("\t", "\n", "\r"):
            with self.subTest(control=repr(control)):
                self.assertEqual(normalize_name("My" + control + " Work"), "My Work")

    def test_control_after_nfkc_is_rejected(self):
        # NFKC folds the fullwidth characters but must not hide the control.
        with self.assertRaises(WorkspaceInventoryError):
            normalize_name("Ｍｙ\x1cＷｏｒｋ")

    def test_build_inventory_skips_control_laden_name(self):
        inventory = build_inventory(
            [
                {"source": "session-dbus", "name": "Dev\x1cOps", "identifier": "dev"},
                {"source": "session-dbus", "name": "Dev\x1cOps"},
                {"source": "saved-state", "name": "Clean", "identifier": "clean"},
            ],
            permitted_sources=SOURCES,
        )
        self.assertEqual(inventory.identifiers(), ("clean",))
        self.assertEqual(len(inventory.problems), 2)
        for problem in inventory.problems:
            self.assertIn("control character", problem.reason)

    def test_normalize_workspace_rejects_control_laden_name(self):
        with self.assertRaisesRegex(WorkspaceInventoryError, "control character"):
            normalize_workspace(
                {"source": "session-dbus", "name": "Dev\x0bOps"}, SOURCES
            )

    def test_valid_names_still_accepted(self):
        self.assertEqual(normalize_name("  Dev  Ops  "), "Dev Ops")
        self.assertEqual(normalize_name("My\t Work\n"), "My Work")


if __name__ == "__main__":
    unittest.main()
