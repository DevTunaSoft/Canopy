"""Offline unit tests for accessible role, label and name metadata validation.

These tests exercise metadata records only. They do not compile Qt, run a
screen reader or prove Linux Mint desktop acceptance.
"""
import unittest

from canopy_features.accessibility.screen_reader_metadata import (
    EMPTY_NAME,
    INVALID_DESCRIPTION,
    INVALID_ELEMENT,
    INVALID_NAME,
    INVALID_ROLE,
    MISSING_LABEL,
    validate_metadata,
)


class ScreenReaderMetadataTests(unittest.TestCase):
    def codes(self, elements):
        return [issue.code for issue in validate_metadata(elements)]

    def test_named_button_is_valid(self):
        elements = [{"objectName": "filesButton", "role": "button",
                     "name": "Toggle Files preview"}]
        self.assertEqual(self.codes(elements), [])

    def test_missing_label_on_button_is_reported(self):
        elements = [{"objectName": "filesButton", "role": "button"}]
        issues = validate_metadata(elements)
        self.assertEqual([issue.code for issue in issues], [MISSING_LABEL])
        self.assertEqual(issues[0].element, "filesButton")

    def test_none_name_on_button_is_reported_as_missing_label(self):
        elements = [{"role": "button", "name": None}]
        self.assertEqual(self.codes(elements), [MISSING_LABEL])

    def test_empty_button_name_is_reported(self):
        elements = [{"objectName": "filesButton", "role": "button", "name": ""}]
        issues = validate_metadata(elements)
        self.assertEqual([issue.code for issue in issues], [EMPTY_NAME])
        self.assertEqual(issues[0].element, "filesButton")

    def test_whitespace_only_button_name_is_reported(self):
        elements = [{"role": "button", "name": "   \t"}]
        self.assertEqual(self.codes(elements), [EMPTY_NAME])

    def test_empty_menu_item_name_is_reported(self):
        elements = [{"role": "menuItem", "label": " "}]
        self.assertEqual(self.codes(elements), [EMPTY_NAME])

    def test_label_field_is_accepted_as_accessible_name(self):
        elements = [{"role": "button", "label": "Canopy penguin launcher"}]
        self.assertEqual(self.codes(elements), [])

    def test_plain_decorative_roles_do_not_require_a_name(self):
        # Informative non-interactive roles (image/staticText/alert) do require
        # a name now; these structural roles still do not. See PE-082.
        elements = [
            {"role": "menuSeparator"},
            {"role": "label", "name": "Files"},
            {"role": "container"},
        ]
        self.assertEqual(self.codes(elements), [])

    def test_unknown_role_is_reported(self):
        elements = [{"role": "flyingCarpet", "name": "Go"}]
        self.assertEqual(self.codes(elements), [INVALID_ROLE])

    def test_missing_and_empty_role_are_reported(self):
        self.assertEqual(self.codes([{"name": "Go"}]), [INVALID_ROLE])
        self.assertEqual(self.codes([{"role": "", "name": "Go"}]), [INVALID_ROLE])

    def test_non_string_name_and_description_are_reported(self):
        elements = [{"role": "button", "name": 42, "description": ["bad"]}]
        self.assertEqual(self.codes(elements), [INVALID_NAME, INVALID_DESCRIPTION])

    def test_non_mapping_element_is_reported_without_crashing(self):
        self.assertEqual(self.codes(["not a record", None]),
                         [INVALID_ELEMENT, INVALID_ELEMENT])

    def test_index_identifier_used_when_object_name_absent(self):
        issues = validate_metadata([{"role": "button"}])
        self.assertEqual(issues[0].element, "elements[0]")

    def test_only_defective_elements_are_reported(self):
        elements = [
            {"objectName": "good", "role": "button", "name": "Open Files"},
            {"objectName": "bad", "role": "button", "name": ""},
            {"objectName": "separator", "role": "menuSeparator"},
        ]
        issues = validate_metadata(elements)
        self.assertEqual([(issue.element, issue.code) for issue in issues],
                         [("bad", EMPTY_NAME)])

    def test_classic_style_metadata_matches_source_conventions(self):
        # Shapes mirror Accessible.name / objectName in the Classic Qt source.
        elements = [
            {"objectName": "canopyLauncher", "role": "button",
             "name": "Canopy penguin launcher"},
            {"objectName": "canopyDockTile", "role": "button",
             "name": "Files preview",
             "description": "Original demonstration artwork, not a working app launcher"},
            {"objectName": "canopyMenuFileOpen", "role": "menuItem",
             "name": "Open Files window"},
            {"objectName": "canopyMenuFileSeparator", "role": "menuSeparator"},
        ]
        self.assertEqual(self.codes(elements), [])

    def test_validation_is_pure_and_deterministic(self):
        elements = [{"role": "button", "name": ""}]
        self.assertEqual(validate_metadata(elements), validate_metadata(elements))
        self.assertEqual(elements, [{"role": "button", "name": ""}])


if __name__ == "__main__":
    unittest.main()
