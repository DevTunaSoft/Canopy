"""Offline tests for the composed Files-intent preview.

The composer is pure data: the host supplies already-formed source records and
receives one immutable, auditable decision. No process, real filesystem walk,
QML or visual change is involved.
"""
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import unittest

from canopy_features.apps.file_manager_intent import LAUNCH_ACTION, FileManagerIntent
from canopy_features.apps.working_directory_policy import Decision
from canopy_features.apps.files_intent_preview import (
    APPROVED,
    DENIED,
    REASON_INVALID_INPUT,
    REASON_OK,
    REASON_PATH_MISMATCH,
    REASON_POLICY_DENIED,
    REASON_UNSAFE_ACTION,
    REASON_UNSAFE_URI,
    FilesIntentPreview,
    PreviewInputError,
    compose_files_intent_preview,
)

MODULE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "canopy_features" / "apps" / "files_intent_preview.py"
)
DIRECTORY = str(Path.home() / "Documents")
OTHER_DIRECTORY = str(Path.home() / "Downloads")


def make_intent(directory=DIRECTORY, *, action=LAUNCH_ACTION, uri=None):
    return FileManagerIntent(
        action=action,
        uri=uri if uri is not None else Path(directory).as_uri(),
        directory=directory,
    )


def make_decision(path=DIRECTORY, *, status="ALLOWED", reason="OK"):
    return Decision(status, reason, path)


class FilesIntentPreviewTests(unittest.TestCase):
    def test_approved_when_both_sources_agree(self):
        preview = compose_files_intent_preview(
            make_intent(), make_decision())
        self.assertIsInstance(preview, FilesIntentPreview)
        self.assertEqual(preview.status, APPROVED)
        self.assertEqual(preview.reason, REASON_OK)
        self.assertTrue(preview.approved)
        self.assertEqual(preview.directory, DIRECTORY)
        self.assertEqual(preview.uri, Path(DIRECTORY).as_uri())
        self.assertEqual(preview.action, LAUNCH_ACTION)
        self.assertIsNone(preview.intent_reason)
        self.assertEqual(preview.policy_reason, "OK")

    def test_approved_to_dict_is_bounded_mapping(self):
        preview = compose_files_intent_preview(make_intent(), make_decision())
        data = preview.to_dict()
        self.assertEqual(set(data), {
            "status", "reason", "action", "uri", "directory",
            "intent_reason", "policy_reason",
        })
        self.assertEqual(data["status"], APPROVED)
        self.assertEqual(data["directory"], DIRECTORY)

    def test_preview_is_immutable(self):
        preview = compose_files_intent_preview(make_intent(), make_decision())
        with self.assertRaises(FrozenInstanceError):
            preview.status = DENIED

    def test_policy_rejection_is_denied_and_carries_no_path(self):
        decision = make_decision(path=None, status="REJECTED",
                                 reason="OUTSIDE_ALLOWED_ROOT")
        preview = compose_files_intent_preview(make_intent(), decision)
        self.assertEqual(preview.status, DENIED)
        self.assertEqual(preview.reason, REASON_POLICY_DENIED)
        self.assertEqual(preview.policy_reason, "OUTSIDE_ALLOWED_ROOT")
        self.assertFalse(preview.approved)
        self.assertIsNone(preview.directory)
        self.assertIsNone(preview.uri)
        self.assertIsNone(preview.action)

    def test_rejection_does_not_leak_untrusted_text_in_mapping(self):
        decision = make_decision(path=None, status="REJECTED",
                                 reason="UNSAFE_INHERITANCE")
        data = compose_files_intent_preview(make_intent(), decision).to_dict()
        for field in ("uri", "directory", "action"):
            self.assertIsNone(data[field])

    def test_path_mismatch_denied(self):
        preview = compose_files_intent_preview(
            make_intent(), make_decision(path=OTHER_DIRECTORY))
        self.assertEqual(preview.status, DENIED)
        self.assertEqual(preview.reason, REASON_PATH_MISMATCH)
        self.assertIsNone(preview.uri)
        self.assertIsNone(preview.directory)

    def test_non_string_policy_path_denied(self):
        preview = compose_files_intent_preview(
            make_intent(), make_decision(path=123))
        self.assertEqual(preview.reason, REASON_PATH_MISMATCH)

    def test_wrong_intent_type_raises_input_error(self):
        with self.assertRaises(PreviewInputError):
            compose_files_intent_preview(object(), make_decision())

    def test_wrong_decision_type_raises_input_error(self):
        with self.assertRaises(PreviewInputError):
            compose_files_intent_preview(make_intent(), object())

    def test_unsafe_action_denied(self):
        preview = compose_files_intent_preview(
            make_intent(action="execute"), make_decision())
        self.assertEqual(preview.reason, REASON_UNSAFE_ACTION)
        self.assertIsNone(preview.uri)

    def test_non_file_uri_scheme_denied(self):
        preview = compose_files_intent_preview(
            make_intent(uri="http://example.com/x"), make_decision())
        self.assertEqual(preview.reason, REASON_UNSAFE_URI)

    def test_shell_metacharacters_in_uri_denied(self):
        preview = compose_files_intent_preview(
            make_intent(uri="file:///tmp/a;rm -rf"), make_decision())
        self.assertEqual(preview.reason, REASON_UNSAFE_URI)

    def test_control_characters_in_uri_denied(self):
        preview = compose_files_intent_preview(
            make_intent(uri="file:///tmp/a\ninjected"), make_decision())
        self.assertEqual(preview.reason, REASON_UNSAFE_URI)

    def test_oversized_uri_denied(self):
        preview = compose_files_intent_preview(
            make_intent(uri="file:///" + "a" * 5000), make_decision())
        self.assertEqual(preview.reason, REASON_UNSAFE_URI)

    def test_invalid_input_reason_is_stable(self):
        self.assertEqual(REASON_INVALID_INPUT, "invalid_input")

    @unittest.skipUnless(os.name == "nt", "Windows case/separator equivalence")
    def test_windows_case_and_separator_equivalence(self):
        variant = DIRECTORY.replace("\\", "/").lower()
        preview = compose_files_intent_preview(
            make_intent(directory=variant), make_decision())
        self.assertEqual(preview.status, APPROVED)

    def test_module_is_inert_data_only(self):
        source = MODULE_SOURCE.read_text(encoding="utf-8")
        for forbidden in (
            "subprocess", "Popen", "os.system", "os.startfile",
            "QDesktopServices", "QProcess", "socket", "requests",
            "QTimer", "Thread(", "asyncio", "time.sleep", "while True",
            "open(", "Path(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
