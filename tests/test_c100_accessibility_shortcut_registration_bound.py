"""Registration iterable consumption is bounded before the domain check."""
from __future__ import annotations

import unittest

from canopy_features.accessibility.shortcut_conflict_check import (
    MAX_REGISTRATIONS, ShortcutConflictError, detect_shortcut_conflicts)


class RegistrationConsumptionBoundTests(unittest.TestCase):
    def test_generator_stops_near_documented_limit(self):
        consumed = []

        def oversized():
            for index in range(MAX_REGISTRATIONS + 10):
                consumed.append(index)
                yield ("action-%d" % index, "Ctrl+A")

        with self.assertRaises(ShortcutConflictError):
            detect_shortcut_conflicts(shell=oversized())
        self.assertLessEqual(len(consumed), MAX_REGISTRATIONS + 1)

    def test_exactly_at_limit_is_still_valid(self):
        registrations = [("action-%d" % i, "Ctrl+A")
                         for i in range(MAX_REGISTRATIONS)]
        report = detect_shortcut_conflicts(shell=registrations)
        self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
