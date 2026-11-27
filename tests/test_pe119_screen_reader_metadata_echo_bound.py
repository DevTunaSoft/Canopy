"""PE-119 regression tests: bounded, printable Issue projections.

PE-118 (F-1 HIGH) proved that caller-controlled ``objectName`` and ``role``
were echoed verbatim into ``Issue.element`` / ``Issue.message``: a 5000-char
role produced a 5018-char message. These tests pin the bounded printable
projection while preserving the existing validation semantics (codes,
interactive/informative classification and the ``elements[i]`` fallback).

The tests exercise pure metadata records only. They do not compile Qt, start
a screen reader, contact AT-SPI or claim Linux Mint desktop acceptance.
"""
import unittest

from canopy_features.accessibility import screen_reader_metadata as srm
from canopy_features.accessibility.screen_reader_metadata import (
    INVALID_ELEMENT,
    INVALID_ROLE,
    MISSING_LABEL,
    validate_metadata,
)


class BoundedProjectionTests(unittest.TestCase):
    def test_projection_constants_are_bounded_and_printable(self):
        self.assertIsInstance(srm.MAX_PROJECTION_CHARS, int)
        self.assertGreater(srm.MAX_PROJECTION_CHARS, 0)
        self.assertLess(srm.MAX_PROJECTION_CHARS, 200)
        self.assertEqual(srm.UNPRINTABLE_TOKEN, "?")
        self.assertTrue(all(ch.isprintable()
                            for ch in srm.PROJECTION_TRUNCATION_MARKER))
        self.assertTrue(srm.PROJECTION_TRUNCATION_MARKER)

    def test_huge_object_name_element_is_bounded(self):
        name = "x" * 5000
        issue = validate_metadata([{"objectName": name, "role": "button"}])[0]
        self.assertEqual(issue.code, MISSING_LABEL)
        self.assertNotIn(name, issue.element)
        self.assertTrue(issue.element.endswith(srm.PROJECTION_TRUNCATION_MARKER))
        self.assertLessEqual(
            len(issue.element),
            srm.MAX_PROJECTION_CHARS + len(srm.PROJECTION_TRUNCATION_MARKER),
        )

    def test_huge_unknown_role_message_is_bounded(self):
        role = "z" * 5000
        issue = validate_metadata([{"objectName": "btn", "role": role}])[0]
        self.assertEqual(issue.code, INVALID_ROLE)
        self.assertNotIn(role, issue.message)
        self.assertTrue(issue.message.endswith(srm.PROJECTION_TRUNCATION_MARKER))
        self.assertLessEqual(
            len(issue.message),
            len("unsupported role: ") + srm.MAX_PROJECTION_CHARS
            + len(srm.PROJECTION_TRUNCATION_MARKER),
        )

    def test_huge_control_character_role_is_bounded_and_printable(self):
        issue = validate_metadata([{"role": "\x00" * 5000}])[0]
        self.assertEqual(issue.code, INVALID_ROLE)
        self.assertNotIn("\x00", issue.message)
        self.assertTrue(all(ch.isprintable() for ch in issue.message))
        self.assertLessEqual(
            len(issue.message),
            len("unsupported role: ") + srm.MAX_PROJECTION_CHARS
            + len(srm.PROJECTION_TRUNCATION_MARKER),
        )

    def test_control_and_separator_characters_are_replaced(self):
        # Cc, Zl and Zp are nonprintable; none may survive into an Issue.
        name = "btn\x00\x1b\n\r\u2028\u2029"
        issue = validate_metadata([{"objectName": name, "role": "button"}])[0]
        self.assertEqual(issue.code, MISSING_LABEL)
        self.assertEqual(issue.element, "btn" + srm.UNPRINTABLE_TOKEN * 6)
        self.assertTrue(all(ch.isprintable() for ch in issue.element))

    def test_surrogate_private_use_and_noncharacter_are_replaced(self):
        # Cs, Co and Cn pass naive ASCII-only filters but are not printable.
        role = "w\ud800\ue000\ufffeidget"
        issue = validate_metadata([{"role": role}])[0]
        self.assertEqual(issue.code, INVALID_ROLE)
        self.assertEqual(issue.message,
                         "unsupported role: w" + srm.UNPRINTABLE_TOKEN * 3
                         + "idget")
        self.assertTrue(all(ch.isprintable() for ch in issue.message))

    def test_projection_preserves_printable_unicode(self):
        name = "caf\u00e9-\u5b89\u5168-\U0001f427"
        issue = validate_metadata([{"objectName": name, "role": "button"}])[0]
        self.assertEqual(issue.element, name)

    def test_wrong_type_object_name_uses_index_identifier(self):
        for value in (42, True, ["x"], b"bytes", {"k": "v"}, None):
            with self.subTest(value=value):
                issue = validate_metadata(
                    [{"objectName": value, "role": "button"}])[0]
                self.assertEqual(issue.code, MISSING_LABEL)
                self.assertEqual(issue.element, "elements[0]")

    def test_wrong_type_role_is_reported_with_fixed_message(self):
        for value in (42, True, ["button"], {"role": "button"}, None):
            with self.subTest(value=value):
                issue = validate_metadata([{"role": value}])[0]
                self.assertEqual(issue.code, INVALID_ROLE)
                self.assertEqual(issue.message,
                                 "role must be a non-empty string")
                self.assertNotIn(repr(value), issue.message)

    def test_wrong_type_name_and_description_do_not_echo_values(self):
        issues = validate_metadata([{"role": "button", "name": ["secret"],
                                     "description": {"secret": "secret"}}])
        self.assertEqual([issue.code for issue in issues],
                         ["invalid-name", "invalid-description"])
        for issue in issues:
            self.assertNotIn("secret", issue.message)

    def test_classification_semantics_are_unchanged_by_projection(self):
        elements = [
            {"objectName": "okButton", "role": "button", "name": "Open"},
            {"objectName": "x" * 5000, "role": "button"},
            {"objectName": "img", "role": "image", "ignored": True},
            {"objectName": "clock", "role": "staticText"},
            "not a record",
        ]
        issues = validate_metadata(elements)
        self.assertEqual([issue.code for issue in issues],
                         [MISSING_LABEL, MISSING_LABEL, INVALID_ELEMENT])
        self.assertEqual(issues[0].element,
                         "x" * srm.MAX_PROJECTION_CHARS
                         + srm.PROJECTION_TRUNCATION_MARKER)
        self.assertEqual(issues[1].element, "clock")
        self.assertEqual(issues[2].element, "elements[4]")

    def test_validation_stays_pure_with_hostile_inputs(self):
        elements = [{"objectName": "\x00" * 5000, "role": "z" * 5000}]
        before = [dict(elements[0])]
        first = validate_metadata(elements)
        self.assertEqual(first, validate_metadata(elements))
        self.assertEqual(elements, before)
        self.assertTrue(all(ch.isprintable()
                            for issue in first
                            for ch in issue.element + issue.message))


if __name__ == "__main__":
    unittest.main()
