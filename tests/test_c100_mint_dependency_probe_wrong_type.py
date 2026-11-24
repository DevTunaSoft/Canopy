"""Regression: hostile-but-bounded wrong-type dependency-probe inputs.

These are pure, offline evaluations with caller-supplied data. They use only
finite inputs and never touch a host, a package manager or a network.
"""
import unittest

from canopy_features.mint import dependency_probe as probe

ALL_TOOLS = {name: True for name in probe.REQUIRED_TOOLS}


class HostileWrongTypeTests(unittest.TestCase):
    def test_wrong_type_available_mapping_fails_closed(self):
        # A bounded version label (or another non-mapping container) placed in
        # the availability slot used to leak a raw AttributeError from .get(),
        # or be silently coerced to an empty mapping.
        bad_inputs = (
            "6.4.2",
            b"6.4.2",
            ["cmake", "ninja"],
            ("cmake",),
            7,
            {"cmake"},
            frozenset({"cmake"}),
            [],
            "",
        )
        for bad in bad_inputs:
            with self.subTest(kind=type(bad).__name__):
                with self.assertRaises(ValueError) as ctx:
                    probe.assess_dependencies(available=bad, qt_version="6.4.2")
                self.assertEqual(type(ctx.exception).__name__,
                                 "DependencyProbeError")
                self.assertNotIn("6.4.2", str(ctx.exception))

    def test_hostile_str_subclass_version_label_cannot_claim_dependency_safe(self):
        # isinstance(x, str) accepts a subclass that overrides strip(); the
        # overridden method returned a valid label and produced a false
        # qt_version_sufficient=True / status=COMPLETE for a non-version input.
        class HostileLabel(str):
            def strip(self, *args):
                return "6.4.2"

        report = probe.assess_dependencies(
            available=ALL_TOOLS, qt_version=HostileLabel("not-a-version"))
        self.assertFalse(report["qt_version_sufficient"])
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["detected_qt_version"], "unavailable-or-invalid")
        self.assertTrue(report["blockers"])

    def test_valid_inputs_still_report_complete(self):
        report = probe.assess_dependencies(available=ALL_TOOLS, qt_version="6.4.2")
        self.assertEqual(report["status"], "COMPLETE")
        self.assertTrue(report["qt_version_sufficient"])
        self.assertEqual(report["detected_qt_version"], "6.4.2")


if __name__ == "__main__":
    unittest.main()
