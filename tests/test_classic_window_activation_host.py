"""Source contracts for the compiled Classic window-activation host wiring.

These tests guard the shell integration of the PR #573 state component. They
never claim compiled Qt behaviour: the compiled host self-test is exercised by
``--self-test-window-activation-fixture`` in the Classic Qt build.
"""
from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
MAIN = CLASSIC / "main.cpp"
CMAKE = CLASSIC / "CMakeLists.txt"
DOCK = CLASSIC / "DockTile.qml"
HEADER = CLASSIC / "WindowActivationState.h"
SOURCE = CLASSIC / "WindowActivationState.cpp"
ADAPTER = CLASSIC / "WindowActivationIndicators.qml"

# PR #573 state component, byte-resynced for the ND-037 compiled wiring at
# integration tip 7535c0e9 (test-only pin sync; no visual source edit).
# Digests are over LF-normalized whole-file bytes.
PR573_HEADER_SHA = "082ae9933f60bfeb43b784e29c437cbb0ff2d6616709f34c60f7484bb79bf2eb"
PR573_SOURCE_SHA = "834fd09e6308ab819ae1c4e041ada7962543dab644a2d0068b7cf9004b21e0a9"


class ClassicWindowActivationHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = MAIN.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.dock = DOCK.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")

    def test_reuses_tested_pr573_state_component_verbatim(self):
        for path, expected in ((HEADER, PR573_HEADER_SHA),
                               (SOURCE, PR573_SOURCE_SHA)):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
                normalized = path.read_text(encoding="utf-8").replace(
                    chr(13) + chr(10), "\n").encode("utf-8")
                self.assertEqual(hashlib.sha256(normalized).hexdigest(),
                                 expected)

    def test_shell_build_registers_component_and_qml_adapter(self):
        self.assertIn(
            "qt_add_executable(canopy-classic-spike main.cpp "
            "LauncherModel.cpp LauncherModel.h WindowActivationState.cpp "
            "WindowActivationState.h "
            "RoundedDockIconProvider.cpp RoundedDockIconProvider.h "
            "SystemAppLauncher.cpp SystemAppLauncher.h)", self.cmake)
        self.assertIn("ShellMenuPopupSet.qml WindowActivationIndicators.qml",
                      self.cmake)
        self.assertIn('qrc:/Canopy/Classic/WindowActivationIndicators.qml',
                      self.cpp)

    def test_host_supplies_snapshot_and_exposes_adapter_before_ui(self):
        cpp = self.cpp
        for marker in (
                "WindowActivationState activationState;",
                "hostActivationSnapshot(systemLauncher, activationBackend, 1)",
                'QStringLiteral("--window-activation-snapshot")',
                "loadActivationSnapshotFile(",
                'QStringLiteral("canopyWindowActivationState")',
                'QStringLiteral("canopyWindowActivation")',
                "activationComponent.create()",
                "WINDOW_ACTIVATION_ADAPTER_LOADED",
                "CANOPY_ACTIVATION_SNAPSHOT_REJECTED_FAIL_CLOSED",
                "CANOPY_ACTIVATION_BACKEND_UNKNOWN_FAIL_CLOSED"):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)
        self.assertLess(cpp.index('setContextProperty(\n'
                                  '        QStringLiteral("canopyWindowActivationState")'),
                        cpp.index("activationComponent.create()"))

    def test_no_process_or_window_telemetry_is_invented(self):
        cpp = self.cpp
        self.assertIn('snapshot.insert(QStringLiteral("owners"), QVariantList())',
                      cpp)
        self.assertIn('snapshot.insert(QStringLiteral("grants"), QVariantList())',
                      cpp)
        self.assertNotIn("QProcess", cpp)
        self.assertIn("No process or\n// window telemetry is invented", cpp)

    def test_all_approved_dock_tiles_use_the_intent_gate(self):
        cpp = self.cpp
        for marker in (
                "class FilesDockLaunchBridge final : public QObject",
                "class BrowserDockLaunchBridge final : public QObject",
                "class MailDockLaunchBridge final : public QObject",
                "class IntentDockBridge final : public QObject",
                "m_state.resolveActivation(",
                'intent != QStringLiteral("LAUNCH")',
                'if (name != QStringLiteral("Trash"))',
                "CANOPY_INTENT_DOCK_CONNECTED",
                "CANOPY_FILES_DOCK_INTENT_REFUSED",
                "CANOPY_BROWSER_DOCK_INTENT_REFUSED",
                "CANOPY_MAIL_DOCK_INTENT_REFUSED"):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)
        # The launcher gate is authoritative; no duplicate direct launch path
        # for approved tiles remains.
        self.assertIn("// approved names use the intent gate below", cpp)

    def test_unavailable_and_refused_intents_are_disclosed(self):
        cpp = self.cpp
        for marker in (
                "window activation state unavailable",
                "is running; focus is unavailable",
                "activation ignored: launcher disabled",
                "could not be launched",
                "showActivationStatus(m_status, activationRefusal(",
                "state.applySnapshot(QVariantMap());  // clear every indicator"):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)

    def test_compiled_host_selftest_covers_live_closed_and_fail_closed(self):
        cpp = self.cpp
        for marker in (
                '--self-test-window-activation-fixture',
                "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: trusted snapshot",
                "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: indicators",
                "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: focus disclosed",
                "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: closed snapshot",
                "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: fail closed",
                "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: accessibility disclosure",
                "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: cleared disclosure",
                "SELF_TEST_PASS: dock running and active indicators reflect trusted snapshot",
                "SELF_TEST_PASS: dock activation intent reaches host gate without false focus",
                "SELF_TEST_PASS: closed snapshot clears running and active indicators",
                "SELF_TEST_PASS: untrusted snapshot clears all indicators",
                "WINDOW_ACTIVATION_HOST_SELF_TEST_PASS"):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)

    def test_qml_adapter_remains_nonvisual_and_sequence_aware(self):
        adapter = self.adapter
        self.assertTrue(adapter.lstrip().startswith("//"))
        self.assertIn("import QtQml", adapter)
        self.assertIn("QtObject {", adapter)
        self.assertIn("canopyWindowActivationState", adapter)
        self.assertIn("readonly property int sequence", adapter)
        self.assertIn('return "REJECT"', adapter)
        self.assertIn("indicatorsAvailable", adapter)
        for forbidden in ("Rectangle", "Image", "Timer", "Animation", ".png",
                          ".svg", "QProcess", "QQmlComponent"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, adapter)

    def test_dock_stays_byte_frozen_and_state_is_applied_by_host(self):
        import hashlib

        # The frozen DockTile.qml blob is deliberately untouched. State is
        # applied to the QObjects from main.cpp, not by editing visual QML.
        # Read universal-newline text so both LF CI and CRLF Windows checkouts
        # normalize back to the same committed blob bytes.
        tile_blob = DOCK.read_text(encoding="utf-8").encode("utf-8")
        blob_sha = hashlib.sha1(b"blob " + str(len(tile_blob)).encode() +
                                b"\0" + tile_blob).hexdigest()
        self.assertEqual(blob_sha, "67ce71fbdf671eff86aa455b0d4b6f4471b8a3e9")
        cpp = self.cpp
        for marker in (
                "static void updateDockActivationProperties(",
                "static void setTileProperty(",
                'setTileProperty(tile, QStringLiteral("activationAvailable"), available)',
                'setTileProperty(tile, QStringLiteral("activationSequence"), sequence)',
                'setTileProperty(tile, QStringLiteral("windowRunning"), running)',
                'setTileProperty(tile, QStringLiteral("windowActive"), active)',
                'setTileProperty(tile, QStringLiteral("activationIntent"), intent)',
                'QQmlProperty accessibleDescription(',
                '&WindowActivationState::stateChanged',
                "updateDockActivationProperties(\n"
                "        window->contentItem(), activationState, activationAdapter)"):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)
        # No visual QML source was added or changed.
        self.assertNotIn("activationDescription", self.dock)
        self.assertNotIn("windowRunning", self.dock)
        self.assertIn(
            'ToolTip.text: iconName === "Files" ? "Toggle Files preview" '
            ': iconName + " — preview only"', self.dock)


if __name__ == "__main__":
    unittest.main()
