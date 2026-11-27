"""Static-contract tests for the PE-082 / QA-005-005 accessible-name gate.

These tests exercise pure metadata records only. They do not compile Qt, do not
contact AT-SPI or Orca, and do not claim any screen-reader or Linux Mint runtime
behaviour. They prove the source-level gate contract, nothing more.
"""
import unittest

from canopy_features.accessibility import screen_reader_metadata as srm
from canopy_features.accessibility.screen_reader_metadata import (
    EMPTY_NAME,
    MISSING_LABEL,
    validate_metadata,
)


class InformativeRoleNameGateTests(unittest.TestCase):
    def codes(self, elements, **kwargs):
        return [issue.code for issue in validate_metadata(elements, **kwargs)]

    def test_informative_roles_are_declared_and_distinct(self):
        self.assertEqual(set(srm.INFORMATIVE_ROLES),
                         {"alert", "image", "staticText"})
        self.assertFalse(srm.INFORMATIVE_ROLES & srm.INTERACTIVE_ROLES)
        self.assertTrue(srm.INFORMATIVE_ROLES <= srm.KNOWN_ROLES)
        self.assertEqual(srm.NAMED_ROLES,
                         srm.INTERACTIVE_ROLES | srm.INFORMATIVE_ROLES)

    def test_unlabelled_informative_roles_are_reported(self):
        elements = [
            {"objectName": "clockImage", "role": "image"},
            {"objectName": "clockText", "role": "staticText"},
            {"objectName": "launchAlert", "role": "alert"},
        ]
        self.assertEqual(
            [(issue.element, issue.code) for issue in validate_metadata(elements)],
            [("clockImage", MISSING_LABEL), ("clockText", MISSING_LABEL),
             ("launchAlert", MISSING_LABEL)],
        )

    def test_empty_and_whitespace_informative_names_are_reported(self):
        self.assertEqual(self.codes([{"role": "image", "name": ""}]), [EMPTY_NAME])
        self.assertEqual(self.codes([{"role": "staticText", "label": " \t"}]),
                         [EMPTY_NAME])
        self.assertEqual(self.codes([{"role": "alert", "name": None}]),
                         [MISSING_LABEL])

    def test_named_informative_roles_are_clean(self):
        elements = [
            {"objectName": "canopyClockIcon", "role": "image",
             "name": "Canopy penguin"},
            {"objectName": "canopyClockLabel", "role": "staticText",
             "label": "14:32"},
            {"objectName": "canopyStatus", "role": "alert",
             "name": "File manager unavailable"},
        ]
        self.assertEqual(self.codes(elements), [])

    def test_decorative_informative_role_needs_explicit_ignored(self):
        self.assertEqual(self.codes([{"role": "image"}]), [MISSING_LABEL])
        self.assertEqual(self.codes([{"role": "image", "ignored": True}]), [])

    def test_truthy_non_boolean_ignored_fails_closed(self):
        for value in ("true", 1, [], {}, None):
            with self.subTest(value=value):
                codes = self.codes([{"role": "image", "ignored": value}])
                self.assertIn(srm.INVALID_IGNORED, codes)
                self.assertIn(MISSING_LABEL, codes)

    def test_ignored_interactive_role_is_reported(self):
        issues = validate_metadata([{"objectName": "filesButton", "role": "button",
                                     "name": "Files", "ignored": True}])
        self.assertEqual([issue.code for issue in issues],
                         [srm.IGNORED_INTERACTIVE])

    def test_non_informative_decorations_still_need_no_name(self):
        self.assertEqual(self.codes([
            {"role": "menuSeparator"},
            {"role": "container"},
            {"role": "group"},
        ]), [])

    def test_custom_role_sets_are_honoured(self):
        self.assertEqual(
            self.codes([{"role": "image"}], informative_roles=frozenset()), [])
        self.assertEqual(
            self.codes(
                [{"role": "statusLamp"}],
                known_roles=srm.KNOWN_ROLES | {"statusLamp"},
                informative_roles=frozenset({"statusLamp"}),
            ),
            [MISSING_LABEL],
        )
        self.assertNotIn("statusLamp", srm.INFORMATIVE_ROLES)

    def test_validation_is_pure(self):
        elements = [{"role": "image", "ignored": True}, {"role": "alert"}]
        before = [dict(element) for element in elements]
        first = validate_metadata(elements)
        self.assertEqual(first, validate_metadata(elements))
        self.assertEqual(elements, before)


if __name__ == "__main__":
    unittest.main()
