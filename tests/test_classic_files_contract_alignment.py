"""Alignment tests between the merged pure Files contracts and the compiled model.

The pure modules are read-only oracles: they are already merged and tested.
This file proves the compiled Classic Files model mirrors their home-scoped
containment, fail-closed refusals and fixed-label launch target without
copying process launch, shell, polling or path leakage into QML/C++.
"""
from pathlib import Path
import re
import unittest

from canopy_features.apps.file_manager_intent import (
    LAUNCH_ACTION, REASON_OUTSIDE_HOME, form_file_manager_intent,
)
from canopy_features.apps.files_intent_preview import (
    APPROVED, compose_files_intent_preview,
)
from canopy_features.apps.working_directory_policy import Decision

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "prototype" / "classic"


class ClassicFilesContractAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = (SOURCE / "FileModel.h").read_text(encoding="utf-8")
        cls.model = (SOURCE / "FileModel.cpp").read_text(encoding="utf-8")
        cls.tile = (SOURCE / "FolderTile.qml").read_text(encoding="utf-8")
        cls.window = (SOURCE / "PreviewWindow.qml").read_text(encoding="utf-8")
        cls.bridge = (SOURCE / "SystemAppLauncher.cpp").read_text(encoding="utf-8")

    def test_pure_contracts_are_merged_and_still_fail_closed(self):
        self.assertEqual(LAUNCH_ACTION, "open-directory")
        self.assertEqual(REASON_OUTSIDE_HOME, "outside_home")
        intent = form_file_manager_intent(".", home=Path.home())
        self.assertTrue(intent.uri.startswith("file:"))
        self.assertEqual(intent.action, LAUNCH_ACTION)
        denied = compose_files_intent_preview(
            intent, Decision("REJECTED", "outside_home"))
        self.assertNotEqual(denied.status, APPROVED)
        self.assertIsNone(denied.uri)
        self.assertIsNone(denied.directory)

    def test_compiled_model_mirrors_canonical_home_containment(self):
        # Same safety shape as form_file_manager_intent: canonicalise first,
        # then require the canonical path to stay under the home root.
        self.assertIn("QDir::homePath()", self.model)
        self.assertIn("canonicalFilePath()", self.model)
        self.assertIn("startsWith(prefix, kCase)", self.model)
        self.assertIn("candidate = path.trimmed()", self.model)
        self.assertIn("candidate = m_homePath", self.model)

    def test_refusal_reasons_are_fixed_and_never_interpolate_a_path(self):
        refusals = re.findall(r"navigationRejected\(([^;]*)\);", self.model)
        self.assertGreaterEqual(len(refusals), 3)
        for reason in refusals:
            with self.subTest(reason=reason.strip()):
                self.assertIn("QStringLiteral(", reason)
                self.assertNotIn(".arg(", reason)
                self.assertNotIn("%1", reason)
                self.assertNotIn("currentPath", reason)
                self.assertNotIn("entry.path", reason)

    def test_native_open_uses_only_the_fixed_dock_label(self):
        self.assertIn('return QStringLiteral("Files");', self.header)
        self.assertIn('candidate.compare(QStringLiteral("Files"), Qt::CaseSensitive) == 0',
                      self.header)
        self.assertIn('QStringLiteral("Files")', self.bridge)
        self.assertIn("g_app_info_launch(", self.bridge)
        launch_args = re.findall(r"canopySystemLauncher\.launch\(([^)]*)\)", self.window)
        self.assertEqual(launch_args, ["dockName"])
        for forbidden in ("g_app_info_launch", "QProcess", "QDesktopServices"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.header)
                self.assertNotIn(forbidden, self.model)
                self.assertNotIn(forbidden, self.tile)

    def test_folder_tile_no_longer_claims_no_disk_access(self):
        self.assertNotIn("no disk access", self.tile)
        self.assertIn('objectName: "canopyFolderTile"', self.tile)
        # Visual contract is untouched: approved folder art and geometry stay.
        self.assertIn("qrc:/Canopy/Classic/assets/ui/folder-blue.svg", self.tile)
        self.assertIn("width: 108", self.tile)
        self.assertIn("height: compact ? 68 : 90", self.tile)


if __name__ == "__main__":
    unittest.main()
