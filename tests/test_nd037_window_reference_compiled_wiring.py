"""ND-037: source contracts for compiled Classic window-reference wiring.

The compiled adapter ``WindowActivationState`` is already constructed by the
shell and fed trusted host snapshots through ``applySnapshot()``. This test
pins the ND-037 extension at that same boundary: PR #688's bounded,
generation-checked window references are consumed fail-closed, with no visual
change, no new host topic, no timer, no polling and no actuation.

These are source-contract tests only. They do not claim compiled Qt behavior or
Mint acceptance; compiled evidence is produced separately by the offscreen
harness recorded in the PR body.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from canopy_features.windows import window_state_capabilities as wsc

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
HEADER = CLASSIC / "WindowActivationState.h"
SOURCE = CLASSIC / "WindowActivationState.cpp"
ADAPTER = CLASSIC / "WindowActivationIndicators.qml"
CMAKE = CLASSIC / "CMakeLists.txt"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


class ND037CompiledWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = _text(HEADER)
        cls.source = _text(SOURCE)
        cls.adapter = _text(ADAPTER)
        cls.cmake = _text(CMAKE)

    def test_bounds_mirror_merged_pr688_contract(self):
        self.assertEqual(
            re.search(r"kMaxLiveWindows\s*=\s*(\d+)", self.header).group(1),
            str(wsc.MAX_LIVE_WINDOWS))
        self.assertEqual(
            re.search(r"kMaxSerial\s*=\s*(\d+)", self.header).group(1),
            str(wsc.MAX_SERIAL))
        for status in (wsc.REF_LIVE, wsc.REF_STALE, wsc.REF_UNKNOWN,
                       wsc.REF_UNAUTHORIZED):
            self.assertIn('QStringLiteral("%s")' % status, self.source)

    def test_reference_facts_enter_at_existing_snapshot_boundary(self):
        source = self.source
        for marker in (
                "bool WindowActivationState::applySnapshot(const QVariantMap &snapshot)",
                'snapshot.contains(QStringLiteral("windowRefs"))',
                "bool WindowActivationState::parseWindowRefs(",
                'QStringLiteral("window_id")', 'QStringLiteral("serial")',
                'QStringLiteral("owner")', "item.size() != keys.size()",
                "live.contains(windowId)",
                "seenSerial.value(windowId, 0) > serial",
                "QString WindowActivationState::classifyReference("):
            self.assertIn(marker, source)
        self.assertIn('snapshot.contains(QStringLiteral("windowRefs"))', source)

    def test_focus_reference_is_validated_before_any_indicator(self):
        source = self.source
        self.assertIn(
            "classifyReference(live, seenSerial, windowId, serial,\n"
            "                                     focusApp) != QStringLiteral(\"LIVE\")",
            source)
        fail_closed = source.index(
            "clear();  // stale, unknown or forged refs clear every indicator")
        commit = source.index("m_liveWindows = live;")
        self.assertLess(fail_closed, commit)
        self.assertLess(source.index("focusGranted = statusValue =="), commit)
        self.assertIn("m_hasRegistry = hasRegistry;", source)
        self.assertIn("m_liveWindows.clear();", source)
        self.assertIn("// m_seenSerial is a bounded monotonic generation history",
                      source)

    def test_decision_only_gate_never_actuates(self):
        source = self.source
        self.assertIn("QString WindowActivationState::resolveActivationWithReference(",
                      source)
        self.assertIn(
            "classifyReference(m_liveWindows, m_seenSerial, windowId, serial,\n"
            "                                 owner) != QStringLiteral(\"LIVE\")",
            source)
        self.assertIn("return resolveActivation(appId, originApp);", source)
        self.assertIn("QString WindowActivationState::referenceStatus(", source)
        self.assertIn("int WindowActivationState::liveWindowCount() const", source)
        for forbidden in ("QProcess", "QTimer", "QNetwork", "QSocket", "app.start",
                          "system(", "QDesktopServices"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        # PR #707 remains an open draft and is not a dependency of this wiring.
        self.assertNotIn("window_activation_contract", source)
        self.assertNotIn("window_activation_contract", self.header)

    def test_qml_face_stays_nonvisual(self):
        adapter = self.adapter
        for marker in (
                "readonly property int liveWindowCount",
                "function referenceStatus(windowId, serial, owner)",
                "function activationForWindow(appId, originApp, windowId, serial, owner)",
                'return "UNVALIDATED"', 'return "REJECT"',
                "resolveActivationWithReference("):
            with self.subTest(marker=marker):
                self.assertIn(marker, adapter)
        for forbidden in ("Rectangle", "Image", "Timer", "Animation", "Item {",
                          ".png", ".svg", "QProcess", "QQmlComponent", "width:",
                          "height:", "anchors."):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, adapter)

    def test_compiled_shell_registration_is_unchanged(self):
        self.assertIn(
            "qt_add_executable(canopy-classic-spike main.cpp LauncherModel.cpp "
            "LauncherModel.h WindowActivationState.cpp WindowActivationState.h",
            self.cmake)
        self.assertIn("ShellMenuPopupSet.qml WindowActivationIndicators.qml",
                      self.cmake)


if __name__ == "__main__":
    unittest.main()
