"""Offline tests for the read-only Classic Qt dependency report."""
import json
from pathlib import Path
import unittest

from canopy_features.mint import dependency_probe as probe
from tools.mint_guest_preflight import NEEDED as PREFLIGHT_NEEDED

ALL_TOOLS = {name: True for name in probe.REQUIRED_TOOLS}


class DependencyProbeTests(unittest.TestCase):
    def report(self, **kwargs):
        return probe.assess_dependencies(
            available=kwargs.get("available", ALL_TOOLS),
            qt_version=kwargs.get("qt_version", "6.4.2"),
            requested_packages=kwargs.get("requested_packages"),
        )

    def test_report_lists_required_qt_packages_without_installing(self):
        report = self.report()
        names = [entry["name"] for entry in report["qt_packages"]]
        self.assertIn("qt6-base-dev", names)
        self.assertIn("qt6-declarative-dev", names)
        self.assertIn("libqt6svg6", names)
        self.assertTrue(report["probe_only"])
        self.assertEqual(report["installation"], "NOT_ATTEMPTED")
        self.assertEqual(report["status"], "COMPLETE")
        serialized = json.dumps(report)
        for token in ("apt-get", "apt install", "pip install", "subprocess", "Popen"):
            self.assertNotIn(token, serialized)

    def test_tool_list_is_reused_from_existing_preflight(self):
        self.assertEqual(list(probe.REQUIRED_TOOLS), list(PREFLIGHT_NEEDED))

    def test_each_missing_tool_is_reported(self):
        for tool in probe.REQUIRED_TOOLS:
            with self.subTest(tool=tool):
                available = dict(ALL_TOOLS)
                available[tool] = False
                report = self.report(available=available)
                self.assertEqual(report["status"], "INCOMPLETE")
                self.assertEqual(report["missing_tools"], [tool])
                self.assertFalse(report["required_tools"][tool])
                self.assertTrue(any(tool in blocker for blocker in report["blockers"]))

    def test_no_tools_available_reports_all_missing(self):
        report = self.report(available={})
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["missing_tools"], list(probe.REQUIRED_TOOLS))

    def test_old_qt_is_reported_as_insufficient(self):
        report = self.report(qt_version="5.15.2")
        self.assertFalse(report["qt_version_sufficient"])
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["detected_qt_version"], "5.15.2")
        self.assertTrue(any("6.4" in blocker for blocker in report["blockers"]))

    def test_missing_qt_is_reported_as_insufficient(self):
        report = self.report(qt_version=None)
        self.assertFalse(report["qt_version_sufficient"])
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["detected_qt_version"], "unavailable-or-invalid")

    def test_qt_version_acceptance_boundaries(self):
        for value in ("6.4", "6.4.0", "6.4.2", "6.10.1"):
            with self.subTest(valid=value):
                self.assertTrue(self.report(qt_version=value)["qt_version_sufficient"])
        for value in ("6.3.9", "5.15"):
            with self.subTest(old=value):
                report = self.report(qt_version=value)
                self.assertFalse(report["qt_version_sufficient"])
                self.assertEqual(report["detected_qt_version"], value)
        for value in ("6", "garbage; rm -rf /", "9" * 30, None, 6.4):
            with self.subTest(invalid=value):
                report = self.report(qt_version=value)
                self.assertFalse(report["qt_version_sufficient"])
                self.assertEqual(report["detected_qt_version"], "unavailable-or-invalid")

    def test_untrusted_package_names_are_rejected(self):
        hostile = [
            "qt6-base-dev; rm -rf /",
            "../../etc/passwd",
            "QT6-BASE-DEV",
            "apt-get remove systemd",
            "qml6-module-evil&&curl http://example.invalid",
            "",
            None,
            42,
        ]
        accepted, rejected = probe.filter_trusted_packages(["cmake"] + hostile)
        self.assertEqual(accepted, ["cmake"])
        self.assertEqual(rejected, len(hostile))

        report = self.report(requested_packages=["qt6-declarative-dev"] + hostile)
        self.assertEqual(report["resolved_requested_packages"], ["qt6-declarative-dev"])
        self.assertEqual(report["untrusted_names_rejected"], len(hostile))
        serialized = json.dumps(report)
        for token in ("rm -rf", "etc/passwd", "curl", "apt-get"):
            self.assertNotIn(token, serialized)

    def test_trusted_requested_names_are_deduplicated(self):
        accepted, rejected = probe.filter_trusted_packages(
            ["cmake", "cmake", "libqt6svg6"]
        )
        self.assertEqual(accepted, ["cmake", "libqt6svg6"])
        self.assertEqual(rejected, 0)

    def test_module_contains_no_installation_mechanism(self):
        source = Path(probe.__file__).read_text(encoding="utf-8")
        for token in ("subprocess", "os.system", "Popen", "apt-get",
                      "apt install", "pip install"):
            self.assertNotIn(token, source)

    def test_collect_reuses_preflight_without_installing(self):
        report = probe.collect()
        self.assertTrue(report["probe_only"])
        self.assertEqual(report["installation"], "NOT_ATTEMPTED")
        self.assertIn(report["status"], ("COMPLETE", "INCOMPLETE"))


if __name__ == "__main__":
    unittest.main()
