"""Deterministic source/contract tests for the Classic window-activation adapter.

These tests guard the cross-language contract between the new C++/QML component
and the already-tested pure Python modules. They never claim compiled Qt
behaviour: the compiled vectors/QML self-test is a separate standalone target
documented in docs/classic-window-activation-workstream-6.md.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from canopy_features.dock import click_intents, dock_running_indicators
from canopy_features.windows import focus_intents, window_state_capabilities

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
ADAPTER_DIR = CLASSIC / "window_activation"
HEADER = CLASSIC / "WindowActivationState.h"
SOURCE = CLASSIC / "WindowActivationState.cpp"
QML_ADAPTER = CLASSIC / "WindowActivationIndicators.qml"
QML_TEST = ADAPTER_DIR / "WindowActivationSelfTest.qml"
VECTORS = ADAPTER_DIR / "contract_vectors.json"
STANDALONE_CMAKE = ADAPTER_DIR / "CMakeLists.txt"


class WindowActivationContractTests(unittest.TestCase):
    def test_component_files_exist(self):
        for path in (HEADER, SOURCE, QML_ADAPTER, QML_TEST, VECTORS,
                     STANDALONE_CMAKE):
            with self.subTest(path=str(path)):
                self.assertTrue(path.is_file(), path)

    def test_approved_dock_names_match_python_allowlist(self):
        source = SOURCE.read_text(encoding="utf-8")
        block = re.search(r"approvedDockNames\(\).*?return \{(.*?)\};",
                          source, re.DOTALL)
        self.assertIsNotNone(block, "missing approvedDockNames allowlist")
        assert block is not None
        names = set(re.findall(r'QStringLiteral\("([^"]+)"\)', block.group(1)))
        self.assertEqual(names, set(click_intents.APPROVED_DOCK_NAMES))

    def test_bounds_match_python_contracts(self):
        header = HEADER.read_text(encoding="utf-8")
        constants = dict(re.findall(
            r"static constexpr int (k\w+) = (\d+);", header))
        self.assertEqual(int(constants["kMaxApps"]),
                         dock_running_indicators.MAX_APPS)
        self.assertEqual(int(constants["kMaxPidsPerApp"]),
                         dock_running_indicators.MAX_PIDS_PER_APP)
        self.assertEqual(int(constants["kMaxPid"]),
                         dock_running_indicators.MAX_PID)
        self.assertEqual(int(constants["kMaxGrants"]), focus_intents.MAX_GRANTS)
        self.assertEqual(int(constants["kSchema"]), 1)

    def test_focus_statuses_and_backends_match_python_contracts(self):
        source = SOURCE.read_text(encoding="utf-8")
        focus_block = re.search(r"focusStatuses\(\).*?return \{(.*?)\};",
                                source, re.DOTALL)
        self.assertIsNotNone(focus_block)
        assert focus_block is not None
        statuses = set(re.findall(r'QStringLiteral\("([^"]+)"\)',
                                  focus_block.group(1)))
        self.assertEqual(statuses, {
            focus_intents.GRANTED, focus_intents.DENIED,
            focus_intents.STALE_TARGET, focus_intents.UNKNOWN_TARGET,
            focus_intents.ACTIVATION_FAILED})
        backend_block = re.search(r"knownBackends\(\).*?return \{(.*?)\};",
                                  source, re.DOTALL)
        self.assertIsNotNone(backend_block)
        assert backend_block is not None
        backends = set(re.findall(r'QStringLiteral\("([^"]+)"\)',
                                  backend_block.group(1)))
        self.assertEqual(backends,
                         set(window_state_capabilities.KNOWN_BACKENDS))

    def test_vectors_are_well_formed_and_cover_fail_closed_paths(self):
        data = json.loads(VECTORS.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        cases = data["cases"]
        self.assertGreaterEqual(len(cases), 14)
        names = [case["name"] for case in cases]
        self.assertEqual(len(names), len(set(names)))
        for required in (
                "empty_snapshot_untrusted", "fresh_valid_indicators_and_intents",
                "stale_sequence_ignored", "duplicate_pid_clears_all_indicators",
                "unknown_backend_fails_closed", "launcher_disabled_returns_ignore",
                "cross_app_focus_requires_explicit_grant"):
            self.assertIn(required, names)
        for case in cases:
            expected = case["expected"]
            for key in ("applied", "trusted", "status", "sequence",
                        "running", "active", "resolutions"):
                self.assertIn(key, case["expected"], case["name"])
            self.assertIs(type(expected["applied"]), bool)
            self.assertIs(type(expected["trusted"]), bool)
            for intent in expected["resolutions"].values():
                self.assertIn(intent, {"FOCUS", "LAUNCH", "REJECT", "IGNORE"})
        by_name = {case["name"]: case for case in cases}
        self.assertFalse(by_name["duplicate_pid_clears_all_indicators"]
                         ["expected"]["trusted"])
        self.assertEqual(by_name["launcher_disabled_returns_ignore"]
                         ["expected"]["resolutions"]["Files|Canopy"], "IGNORE")

    def test_qml_is_nonvisual_and_fails_closed(self):
        adapter = QML_ADAPTER.read_text(encoding="utf-8")
        selftest = QML_TEST.read_text(encoding="utf-8")
        for text in (adapter, selftest):
            self.assertTrue(text.lstrip().startswith("//"))
            self.assertIn("import QtQml", text)
            self.assertIn("QtObject {", text)
            for forbidden in ("Rectangle", "Image", "Timer", "Animation",
                              ".png", ".svg", "QProcess", "QQmlComponent"):
                self.assertNotIn(forbidden, text)
        self.assertIn('return "REJECT"', adapter)
        self.assertIn("indicatorsAvailable", adapter)
        self.assertIn("checkUntrusted", selftest)
        self.assertIn("checkReady", selftest)
        self.assertIn("checkCleared", selftest)

    def test_component_performs_no_host_observation_or_actuation(self):
        source = SOURCE.read_text(encoding="utf-8")
        for forbidden in ("QProcess", "system(", "popen", "xdotool", "wmctrl",
                          "QTimer", "QThread", "QFile", "QNetwork",
                          "QGuiApplication", "QDBus"):
            self.assertNotIn(forbidden, source)

    def test_standalone_build_does_not_touch_owned_cmake_registration(self):
        cmake = STANDALONE_CMAKE.read_text(encoding="utf-8")
        self.assertIn("find_package(Qt6 REQUIRED COMPONENTS Core Qml)", cmake)
        self.assertIn("../WindowActivationState.cpp", cmake)
        self.assertNotIn("ShellMenuPopupSet.qml", cmake)
        self.assertNotIn("DockTile.qml", cmake)


if __name__ == "__main__":
    unittest.main()
