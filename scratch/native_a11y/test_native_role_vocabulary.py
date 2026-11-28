#!/usr/bin/env python3
"""Regression checks for native AT-SPI role vocabulary in the owned metadata gate.

STATIC/CI-SCOPED only: these records are derived from the 1920x1080 native
AT-SPI tree in the already-captured evidence (a11y_summary.json). They do not
start a VM, query AT-SPI or observe a screen reader. Existing behaviour for
Classic-only metadata roles must remain unchanged.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from canopy_features.accessibility import screen_reader_metadata as srm  # noqa: E402

# Roles actually exported by the native Qt/AT-SPI bridge at 1920x1080.
NATIVE_ROLES = (
    "alert", "application", "button", "check box", "filler", "frame",
    "label", "text",
)


class NativeRoleVocabularyTests(unittest.TestCase):
    def test_all_observed_native_roles_are_known(self):
        unknown = [role for role in NATIVE_ROLES if role not in srm.KNOWN_ROLES]
        self.assertEqual(unknown, [], "native AT-SPI roles rejected by metadata gate")

    def test_named_native_records_raise_no_issue(self):
        elements = [
            {"objectName": "native-" + role, "role": role, "name": "Named " + role}
            for role in NATIVE_ROLES
        ]
        self.assertEqual(srm.validate_metadata(elements), [])

    def test_unnamed_native_label_is_reported(self):
        issues = srm.validate_metadata([
            {"objectName": "fileDetailLabel", "role": "label", "name": ""},
        ])
        self.assertEqual([(i.element, i.code) for i in issues],
                         [("fileDetailLabel", srm.EMPTY_NAME)])

    def test_native_check_box_requires_a_name(self):
        self.assertEqual(
            [i.code for i in srm.validate_metadata(
                [{"role": "check box", "name": "    "}])],
            [srm.EMPTY_NAME],
        )

    def test_ignored_native_interactive_role_is_contradictory(self):
        issues = srm.validate_metadata([
            {"objectName": "reducedMotion", "role": "check box",
             "name": "Reduced motion", "ignored": True},
        ])
        self.assertEqual([i.code for i in issues], [srm.IGNORED_INTERACTIVE])

    def test_existing_classic_contract_is_preserved(self):
        self.assertEqual(srm.INFORMATIVE_ROLES, {"alert", "image", "staticText"})
        self.assertEqual(srm.NAMED_ROLES,
                         srm.INTERACTIVE_ROLES | srm.INFORMATIVE_ROLES)
        self.assertEqual(
            [i.code for i in srm.validate_metadata([{"role": "flyingCarpet"}])],
            [srm.INVALID_ROLE],
        )
        self.assertEqual(srm.validate_metadata([{"role": "menuSeparator"}]), [])


if __name__ == "__main__":
    unittest.main()
