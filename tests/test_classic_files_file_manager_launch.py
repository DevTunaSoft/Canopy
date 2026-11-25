"""Source-contract tests for the Files preview's native launch action.

No Qt runtime is required. These tests keep the owned C++/QML contract honest:
an exact, case-sensitive dock-label target, a single fail-closed call to the
existing host GIO launcher bridge, visible refusal status, and no shell,
argv, path or URL ever reaching the launcher.
"""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic"


class ClassicFilesFileManagerLaunchSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = (SOURCE / "FileModel.h").read_text(encoding="utf-8")
        cls.model = (SOURCE / "FileModel.cpp").read_text(encoding="utf-8")
        cls.window = (SOURCE / "PreviewWindow.qml").read_text(encoding="utf-8")
        # Read-only reference: the launcher bridge itself is not owned here.
        cls.bridge = (SOURCE / "SystemAppLauncher.cpp").read_text(encoding="utf-8")

    def test_exact_target_validation_lives_in_the_model(self):
        self.assertIn('Q_PROPERTY(QString fileManagerDockName READ fileManagerDockName CONSTANT)',
                      self.header)
        self.assertIn('QString fileManagerDockName() const { return QStringLiteral("Files"); }',
                      self.header)
        self.assertIn('Q_INVOKABLE bool isFileManagerDockName(const QString &candidate) const',
                      self.header)
        self.assertIn('candidate.compare(QStringLiteral("Files"), Qt::CaseSensitive) == 0',
                      self.header)
        # The model exposes only the fixed label; it never accepts a path or
        # command as the launch target.
        self.assertNotIn("openFileManager", self.header)
        self.assertNotIn("fileManagerPath", self.header)

    def test_action_is_clearly_labeled_and_accessible(self):
        self.assertIn('objectName: "canopyOpenInFileManager"', self.window)
        self.assertIn('text: "Open in file manager"', self.window)
        self.assertIn('Accessible.name: "Open in file manager"', self.window)
        self.assertIn('ToolTip.text: "Open in file manager"', self.window)
        self.assertIn('onClicked: preview.openInFileManager(preview.fileManagerDockName)',
                      self.window)
        self.assertRegex(self.window, r"function openInFileManager\(dockName\)")
        self.assertRegex(self.window, r"function canOpenInFileManager\(\)")
        # The action lives in the always-visible footer, not the toolbar that
        # is hidden in condensed mode at small resolutions.
        status_bar = self.window[self.window.index("id: statusBar"):]
        self.assertIn('objectName: "canopyOpenInFileManager"', status_bar)

    def test_only_exact_dock_label_can_reach_the_bridge(self):
        # Reject non-strings and every string except the model-owned literal
        # before any bridge method is called.
        self.assertIn('typeof dockName !== "string"', self.window)
        self.assertIn('!fileModel.isFileManagerDockName(dockName)', self.window)
        self.assertIn('dockName !== preview.fileManagerDockName', self.window)
        self.assertIn('fileManagerDockName !== "Files"', self.window)
        launch_args = re.findall(r"canopySystemLauncher\.launch\(([^)]*)\)", self.window)
        self.assertEqual(launch_args, ["dockName"])
        can_launch_args = re.findall(r"canopySystemLauncher\.canLaunch\(([^)]*)\)",
                                     self.window)
        self.assertEqual(can_launch_args, ["fileManagerDockName"])
        for forbidden in ("preview.currentPath", "preview.homePath", "preview.searchQuery",
                          "fileModel.currentPath", "path)", "searchQuery)"):
            self.assertNotIn("launch(" + forbidden, self.window)

    def test_bridge_readiness_is_type_guarded_and_opt_in(self):
        for guard in ('typeof canopySystemLaunchEnabled !== "undefined"',
                      'canopySystemLaunchEnabled === true',
                      'typeof canopySystemLauncher !== "undefined"',
                      'canopySystemLauncher !== null',
                      'typeof canopySystemLauncher.canLaunch === "function"',
                      'typeof canopySystemLauncher.launch === "function"',
                      'canopySystemLauncher.canLaunch(fileManagerDockName) === true'):
            with self.subTest(guard=guard):
                self.assertIn(guard, self.window)
        self.assertIn("enabled: preview.canOpenInFileManager()", self.window)

    def test_fail_closed_status_never_claims_false_success(self):
        for status in ('File manager not opened — invalid target',
                       'File manager not opened — bridge unavailable',
                       'File manager could not be launched',
                       'File manager unavailable'):
            with self.subTest(status=status):
                self.assertIn('"' + status + '"', self.window)
        self.assertIn('objectName: "canopyFileManagerStatus"', self.window)
        self.assertIn('Accessible.name: "File manager launch status"', self.window)
        # The success message is reachable only inside the launch() success
        # branch; refusal messages are the failure branches.
        success = self.window.index('fileManagerStatus = "Opened system file manager"')
        launch = self.window.index("if (canopySystemLauncher.launch(dockName))")
        refusal = self.window.index('fileManagerStatus = "File manager could not be launched"')
        self.assertLess(launch, success)
        self.assertLess(success, refusal)
        self.assertEqual(
            self.window.count('fileManagerStatus = "Opened system file manager"'), 1)

    def test_no_shell_argv_path_or_process_api(self):
        for forbidden in ("QProcess", "QNetworkAccessManager", "QUdpSocket",
                          "std::system", "::system(", "popen(", "QDesktopServices",
                          "Qt.createQmlObject", "XMLHttpRequest", "Timer {",
                          "QTimer", "Qt.callLater", "setInterval"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.window)
                self.assertNotIn(forbidden, self.header)
                self.assertNotIn(forbidden, self.model)

    def test_existing_gio_bridge_is_the_only_launch_path(self):
        # Read-only reference: the Files dock entry already maps to fixed
        # desktop IDs and uses GIO's launch API with no argv or shell.
        self.assertIn('QStringLiteral("Files")', self.bridge)
        for desktop_id in ("nemo.desktop", "org.gnome.Nautilus.desktop", "thunar.desktop"):
            self.assertIn(desktop_id, self.bridge)
        self.assertIn("g_app_info_launch(", self.bridge)
        self.assertIn("G_APP_INFO(info), nullptr, nullptr, &error", self.bridge)
        # No second GIO/shell code path was added to the owned files.
        for owned in (self.header, self.model, self.window):
            self.assertNotIn("g_app_info_launch", owned)


if __name__ == "__main__":
    unittest.main()
