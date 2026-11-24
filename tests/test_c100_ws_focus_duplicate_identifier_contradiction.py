"""Regression tests: duplicate workspace identifiers must not read as success.

Both bounded snapshots validate their caller-supplied value objects. A raw
WorkspaceInventory carrying two workspaces with the same identifier is a
contradictory workspace claim: the canonical builder reports such a duplicate
as a problem, so a composition that reports STATUS_OK with zero problems is a
false workspace-success claim. These tests fail closed instead.
"""

import unittest

from canopy_features.reliability import screen_topology_change as topology
from canopy_features.windows import focus_intents as focus
from canopy_features.windows import workspace_inventory as inventory


def _display():
    return topology.ScreenTopologyModel().apply(topology.Topology(
        [topology.Monitor("eDP-1", 1920, 1080, True)]))


def _focus():
    return focus.FocusBroker(lambda *_: True)


def _workspaces():
    return (inventory.Workspace("alpha", "Alpha", "test"),
            inventory.Workspace("beta", "Beta", "test"))


def _duplicate_inventory():
    return inventory.WorkspaceInventory(
        (_workspaces()[0],
         inventory.Workspace("alpha", "Alpha Duplicate", "test")), ())


def _quiet_reconciliation(inv):
    return inventory.reconcile(inv, inv)


class DuplicateIdentifierContradictionTests(unittest.TestCase):
    def test_display_focus_map_rejects_duplicate_workspace_identifiers(self):
        from canopy_features.windows import display_focus_map_snapshot as module
        with self.assertRaises(module.SnapshotError):
            module.compose(_display(), _duplicate_inventory(), _focus())

    def test_reconciliation_snapshot_rejects_duplicate_workspace_identifiers(self):
        from canopy_features.windows import workspace_reconciliation_snapshot as module
        reconciliation = _quiet_reconciliation(_duplicate_inventory())
        with self.assertRaises(module.SnapshotError):
            module.compose(reconciliation, _display())

    def test_unique_identifiers_still_compose(self):
        from canopy_features.windows import display_focus_map_snapshot as dfm
        from canopy_features.windows import workspace_reconciliation_snapshot as wrs
        inv = inventory.WorkspaceInventory(_workspaces(), ())
        display = _display()
        self.assertEqual(
            dfm.compose(display, inv, _focus()).workspace.identifiers,
            ("alpha", "beta"))
        record = wrs.compose(_quiet_reconciliation(inv), display)
        self.assertEqual(record.workspace.identifiers, ("alpha", "beta"))
        self.assertEqual(record.status, wrs.STATUS_OK)


if __name__ == "__main__":
    unittest.main()
