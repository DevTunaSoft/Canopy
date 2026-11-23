"""Offline unit tests for permitted-source workspace name/identifier normalization.

These tests are pure Python. They do not compile Qt, launch a desktop, observe
real window events or run on Linux Mint. Future Shell Host wiring is still
needed before this component affects a visible desktop.
"""
import unittest

from canopy_features.windows.workspace_inventory import (
    MAX_PROBLEMS,
    MAX_WORKSPACES,
    WorkspaceInventory,
    WorkspaceInventoryError,
    build_inventory,
    normalize_identifier,
    normalize_name,
    normalize_workspace,
    reconcile,
)

SOURCES = frozenset({"session-dbus", "saved-state"})
MAX_NAME_BYTES_OVERFLOW = 200


def record(identifier, name=None, source="session-dbus"):
    row = {"source": source, "name": name or identifier}
    if identifier is not None:
        row["identifier"] = identifier
    return row


class NormalizeValueTests(unittest.TestCase):
    def test_name_unicode_nfkc_trim_and_collapse(self):
        self.assertEqual(normalize_name("  My\t Work\n"), "My Work")
        self.assertEqual(normalize_name("Ｍｙ　Ｗｏｒｋ"), "My Work")

    def test_name_rejects_empty_control_and_oversize(self):
        with self.assertRaises(WorkspaceInventoryError):
            normalize_name("   ")
        with self.assertRaises(WorkspaceInventoryError):
            normalize_name("Bad\x1bName")
        with self.assertRaises(WorkspaceInventoryError):
            normalize_name("x" * MAX_NAME_BYTES_OVERFLOW)
        with self.assertRaises(WorkspaceInventoryError):
            normalize_name(None)

    def test_identifier_slug_is_stable_and_case_insensitive(self):
        self.assertEqual(normalize_identifier("Dev/Team 1"), "dev-team-1")
        self.assertEqual(normalize_identifier("  DEV_TEAM__1 "), "dev-team-1")
        self.assertEqual(normalize_identifier("dev-team-1"), "dev-team-1")

    def test_identifier_rejects_symbols_only_and_oversize(self):
        with self.assertRaises(WorkspaceInventoryError):
            normalize_identifier("///")
        with self.assertRaises(WorkspaceInventoryError):
            normalize_identifier("x" * 65)
        with self.assertRaises(WorkspaceInventoryError):
            normalize_identifier(7)

    def test_workspace_requires_permitted_source_and_valid_fields(self):
        workspace = normalize_workspace(
            {"source": "saved-state", "name": " Build ", "id": "Build/2"}, SOURCES
        )
        self.assertEqual(workspace.identifier, "build-2")
        self.assertEqual(workspace.name, "Build")
        self.assertEqual(workspace.source, "saved-state")
        with self.assertRaisesRegex(WorkspaceInventoryError, "not permitted"):
            normalize_workspace(record("x", source="untrusted"), SOURCES)
        with self.assertRaisesRegex(WorkspaceInventoryError, "frozenset"):
            normalize_workspace(record("x"), {"session-dbus"})


class InventoryTests(unittest.TestCase):
    def test_empty_snapshot_is_valid(self):
        inventory = build_inventory([], permitted_sources=SOURCES)
        self.assertEqual(inventory.workspaces, ())
        self.assertEqual(inventory.problems, ())
        self.assertIsNone(inventory.get("missing"))

    def test_normalizes_and_orders_by_first_occurrence(self):
        inventory = build_inventory(
            [record("Build/2", "  Build  "), record("Web", "Web Browser")],
            permitted_sources=SOURCES,
        )
        self.assertEqual(inventory.identifiers(), ("build-2", "web"))
        self.assertEqual(inventory.get("build-2").name, "Build")

    def test_duplicate_workspaces_keep_first_occurrence(self):
        inventory = build_inventory(
            [
                record("Dev", "Development", source="session-dbus"),
                record("DEV", "Development", source="saved-state"),
                record("dev", "Different Name", source="saved-state"),
            ],
            permitted_sources=SOURCES,
        )
        self.assertEqual(inventory.identifiers(), ("dev",))
        self.assertEqual(inventory.get("dev").name, "Development")
        self.assertEqual(len(inventory.problems), 2)
        self.assertIn("duplicate", inventory.problems[0].reason)
        self.assertIn("conflicting", inventory.problems[1].reason)

    def test_reordered_workspaces_preserve_snapshot_order(self):
        first = build_inventory(
            [record("a", "Alpha"), record("b", "Beta"), record("c", "Cedar")],
            permitted_sources=SOURCES,
        )
        reordered = build_inventory(
            [record("c", "Cedar"), record("a", "Alpha"), record("b", "Beta")],
            permitted_sources=SOURCES,
        )
        self.assertEqual(first.identifiers(), ("a", "b", "c"))
        self.assertEqual(reordered.identifiers(), ("c", "a", "b"))
        delta = reconcile(first, reordered)
        self.assertEqual(delta.added, ())
        self.assertEqual(delta.removed, ())
        self.assertEqual(delta.renamed, ())
        self.assertEqual(set(delta.reordered), {"a", "b", "c"})
        self.assertIs(delta.inventory, reordered)

    def test_removed_workspaces_are_reported(self):
        previous = build_inventory(
            [record("a", "Alpha"), record("b", "Beta"), record("c", "Cedar")],
            permitted_sources=SOURCES,
        )
        current = build_inventory(
            [record("a", "Alpha"), record("c", "Cedar")], permitted_sources=SOURCES
        )
        delta = reconcile(previous, current)
        self.assertEqual(delta.removed, ("b",))
        self.assertEqual(delta.added, ())
        self.assertEqual(delta.inventory.identifiers(), ("a", "c"))

    def test_added_and_renamed_workspaces_are_reported(self):
        previous = build_inventory([record("a", "Alpha")], permitted_sources=SOURCES)
        current = build_inventory(
            [record("a", "Alpha Renamed"), record("b", "Beta")],
            permitted_sources=SOURCES,
        )
        delta = reconcile(previous, current)
        self.assertEqual(delta.added, ("b",))
        self.assertEqual(delta.renamed, ("a",))
        self.assertEqual(delta.reordered, ())

    def test_non_permitted_and_malformed_records_are_skipped(self):
        inventory = build_inventory(
            [
                record("good", "Good"),
                record("bad", "Bad", source="untrusted"),
                {"source": "session-dbus", "name": "Bad Id", "identifier": "///"},
                "not a mapping",
                {"source": "session-dbus", "name": None},
            ],
            permitted_sources=SOURCES,
        )
        self.assertEqual(inventory.identifiers(), ("good",))
        self.assertEqual(len(inventory.problems), 4)
        self.assertIn("not permitted", inventory.problems[0].reason)

    def test_bounds_are_independent_of_input_size(self):
        records = [record("id-" + str(index)) for index in range(MAX_WORKSPACES + MAX_PROBLEMS + 50)]
        inventory = build_inventory(records, permitted_sources=SOURCES)
        self.assertEqual(len(inventory.workspaces), MAX_WORKSPACES)
        self.assertEqual(len(inventory.problems), MAX_PROBLEMS)
        self.assertTrue(all(p.reason == "workspace limit reached" for p in inventory.problems))

    def test_inventories_and_immutable_and_reconcile_validates_types(self):
        inventory = build_inventory([record("a", "Alpha")], permitted_sources=SOURCES)
        with self.assertRaises(Exception):
            inventory.workspaces = ()
        with self.assertRaises(WorkspaceInventoryError):
            reconcile(inventory, [])
        self.assertIsInstance(inventory, WorkspaceInventory)

    def test_generator_input_supported_and_execution_free(self):
        marker = []
        records = (record("id-" + str(index)) for index in range(3))
        inventory = build_inventory(records, permitted_sources=SOURCES)
        self.assertEqual(len(inventory.identifiers()), 3)
        self.assertEqual(marker, [])


if __name__ == "__main__":
    unittest.main()
