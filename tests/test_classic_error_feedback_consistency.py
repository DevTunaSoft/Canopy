"""Source-contract tests for PE-033 user-visible failure feedback.

No Qt runtime is required. Dock bridges keep publishing their existing
machine-readable refusal text on ``selectionMessage``; the launcher footer and
the Files status footer are the single user-visible boundary and must append the
same actionable recovery hint. These tests protect that boundary without
changing compiled dock fixtures, approved artwork or shell geometry.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
LAUNCHER = (CLASSIC / "LauncherOverlay.qml").read_text(encoding="utf-8")
FILES = (CLASSIC / "PreviewWindow.qml").read_text(encoding="utf-8")
HOST = (CLASSIC / "main.cpp").read_text(encoding="utf-8")

HINT = "Check availability, then try again"
SEPARATOR = " · "

# Accessibility contract owned by PR #685: the status label's accessible name
# is the rendered text, and its role is AlertMessage (QML role 8). Alert is a
# C++ Event enum (2); using it as a QML role silently yields MenuBar.
DYNAMIC_STATUS_NAME = "Accessible.name: fileManagerStatusLabel.text"
LEGACY_STATUS_NAME = 'Accessible.name: "File manager launch status"'
ALERT_MESSAGE_ROLE = "Accessible.role: Accessible.AlertMessage"
ALERT_EVENT_ROLE = "Accessible.role: Accessible.Alert"
QT_GUARD = "#if QT_VERSION >= QT_VERSION_CHECK(6, 8, 0)"


def status_label_block(source: str) -> str:
    """Return the Files status Label block from a QML source string."""
    lines = source.replace("\r\n", "\n").split("\n")
    ids = [i for i, line in enumerate(lines)
           if "id: fileManagerStatusLabel" in line]
    if len(ids) != 1:
        raise AssertionError("fileManagerStatusLabel found %d times" % len(ids))
    start = None
    for i in range(ids[0], -1, -1):
        if lines[i].strip().startswith("Label {"):
            start = i
            break
    if start is None:
        raise AssertionError("no Label block for fileManagerStatusLabel")
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0 and i > start:
            return "\n".join(lines[start:i + 1])
    raise AssertionError("unbalanced Label block for fileManagerStatusLabel")


def assert_dynamic_status_a11y(block: str) -> None:
    if LEGACY_STATUS_NAME in block:
        raise AssertionError("stale constant accessible name in status label")
    if DYNAMIC_STATUS_NAME not in block:
        raise AssertionError("accessible name is not bound to rendered text")
    if ALERT_MESSAGE_ROLE not in block:
        raise AssertionError("status label is not an AlertMessage (role 8)")
    if re.search(r"Accessible\.role:\s*Accessible\.Alert\b", block):
        raise AssertionError("Alert event enum (2) used as a QML role")


def assert_qt_announce_guard(source: str) -> None:
    if QT_GUARD not in source:
        raise AssertionError("Qt 6.8 native announce guard is missing")
    guarded = source.split(QT_GUARD, 1)[1]
    true_branch, rest = guarded.split("#else", 1)
    false_branch = rest.split("#endif", 1)[0]
    if "return true;" not in true_branch or "return false;" not in false_branch:
        raise AssertionError("Qt version guard does not select an announce path")


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
        self.assertIn(DYNAMIC_STATUS_NAME, FILES)
        self.assertNotIn(LEGACY_STATUS_NAME, FILES)
        assert_dynamic_status_a11y(status_label_block(FILES))

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
                       DYNAMIC_STATUS_NAME):
            with self.subTest(frozen=needle):
                self.assertIn(needle, FILES)
        self.assertNotIn(LEGACY_STATUS_NAME, FILES)

    def test_status_a11y_negative_controls_reject_stale_name_and_wrong_role(self):
        # AlertMessage is role 8; Alert is a C++ Event enum (2), not a role.
        # Each hostile mutation must be rejected by the same source gate.
        for hostile, label in (
            (FILES.replace(DYNAMIC_STATUS_NAME, LEGACY_STATUS_NAME, 1),
             "constant accessible name"),
            (FILES.replace(ALERT_MESSAGE_ROLE, ALERT_EVENT_ROLE, 1),
             "Alert event enum used as role"),
        ):
            with self.subTest(mutation=label):
                self.assertNotEqual(hostile, FILES)
                with self.assertRaises(AssertionError):
                    assert_dynamic_status_a11y(status_label_block(hostile))

    def test_qt_announce_guard_negative_control(self):
        assert_qt_announce_guard(HOST)
        hostile = HOST.replace(QT_GUARD, "#if 1", 1)
        self.assertNotEqual(hostile, HOST)
        with self.assertRaises(AssertionError):
            assert_qt_announce_guard(hostile)


if __name__ == "__main__":
    unittest.main()
