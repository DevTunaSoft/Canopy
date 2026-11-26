"""Focused tests for shell-free native default-app opening of local items.

The host owns process spawning; this module only validates a local path and
returns an immutable argv for a default-app handler. No Qt runtime, VM, full
suite or real desktop behavior is claimed here.
"""
import os
from pathlib import Path
import tempfile
import unittest

from unittest.mock import patch

from canopy_features.apps.native_file_open import (
    APPROVED,
    DENIED,
    HANDLER_GIO,
    HANDLER_XDG_OPEN,
    MAX_PATH_CHARS,
    build_native_open,
    failure_feedback,
)


class NativeFileOpenHappyPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.target = self.home / "notes.txt"
        self.target.write_text("synthetic fixture\n", encoding="utf-8")

    def test_approved_file_yields_single_gio_open_argument(self):
        decision = build_native_open(str(self.target), home=self.home)

        self.assertTrue(decision.approved)
        self.assertEqual(decision.status, APPROVED)
        self.assertEqual(decision.reason, "ok")
        self.assertEqual(decision.handler, HANDLER_GIO)
        self.assertEqual(decision.kind, "file")
        self.assertEqual(decision.target, str(self.target.resolve()))
        self.assertEqual(decision.argv, ("gio", "open", "--", str(self.target.resolve())))
        self.assertEqual(decision.feedback, "")


class NativeFileOpenValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.outside = Path(self.tmp.name) / "outside"
        self.outside.mkdir()
        self.outside_file = self.outside / "secret.txt"
        self.outside_file.write_text("outside fixture\n", encoding="utf-8")

    def assertDenied(self, decision, reason):
        self.assertFalse(decision.approved)
        self.assertEqual(decision.status, DENIED)
        self.assertEqual(decision.reason, reason)
        self.assertIsNone(decision.argv)
        self.assertIsNone(decision.target)
        self.assertTrue(decision.feedback)

    def test_empty_path_is_refused_with_feedback(self):
        self.assertDenied(build_native_open("   ", home=self.home), "empty_path")

    def test_missing_target_is_refused_with_feedback(self):
        self.assertDenied(build_native_open(self.home / "gone.txt", home=self.home),
                          "missing_target")

    def test_parent_traversal_cannot_leave_home(self):
        escape = os.path.join("..", "outside", "secret.txt")
        self.assertDenied(build_native_open(escape, home=self.home), "outside_home")

    def test_symlink_escape_is_refused_after_resolution(self):
        link = self.home / "escape.txt"
        try:
            link.symlink_to(self.outside_file)
        except (OSError, NotImplementedError):
            self.skipTest("host cannot create filesystem symlinks")
        self.assertDenied(build_native_open(link, home=self.home), "outside_home")

    def test_control_characters_are_refused(self):
        self.assertDenied(build_native_open("bad\x00name.txt", home=self.home),
                          "invalid_path")
        self.assertDenied(build_native_open("bad\nname.txt", home=self.home),
                          "invalid_path")

    def test_oversized_path_is_refused(self):
        self.assertDenied(build_native_open("a" * (MAX_PATH_CHARS + 1), home=self.home),
                          "too_long")

    def test_hostile_input_types_are_refused_without_builtin_errors(self):
        class BadPathLike:
            def __fspath__(self):
                raise RuntimeError("hostile fspath")

        for candidate in (42, b"bytes", None, BadPathLike()):
            with self.subTest(candidate=type(candidate).__name__):
                self.assertDenied(build_native_open(candidate, home=self.home),
                                  "invalid_path")

    def test_unsupported_file_type_is_refused(self):
        target = self.home / "fixture.txt"
        target.write_text("fixture\n", encoding="utf-8")
        with patch.object(Path, "is_file", return_value=False):
            decision = build_native_open(target, home=self.home)
        self.assertDenied(decision, "unsupported_type")

    def test_unavailable_home_is_refused_with_feedback(self):
        missing_home = Path(self.tmp.name) / "no-such-home"
        self.assertDenied(build_native_open("anything.txt", home=missing_home),
                          "home_unavailable")

    def test_directory_target_is_approved_as_a_directory(self):
        folder = self.home / "Pictures"
        folder.mkdir()
        decision = build_native_open(folder, home=self.home)
        self.assertTrue(decision.approved)
        self.assertEqual(decision.kind, "directory")
        self.assertEqual(decision.argv[-1], str(folder.resolve()))

    def test_shell_shaped_filename_stays_one_argv_token(self):
        odd = self.home / 'notes;$HOME & $(id).txt'
        odd.write_text("fixture\n", encoding="utf-8")
        decision = build_native_open(odd, home=self.home)
        self.assertTrue(decision.approved)
        self.assertEqual(len(decision.argv), 4)
        self.assertEqual(decision.argv[-1], str(odd.resolve()))
        for token in decision.argv:
            self.assertIs(type(token), str)


class NativeFileOpenHandlerAndFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.target = self.home / "report.txt"
        self.target.write_text("fixture\n", encoding="utf-8")

    def test_xdg_open_handler_yields_its_own_argument_vector(self):
        decision = build_native_open(
            self.target, home=self.home, handler=HANDLER_XDG_OPEN,
            available_handlers=(HANDLER_XDG_OPEN,))
        self.assertTrue(decision.approved)
        self.assertEqual(decision.handler, HANDLER_XDG_OPEN)
        self.assertEqual(decision.argv, ("xdg-open", str(self.target.resolve())))

    def test_handler_outside_host_allowlist_is_denied(self):
        decision = build_native_open(
            self.target, home=self.home, handler=HANDLER_XDG_OPEN,
            available_handlers=(HANDLER_GIO,))
        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "handler_unavailable")
        self.assertIsNone(decision.argv)

    def test_malformed_handler_allowlist_fails_closed(self):
        for allowed in ("gio", b"gio", {"gio": True}, 42, ("gio", 7)):
            with self.subTest(allowed=type(allowed).__name__):
                decision = build_native_open(self.target, home=self.home,
                                             available_handlers=allowed)
                self.assertFalse(decision.approved)
                self.assertEqual(decision.reason, "handler_unavailable")

    def test_failure_feedback_is_fixed_and_never_echoes_a_path(self):
        codes = (
            "home_unavailable", "invalid_path", "empty_path", "too_long",
            "missing_target", "unsupported_type", "outside_home",
            "handler_unavailable", "handler_missing", "no_default_app",
            "permission_denied", "open_failed", "cancelled", "unknown",
        )
        seen = []
        for code in codes:
            with self.subTest(code=code):
                message = failure_feedback(code)
                self.assertIs(type(message), str)
                self.assertTrue(message)
                self.assertNotIn("notes.txt", message)
                seen.append(message)
        self.assertEqual(len(seen), len(set(seen)))
        # Wrong-type reports collapse to one generic refusal; an unknown
        # string gets its own message, neither echoes a path.
        self.assertEqual(failure_feedback(42), failure_feedback(None))
        self.assertNotIn(failure_feedback("notes.txt"), seen)

    def test_decision_is_immutable_and_serializes_plain_data(self):
        decision = build_native_open(self.target, home=self.home)
        with self.assertRaises(Exception):
            decision.status = DENIED
        payload = decision.to_dict()
        self.assertIs(type(payload["argv"]), list)
        self.assertEqual(payload["argv"], list(decision.argv))
        self.assertEqual(payload["feedback"], "")

    def test_module_source_has_no_shell_or_process_launch_api(self):
        source = (Path(__file__).resolve().parents[1] / "canopy_features"
                  / "apps" / "native_file_open.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "shell=True", "popen(",
                          "Popen", "QProcess", "QDesktopServices", "os.exec",
                          "shlex", "$(", "`", "eval(", "exec("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
