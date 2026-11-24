"""Offline unit tests for the installer Mint dependency contract.

These are pure evaluations with caller-supplied data. They do not query a host,
compile Qt, or test a real Linux Mint guest.
"""
import inspect
from pathlib import Path
import unittest

from canopy_features.installer import mint_dependency_contract as contract


ROOT = Path(__file__).resolve().parents[1]


def installed(base=None, **versions):
    """Build an installed-package mapping, optionally from a base mapping."""
    result = dict(base or {})
    result.update(versions)
    return result


class MintDependencyContractTests(unittest.TestCase):
    def setUp(self):
        self.satisfied = installed(cmake="3.28.3", **{
            "qt6-core": "6.4.2", "qt6-declarative": "6.4.2",
        })

    def test_stable_release_with_matching_versions_is_satisfied(self):
        report = contract.evaluate(self.satisfied, "22.3")
        self.assertEqual(report.status, "SATISFIED")
        self.assertTrue(report.ok)
        self.assertTrue(report.stable_release)
        self.assertEqual(report.mint_version, "22.3")
        self.assertTrue(report.findings)
        self.assertTrue(all(f.status == "ok" for f in report.findings))

    def test_version_mismatch_is_reported_and_fails_closed(self):
        # cmake 3.18 is below the 3.21 minimum declared by the Qt CMake file.
        report = contract.evaluate(installed(self.satisfied, cmake="3.18.4"), "22")
        self.assertEqual(report.status, "UNSATISFIED")
        self.assertFalse(report.ok)
        cmake = next(f for f in report.findings if f.package == "cmake")
        self.assertEqual(cmake.status, "below_minimum")
        self.assertEqual(cmake.installed, "3.18.4")
        self.assertEqual(cmake.required, "3.21")
        self.assertIn("below required minimum", cmake.detail)

    def test_missing_required_package_is_unknown_and_fails(self):
        partial = installed(cmake="3.28.3", **{"qt6-core": "6.4.2"})
        report = contract.evaluate(partial, "21.3")
        self.assertEqual(report.status, "UNSATISFIED")
        missing = [f for f in report.findings if f.status == "not_installed"]
        self.assertEqual([f.package for f in missing], ["qt6-declarative"])
        self.assertIsNone(missing[0].installed)

    def test_unrelated_installed_packages_are_ignored(self):
        noisy = installed(self.satisfied, **{
            "unknown-extra": "9.9.9", "some-secret-token": "not-a-version",
        })
        report = contract.evaluate(noisy, "22.3")
        self.assertEqual(report.status, "SATISFIED")
        self.assertNotIn("unknown-extra", [f.package for f in report.findings])

    def test_unsupported_mint_release_fails_without_reading_packages(self):
        for release in ("24.04", "devel", "", None, 22):
            with self.subTest(release=release):
                report = contract.evaluate(self.satisfied, release)
                self.assertEqual(report.status, "UNSUPPORTED_RELEASE")
                self.assertFalse(report.stable_release)
                self.assertFalse(report.ok)
                self.assertEqual(report.findings, ())

    def test_unparseable_installed_version_fails_closed(self):
        report = contract.evaluate(installed(self.satisfied, **{
            "qt6-core": "six-dot-four",
        }), "22.3")
        self.assertEqual(report.status, "UNSATISFIED")
        finding = next(f for f in report.findings if f.package == "qt6-core")
        self.assertEqual(finding.status, "invalid_version")

    def test_version_parser_ignores_packaging_suffixes_and_numeric_order(self):
        self.assertEqual(contract.parse_version("6.4.2-0ubuntu1"), (6, 4, 2))
        self.assertEqual(contract.parse_version("6.4+dfsg"), (6, 4))
        self.assertIsNone(contract.parse_version(""))
        self.assertIsNone(contract.parse_version("6.x"))
        self.assertIsNone(contract.parse_version(None))
        self.assertEqual(contract._compare((6, 4), (6, 4, 0)), 0)
        self.assertGreater(contract._compare((6, 10), (6, 9)), 0)
        self.assertLess(contract._compare((3, 21), (3, 21, 1)), 0)

    def test_equal_minimum_boundary_is_accepted(self):
        exact = installed(cmake="3.21", **{
            "qt6-core": "6.4", "qt6-declarative": "6.4.0",
        })
        self.assertEqual(contract.evaluate(exact, "22.3").status, "SATISFIED")

    def test_evaluation_is_pure_bounded_and_does_not_mutate_inputs(self):
        snapshot = dict(self.satisfied)
        first = contract.evaluate(self.satisfied, "22.3")
        second = contract.evaluate(self.satisfied, "22.3")
        self.assertEqual(first, second)
        self.assertEqual(self.satisfied, snapshot)
        # A large installed mapping does not change the bounded result.
        huge = installed(self.satisfied, **{
            "extra-%d" % i: "1.0" for i in range(200)
        })
        self.assertEqual(contract.evaluate(huge, "22.3"), first)

    def test_module_has_no_host_probe_or_polling_imports(self):
        source = inspect.getsource(contract)
        for forbidden in ("import subprocess", "import socket", "import os",
                          "import requests", "import urllib", "time.sleep",
                          "threading"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, source)

    def test_overlong_numeric_version_labels_fail_closed_without_raw_exception(self):
        # A bounded 5000-digit label exceeds CPython's int() conversion limit.
        # The documented fail-closed path must yield a finding, never a raw
        # ValueError; this applies to installed labels and declared minimums.
        huge = "9" * 5000
        self.assertIsNone(contract.parse_version(huge))
        report = contract.evaluate(installed(self.satisfied, **{
            "qt6-core": huge,
        }), "22.3")
        self.assertEqual(report.status, "UNSATISFIED")
        self.assertFalse(report.ok)
        finding = next(f for f in report.findings if f.package == "qt6-core")
        self.assertEqual(finding.status, "invalid_version")
        self.assertEqual(finding.installed, huge)
        min_report = contract.evaluate(
            self.satisfied, "22.3", constraints=(("cmake", huge),))
        self.assertEqual(min_report.status, "UNSATISFIED")
        self.assertFalse(min_report.ok)
        min_finding = next(f for f in min_report.findings if f.package == "cmake")
        self.assertEqual(min_finding.status, "invalid_constraint")
        self.assertEqual(min_finding.required, huge)

    def test_contract_minimums_match_compiled_qt_source_contract(self):
        text = (ROOT / "prototype" / "classic" / "CMakeLists.txt").read_text(
            encoding="utf-8")
        self.assertIn("cmake_minimum_required(VERSION 3.21)", text)
        self.assertIn("find_package(Qt6 6.4 REQUIRED", text)
        minimums = dict(contract.CANOPY_CONSTRAINTS)
        self.assertEqual(minimums["cmake"], "3.21")
        self.assertEqual(minimums["qt6-core"], "6.4")
        self.assertEqual(minimums["qt6-declarative"], "6.4")


if __name__ == "__main__":
    unittest.main()
