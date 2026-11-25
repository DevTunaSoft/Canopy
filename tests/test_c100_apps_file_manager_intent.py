"""Offline unit tests for safe file-manager launch intents.

No Qt, no desktop session and no real Mint claim. Tests use a temporary
home scope on the host filesystem and assert inert data plus fail-closed
handling of escapes, symlinks and missing directories.
"""

from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import tempfile
import unittest

from canopy_features.apps.file_manager_intent import (
    LAUNCH_ACTION,
    REASON_HOME_UNAVAILABLE,
    REASON_INVALID_PATH,
    REASON_MISSING_DIRECTORY,
    REASON_NOT_DIRECTORY,
    REASON_OUTSIDE_HOME,
    FileManagerIntent,
    IntentRejected,
    form_file_manager_intent,
)

MODULE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "canopy_features" / "apps" / "file_manager_intent.py"
)


class FileManagerIntentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="canopy-intent-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.home = self.base / "home"
        self.outside = self.base / "outside"
        self.home.mkdir()
        self.outside.mkdir()

    def symlink(self, target, link):
        """Create a directory symlink; skip where the host forbids it."""
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError) as exc:
            self.skipTest("symlink creation unavailable on this host: " + str(exc))

    def assert_rejected(self, reason, path=None, **kwargs):
        with self.assertRaises(IntentRejected) as caught:
            form_file_manager_intent(path, home=self.home, **kwargs)
        self.assertEqual(caught.exception.reason, reason)

    def test_home_when_path_empty_and_plain_home_scope(self):
        intent = form_file_manager_intent(home=self.home)
        self.assertIsInstance(intent, FileManagerIntent)
        self.assertEqual(intent.action, LAUNCH_ACTION)
        self.assertEqual(intent.directory, str(self.home))
        self.assertEqual(intent.uri, self.home.as_uri())
        self.assertTrue(intent.uri.startswith("file:///"))

    def test_existing_subdirectory_inside_home(self):
        docs = self.home / "Documents"
        docs.mkdir()
        intent = form_file_manager_intent(docs, home=self.home)
        self.assertEqual(intent.directory, str(docs))
        self.assertEqual(intent.uri, docs.as_uri())
        self.assertEqual(intent.to_dict(), {
            "action": LAUNCH_ACTION,
            "uri": docs.as_uri(),
            "directory": str(docs),
        })

    def test_relative_and_whitespace_paths_resolve_under_home(self):
        nested = self.home / "a" / "b"
        nested.mkdir(parents=True)
        self.assertEqual(
            form_file_manager_intent("a/b", home=self.home).directory,
            str(nested),
        )
        self.assertEqual(
            form_file_manager_intent("  a/b  ", home=self.home).directory,
            str(nested),
        )

    def test_tilde_path_outside_supplied_scope_rejected(self):
        # "~" expands to the process home, which is deliberately outside the
        # temporary home scope passed in here: expansion must not bypass scope.
        self.assertNotEqual(Path.home(), self.home)
        self.assert_rejected(REASON_OUTSIDE_HOME, "~")

    def test_missing_directory_rejected(self):
        self.assert_rejected(REASON_MISSING_DIRECTORY, self.home / "NoSuchFolder")

    def test_missing_home_rejected(self):
        with self.assertRaises(IntentRejected) as caught:
            form_file_manager_intent(home=self.base / "absent-home")
        self.assertEqual(caught.exception.reason, REASON_HOME_UNAVAILABLE)

    def test_file_inside_home_rejected(self):
        note = self.home / "note.txt"
        note.write_text("hello", encoding="utf-8")
        self.assert_rejected(REASON_NOT_DIRECTORY, note)

    def test_dotdot_traversal_outside_home_rejected(self):
        self.assert_rejected(
            REASON_OUTSIDE_HOME,
            self.home / ".." / "outside",
        )

    def test_absolute_directory_outside_home_rejected(self):
        self.assert_rejected(REASON_OUTSIDE_HOME, self.outside)

    def test_symlink_escape_outside_home_rejected(self):
        link = self.home / "escape"
        self.symlink(self.outside, link)
        self.assertTrue(link.is_dir())  # visible link, target outside scope
        self.assert_rejected(REASON_OUTSIDE_HOME, link)

    def test_broken_symlink_rejected_as_missing(self):
        link = self.home / "broken"
        self.symlink(self.outside / "does-not-exist", link)
        self.assert_rejected(REASON_MISSING_DIRECTORY, link)

    def test_internal_symlink_allowed_and_canonicalised(self):
        real = self.home / "real"
        real.mkdir()
        link = self.home / "alias"
        self.symlink(real, link)
        intent = form_file_manager_intent(link, home=self.home)
        self.assertEqual(intent.directory, str(real))
        self.assertEqual(intent.uri, real.as_uri())

    def test_special_characters_percent_encoded(self):
        folder = self.home / "a folder #1 & café"
        folder.mkdir()
        uri = form_file_manager_intent(folder, home=self.home).uri
        self.assertTrue(uri.startswith("file:///"))
        self.assertNotIn(" ", uri)
        self.assertNotIn("#", uri.replace("file:///", ""))
        self.assertEqual(uri, folder.as_uri())

    def test_invalid_path_type_rejected(self):
        for bad in (123, object(), b"bytes"):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(IntentRejected) as caught:
                    form_file_manager_intent(bad, home=self.home)
                self.assertEqual(caught.exception.reason, REASON_INVALID_PATH)

    def test_intent_is_immutable(self):
        intent = form_file_manager_intent(home=self.home)
        with self.assertRaises(FrozenInstanceError):
            intent.uri = "file:///etc"

    def test_module_is_inert_data_only(self):
        source = MODULE_SOURCE.read_text(encoding="utf-8")
        for forbidden in (
            "subprocess", "Popen", "os.system", "os.startfile",
            "QDesktopServices", "QProcess", "socket", "requests",
            "QTimer", "Thread(", "asyncio", "time.sleep", "while True",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    @unittest.skipUnless(os.name == "nt", "Windows case-insensitive path check")
    def test_windows_home_case_does_not_change_result(self):
        mixed = "".join(
            char.swapcase() if char.isalpha() else char
            for char in str(self.home)
        )
        intent = form_file_manager_intent(home=Path(mixed))
        self.assertEqual(intent.directory, str(self.home))


if __name__ == "__main__":
    unittest.main()
