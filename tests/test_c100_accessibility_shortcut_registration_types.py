"""Wrong-type registration inputs must fail with the documented domain error."""
from __future__ import annotations

import unittest

from canopy_features.accessibility.shortcut_conflict_check import (
    MAX_REGISTRATIONS, ShortcutConflictError, detect_shortcut_conflicts)


class ShortcutRegistrationTypeTests(unittest.TestCase):
    def test_none_registration_source_is_rejected(self):
        with self.assertRaises(ShortcutConflictError):
            detect_shortcut_conflicts(shell=None)

    def test_scalar_registration_sources_are_rejected(self):
        for value in (7, 1.5, True, object()):
            with self.subTest(value=type(value).__name__), \
                    self.assertRaises(ShortcutConflictError):
                detect_shortcut_conflicts(user=value)

    def test_string_and_bytes_are_still_rejected_with_domain_error(self):
        for value in ("Ctrl+A", b"Ctrl+A"):
            with self.subTest(value=value), self.assertRaises(ShortcutConflictError):
                detect_shortcut_conflicts(shell=value)

    def test_valid_pair_forms_still_work(self):
        report = detect_shortcut_conflicts(
            shell=[("open", "Ctrl+O")], user=(("save", "Ctrl+S"),))
        self.assertTrue(report.ok)

    def test_oversized_generator_is_bounded(self):
        def oversized():
            for index in range(MAX_REGISTRATIONS + 2):
                yield ("action-%d" % index, "Ctrl+A")
        with self.assertRaises(ShortcutConflictError):
            detect_shortcut_conflicts(shell=oversized())

    def test_bound_is_consistent_with_documented_limit(self):
        self.assertEqual(MAX_REGISTRATIONS, 256)


if __name__ == "__main__":
    unittest.main()
