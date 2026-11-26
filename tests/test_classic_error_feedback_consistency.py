"""Source-contract tests for PE-033 user-visible failure feedback.

No Qt runtime is required. Dock bridges keep publishing their existing
machine-readable refusal text on ``selectionMessage``; the launcher footer and
the Files status footer are the single user-visible boundary and must append the
same actionable recovery hint. These tests protect that boundary without
changing compiled dock fixtures, approved artwork or shell geometry.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
LAUNCHER = (CLASSIC / "LauncherOverlay.qml").read_text(encoding="utf-8")
FILES = (CLASSIC / "PreviewWindow.qml").read_text(encoding="utf-8")
HOST = (CLASSIC / "main.cpp").read_text(encoding="utf-8")

HINT = "Check availability, then try again"
SEPARATOR = " · "


class ClassicErrorFeedbackConsistencyTests(unittest.TestCase):
    def test_both_boundaries_declare_the_same_single_hint(self):
        for name, text in (("LauncherOverlay.qml", LAUNCHER),
                           ("PreviewWindow.qml", FILES)):
            with self.subTest(source=name):
                self.assertEqual(text.count('"' + HINT + '"'), 1)
                self.assertIn('readonly property string retryHint: "' + HINT + '"', text)

    def test_both_boundaries_compose_failures_identically(self):
        for name, text, owner in (("LauncherOverlay.qml", LAUNCHER, "launcher"),
                                  ("PreviewWindow.qml", FILES, "preview")):
            with self.subTest(source=name):
                self.assertIn("function feedback(message)", text)
                self.assertIn('if (typeof message !== "string" || message.length === 0)',
                              text)
                self.assertIn('message.indexOf("Opened ") === 0', text)
                self.assertIn('message + "' + SEPARATOR + '" + ' + owner
                              + '.retryHint', text)

    def test_launcher_footer_displays_the_composed_status(self):
        self.assertIn("readonly property string visibleStatus", LAUNCHER)
        self.assertIn("launcher.feedback(launcher.selectionMessage)", LAUNCHER)
        self.assertIn("text: launcher.visibleStatus", LAUNCHER)
        self.assertNotIn("text: launcher.selectionMessage.length > 0", LAUNCHER)
        self.assertIn("Accessible.name: text", LAUNCHER)

    def test_files_footer_displays_the_composed_status(self):
        self.assertIn('id: fileManagerStatusLabel', FILES)
        self.assertIn('objectName: "canopyFileManagerStatus"', FILES)
        self.assertIn("return preview.feedback(status)", FILES)
        self.assertIn('"File manager unavailable"', FILES)
        self.assertIn('Accessible.name: "File manager launch status"', FILES)

    def test_dock_launcher_and_files_refusals_still_reach_the_boundary(self):
        # The host text is read-only here: compiled self-tests assert those
        # exact substrings. The QML boundary is what makes them actionable.
        for marker in ("Files could not be launched",
                       "Browser could not be launched",
                       "Mail could not be launched",
                       " could not be launched"):
            with self.subTest(dock=marker):
                self.assertIn(marker, HOST)
        self.assertGreaterEqual(HOST.count('setProperty("selectionMessage"'), 4)
        for marker in ('" is not connected in this preview"',
                       '" could not be launched"'):
            with self.subTest(launcher=marker):
                self.assertIn(marker, LAUNCHER)
        for marker in ('"File manager not opened — invalid target"',
                       '"File manager not opened — bridge unavailable"',
                       '"File manager could not be launched"'):
            with self.subTest(files=marker):
                self.assertIn(marker, FILES)

    def test_success_notices_are_not_relabelled_as_failures(self):
        self.assertIn('"Opened system file manager"', FILES)
        self.assertIn('"Opened system Settings for "',
                      (CLASSIC / "QuickControlsOverlay.qml").read_text(encoding="utf-8"))
        for name, text in (("LauncherOverlay.qml", LAUNCHER),
                           ("PreviewWindow.qml", FILES)):
            with self.subTest(source=name):
                self.assertIn('message.indexOf("Opened ") === 0', text)

    def test_no_visual_or_asset_contract_was_touched(self):
        for needle in ('objectName: "canopyLauncherStatus"',
                       'objectName: "canopyLauncherGrid"',
                       "width < 470 ? 3 : 4",
                       "panel.height < 410 ? 98 : 116",
                       "keyNavigationWraps: true",
                       'Accessible.name: "Search available preview applications"'):
            with self.subTest(frozen=needle):
                self.assertIn(needle, LAUNCHER)
        for needle in ('objectName: "canopyOpenInFileManager"',
                       "enabled: preview.canOpenInFileManager()",
                       "launch(dockName)",
                       'Accessible.name: "File manager launch status"'):
            with self.subTest(frozen=needle):
                self.assertIn(needle, FILES)


if __name__ == "__main__":
    unittest.main()
