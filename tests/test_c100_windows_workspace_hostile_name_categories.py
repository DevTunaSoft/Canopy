"""Hostile-but-bounded workspace names must fail closed, not look valid.

``normalize_name`` rejected only Unicode ``Cc`` controls. Other non-printing
categories (``Cf``, ``Co``, ``Cn``, ``Zl``, ``Zp``, ``Cs``) survived NFKC and
whitespace collapse. ``build_inventory`` then emitted a workspace with zero
problems for a name such as ``Dev\\uffffOps`` -- a false inventory-valid claim
for text that cannot be displayed or round-tripped as interoperable Unicode.

Pure Python only; no Qt, visual or desktop behavior is claimed here.
"""
import unicodedata
import unittest

from canopy_features.windows.workspace_inventory import (
    WorkspaceInventoryError,
    build_inventory,
    normalize_name,
    normalize_workspace,
)

PERMITTED = frozenset({"session-dbus", "saved-state"})

# Each probe is a single non-printing scalar embedded in an otherwise valid,
# short, ASCII name. Byte length is far below MAX_NAME_BYTES: the rejection
# must come from the character gate, not from the size bound.
HOSTILE_CHARS = {
    "Cf_zero_width_space": "\u200b",
    "Cf_zero_width_joiner": "\u200d",
    "Co_private_use": "\ue000",
    "Cn_noncharacter_bmp": "\uffff",
    "Cn_noncharacter_astral": "\U0001fffe",
    "Zl_line_separator": "\u2028",
    "Zp_paragraph_separator": "\u2029",
    "Cs_unpaired_surrogate": "\ud800",
}


class HostileNameCategoryTests(unittest.TestCase):
    def test_nonprinting_categories_are_rejected_by_normalize_name(self):
        for label, char in HOSTILE_CHARS.items():
            with self.subTest(label=label, category=unicodedata.category(char)):
                with self.assertRaises(WorkspaceInventoryError):
                    normalize_name("Dev" + char + "Ops")

    def test_build_inventory_reports_hostile_names_instead_of_valid_claim(self):
        records = (
            {"source": "session-dbus", "name": "Clean", "identifier": "clean"},
            {"source": "session-dbus", "name": "Dev\uffffOps", "identifier": "dev-nonchar"},
            {"source": "saved-state", "name": "Dev\u2028Ops", "identifier": "dev-separator"},
            {"source": "session-dbus", "name": "Other", "identifier": "other"},
        )
        inventory = build_inventory(records, permitted_sources=PERMITTED)
        self.assertEqual(inventory.identifiers(), ("clean", "other"))
        self.assertEqual(len(inventory.problems), 2)
        self.assertEqual(
            tuple(problem.location for problem in inventory.problems),
            ("record[1]", "record[2]"),
        )
        for problem in inventory.problems:
            self.assertIn("control character", problem.reason)

    def test_normalize_workspace_rejects_hostile_name(self):
        for label, char in HOSTILE_CHARS.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(WorkspaceInventoryError, "control character"):
                    normalize_workspace(
                        {"source": "session-dbus", "name": "Dev" + char + "Ops"},
                        PERMITTED,
                    )

    def test_documented_whitespace_and_nfkc_names_still_valid(self):
        self.assertEqual(normalize_name("My\t Work\n"), "My Work")
        self.assertEqual(normalize_name("Ｍｙ　Ｗｏｒｋ"), "My Work")
        self.assertEqual(normalize_name("  Dev  Ops  "), "Dev Ops")


if __name__ == "__main__":
    unittest.main()
