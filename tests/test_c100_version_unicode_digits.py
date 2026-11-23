"""Regression: offline version parsers fail closed on non-ASCII digit inputs.

Both parsers document that malformed values return ``None`` and that callers
receive a bounded report rather than an exception. Their ``isdigit()``/``int()``
combination accepted Unicode digit characters that ``int()`` either rejects
(superscript digits raise ``ValueError``) or silently coerces (Arabic-Indic and
Devanagari digits). Both outcomes escape the documented fail-closed path.

These are pure in-memory checks: no Qt, host query, process, network, visual
asset, geometry, color or typography is involved.
"""
import unittest

from canopy_features.installer import mint_dependency_contract as contract
from canopy_features.mint import qt_plugin_discovery as discovery


SUPERSCRIPT_TWO = "\u00b2"      # isdigit() True, isdecimal() False -> int() raises
ARABIC_INDI_THREE = "\u0663"   # isdigit() True, int() silently coerces to 3
DEVANAGARI_FOUR = "\u0968"     # isdigit() True, int() silently coerces to 4


class MintDependencyContractUnicodeDigitTests(unittest.TestCase):
    def test_parse_version_rejects_unicode_digits(self):
        for bad in (SUPERSCRIPT_TWO, "6." + SUPERSCRIPT_TWO,
                    ARABIC_INDI_THREE, "6." + ARABIC_INDI_THREE,
                    DEVANAGARI_FOUR):
            with self.subTest(bad=bad):
                self.assertIsNone(contract.parse_version(bad))

    def test_evaluate_unknown_installed_version_fails_closed(self):
        installed = {
            "cmake": "3.21",
            "qt6-core": SUPERSCRIPT_TWO,
            "qt6-declarative": "6.4",
        }
        report = contract.evaluate(installed, "22")
        self.assertEqual(report.status, "UNSATISFIED")
        self.assertFalse(report.ok)
        core = [f for f in report.findings if f.package == "qt6-core"]
        self.assertEqual(len(core), 1)
        self.assertEqual(core[0].status, "invalid_version")
        self.assertEqual(core[0].installed, SUPERSCRIPT_TWO)

    def test_evaluate_non_ascii_digits_are_not_silently_coerced(self):
        installed = {
            "cmake": "3.21",
            "qt6-core": "6." + ARABIC_INDI_THREE,
            "qt6-declarative": "6.4",
        }
        report = contract.evaluate(installed, "22")
        self.assertEqual(report.status, "UNSATISFIED")
        core = [f for f in report.findings if f.package == "qt6-core"]
        self.assertEqual(core[0].status, "invalid_version")

    def test_valid_ascii_versions_still_parse_and_satisfy(self):
        self.assertEqual(contract.parse_version("6.4.2-0ubuntu1"), (6, 4, 2))
        installed = {
            "cmake": "3.21",
            "qt6-core": "6.4",
            "qt6-declarative": "6.4",
        }
        self.assertTrue(contract.evaluate(installed, "22").ok)


class QtPluginDiscoveryUnicodeDigitTests(unittest.TestCase):
    def test_parse_version_rejects_unicode_digits(self):
        for bad in (SUPERSCRIPT_TWO, "6." + SUPERSCRIPT_TWO,
                    ARABIC_INDI_THREE, "6." + ARABIC_INDI_THREE,
                    DEVANAGARI_FOUR):
            with self.subTest(bad=bad):
                self.assertIsNone(discovery.parse_version(bad))

    def test_assess_unknown_qt_version_returns_blocked_report(self):
        report = discovery.assess(
            ["qsvg.so"], ["qxcb.so"], qt_version=SUPERSCRIPT_TWO,
            session="x11",
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["qt_version_compatible"])
        self.assertIsNone(report["qt_version"])
        self.assertTrue(any("unparseable" in b for b in report["blockers"]))

    def test_assess_non_ascii_digits_are_not_silently_coerced(self):
        report = discovery.assess(
            ["qsvg.so"], ["qxcb.so"],
            qt_version="6." + ARABIC_INDI_THREE, session="x11",
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["qt_version_compatible"])
        self.assertIsNone(report["qt_version"])

    def test_valid_ascii_version_still_parses_and_is_compatible(self):
        self.assertEqual(discovery.parse_version("6.4.2"), (6, 4, 2))
        report = discovery.assess(
            ["qsvg.so"], ["qxcb.so"], qt_version="6.4.2", session="x11",
        )
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["qt_version"], "6.4.2")


if __name__ == "__main__":
    unittest.main()
