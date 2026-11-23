"""Surrogate-bearing workspace names must fail closed with the domain error.

An unpaired UTF-16 surrogate survives NFKC, whitespace collapse and the C0
control check, but cannot be UTF-8 encoded. ``_byte_length`` must translate
that raw ``UnicodeEncodeError`` into ``WorkspaceInventoryError`` so that
``build_inventory`` can skip the bad record and report a problem instead of
crashing the whole snapshot.
"""
import unittest

from canopy_features.windows.workspace_inventory import (  # noqa: E402
    WorkspaceInventoryError,
    build_inventory,
    normalize_identifier,
    normalize_name,
    normalize_workspace,
)

PERMITTED = frozenset({"shell"})
SURROGATES = ("\ud800", "\udfff", "Dev\ud800Ops", "\ud83dDesktop", "Ops\udfff")


class WorkspaceSurrogateNameTest(unittest.TestCase):
    def test_normalize_name_rejects_surrogates_with_domain_error(self):
        for value in SURROGATES:
            with self.subTest(value=ascii(value)):
                with self.assertRaises(WorkspaceInventoryError):
                    normalize_name(value)

    def test_normalize_workspace_rejects_surrogate_name(self):
        record = {"source": "shell", "name": "Dev\ud800Ops"}
        with self.assertRaises(WorkspaceInventoryError):
            normalize_workspace(record, PERMITTED)

    def test_build_inventory_skips_surrogate_record_and_reports_problem(self):
        records = (
            {"source": "shell", "name": "Good"},
            {"source": "shell", "name": "Dev\ud800Ops"},
        )
        inv = build_inventory(records, permitted_sources=PERMITTED)
        self.assertEqual(len(inv.workspaces), 1)
        self.assertEqual(inv.workspaces[0].name, "Good")
        self.assertEqual(len(inv.problems), 1)
        self.assertIn("record[1]", inv.problems[0].location)

    def test_valid_name_still_accepted(self):
        self.assertEqual(normalize_name("  Dev   Ops  "), "Dev Ops")

    def test_c0_control_still_rejected(self):
        with self.assertRaises(WorkspaceInventoryError):
            normalize_name("Dev\x01Ops")

    def test_byte_bound_still_enforced(self):
        with self.assertRaises(WorkspaceInventoryError):
            normalize_name("a" * 200)

    def test_identifier_byte_bound_still_enforced(self):
        # normalize_identifier routes through the same _byte_length helper;
        # its slug regex removes surrogates before encoding, so only the
        # ordinary byte bound applies here.
        with self.assertRaises(WorkspaceInventoryError):
            normalize_identifier("a" * 200)


if __name__ == "__main__":
    unittest.main()
