"""Source contract for the last remaining Classic dock launch: Terminal.

The native result recorded a preview-only Terminal tile with a refusal footer
while a GIO ``konsole.desktop`` launch succeeded at all three tested sizes.
The frozen dock label must instead resolve through the one host-owned native
launcher when an installed desktop entry is available, or through the
documented launcher fallback with no refusal footer. These are source-level
invariants; compiled fixtures and CI continue to exercise the real GIO path.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_classic_dock_frozen import (
    APPROVED_DOCK_FNV64,
    fnv1a64,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic"
MAIN = SOURCE / "main.cpp"
DOC = SOURCE / "HOST_EVENT_BRIDGE.md"


def bridge_block(cpp):
    marker = "class TerminalDockLaunchBridge final : public QObject"
    if marker not in cpp:
        return ""
    return cpp.split(marker, 1)[1].split(
        "// Host-owned window-activation snapshot source", 1)[0]


def name_list_block(cpp, marker):
    if marker not in cpp:
        return ""
    return cpp.split(marker, 1)[1].split("};", 1)[0]


class ClassicTerminalDockNativeLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = MAIN.read_text(encoding="utf-8")
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.block = bridge_block(cls.cpp)

    def test_native_launch_uses_the_single_host_launcher(self):
        self.assertIn("class TerminalDockLaunchBridge final : public QObject",
                      self.cpp)
        self.assertTrue(self.block, "Terminal bridge block is missing")
        self.assertIn('name == QStringLiteral("Terminal")', self.block)
        self.assertIn("m_state.resolveActivation(", self.block)
        self.assertIn("m_launcher.canLaunch(name) && m_launcher.launch(name)",
                      self.block)
        self.assertIn("CANOPY_TERMINAL_DOCK_NATIVE_LAUNCH_REQUESTED",
                      self.block)
        self.assertIn("CANOPY_TERMINAL_DOCK_REJECTED", self.block)
        self.assertNotIn("could not be launched", self.block)

    def test_documented_fallback_never_shows_a_refusal_footer(self):
        self.assertIn('QMetaObject::invokeMethod(m_status, "openLauncher"',
                      self.block)
        self.assertIn('"Choose an installed terminal application"',
                      self.block)
        self.assertIn("CANOPY_TERMINAL_DOCK_FALLBACK_OPENED", self.block)
        self.assertIn("setProperty(\"selectionMessage\"", self.block)
        self.assertNotIn('name + QStringLiteral(" could not be launched")',
                         self.block)
        fallback = self.block.split(
            "m_launcher.canLaunch(name) && m_launcher.launch(name)", 1)[1]
        self.assertNotIn("showActivationStatus(", fallback)
        self.assertNotIn("activationRefusal(", fallback)

    def test_terminal_is_wired_once_and_is_not_gated_preview_only(self):
        cpp = self.cpp
        self.assertIn("static const QStringList terminalDockNames", cpp)
        remaining = name_list_block(
            cpp, "static const QStringList remainingDockNames = {")
        gated = name_list_block(cpp, "static const QStringList gatedDockNames = {")
        self.assertTrue(remaining and gated)
        self.assertNotIn('QStringLiteral("Terminal")', remaining)
        self.assertNotIn('QStringLiteral("Terminal")', gated)
        self.assertIn('QStringLiteral("Terminal")',
                      name_list_block(cpp, "static const QStringList "
                                      "terminalDockNames = {"))
        self.assertEqual(cpp.count("new TerminalDockLaunchBridge("), 1)
        self.assertIn("CANOPY_TERMINAL_DOCK_NATIVE_LAUNCH_CONNECTED", cpp)

    def test_compiled_fixture_exposes_both_terminal_cases(self):
        cpp = self.cpp
        self.assertIn("static bool runTerminalDockFixture", cpp)
        for token in ('"--self-test-terminal-dock-status"',
                      '"--self-test-terminal-dock-fixture"',
                      'QStringLiteral("TERMINAL_DOCK_STATUS_FIXTURE_PASS")',
                      'QStringLiteral("TERMINAL_DOCK_LAUNCH_FIXTURE_PASS")',
                      'QStringLiteral(";echo bad")'):
            with self.subTest(token=token):
                self.assertIn(token, cpp)

    def test_native_result_and_fallback_are_documented(self):
        for token in ("konsole.desktop", "1920x1080", "1200x750", "760x500",
                      "documented fallback", "NOT_RUN", "SYNTHETIC",
                      "screen-reader", "no visual approval"):
            with self.subTest(token=token):
                self.assertIn(token, self.doc)

    def test_frozen_visual_dock_and_single_launch_path_unchanged(self):
        main = (SOURCE / "Main.qml").read_text(encoding="utf-8")
        start = main.index("    Rectangle {\n        id: dock")
        self.assertEqual(fnv1a64(main[start:-1].encode("ascii")),
                         APPROVED_DOCK_FNV64)
        for forbidden in ("QProcess", "g_app_info_launch", "gio launch",
                          "QUrl(name)"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.cpp)


if __name__ == "__main__":
    unittest.main()
