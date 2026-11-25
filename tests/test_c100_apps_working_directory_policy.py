"""Offline unit tests for the launch working-directory policy component."""

import os
import tempfile
import unittest
from pathlib import Path

from canopy_features.apps.working_directory_policy import (
    Decision,
    SystemFilesystem,
    WorkingDirectoryPolicy,
    WorkingDirectoryPolicyError,
)

ROOT = "/home/user"
HOME = "/home/user/docs"
PARENT = "/home/user"


class FakeFilesystem:
    """In-memory read-only view: directories and symlink-style redirects."""

    def __init__(self, directories=(), links=None):
        self.directories = frozenset(directories)
        self.links = dict(links or {})

    def is_directory(self, path):
        return path in self.directories or path in self.links

    def resolve(self, path):
        return self.links.get(path, path)


class WorkingDirectoryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.fs = FakeFilesystem((ROOT, HOME, "/home/user2/docs"))
        self.policy = WorkingDirectoryPolicy(
            (ROOT,), filesystem=self.fs, flavor="posix")

    def evaluate(self, requested, inherited=HOME):
        return self.policy.evaluate(requested, inherited)

    # Relative paths: the request must never depend on an inherited cwd.
    def test_relative_path_rejected(self):
        for requested in ("docs", "./docs", "../docs", "~/docs", ".", ""):
            with self.subTest(requested=requested):
                decision = self.evaluate(requested)
                self.assertEqual(decision.status, "REJECTED")
                self.assertEqual(decision.reason, "RELATIVE_PATH")
                self.assertIsNone(decision.path)
                self.assertFalse(decision.allowed)

    def test_windows_flavor_rejects_drive_relative_path(self):
        fs = FakeFilesystem(("C:\\apps", "C:\\apps\\work"))
        policy = WorkingDirectoryPolicy(
            ("C:\\apps",), filesystem=fs, flavor="windows")
        decision = policy.evaluate("work", "C:\\apps")
        self.assertEqual(decision.reason, "RELATIVE_PATH")

    # Missing directories: an explicit directory that does not exist is refused.
    def test_missing_directory_rejected(self):
        decision = self.evaluate("/home/user/gone")
        self.assertEqual(decision.status, "REJECTED")
        self.assertEqual(decision.reason, "MISSING_DIRECTORY")
        self.assertIsNone(decision.path)

    def test_existing_file_is_not_a_directory(self):
        self.fs.directories = frozenset((ROOT,))
        decision = self.evaluate(HOME)
        self.assertEqual(decision.reason, "MISSING_DIRECTORY")

    # Unsafe inheritance: inheriting a cwd outside the allowed roots is refused.
    def test_unsafe_inheritance_outside_root_rejected(self):
        decision = self.evaluate(None, inherited="/home/user2/docs")
        self.assertEqual(decision.status, "REJECTED")
        self.assertEqual(decision.reason, "UNSAFE_INHERITANCE")
        self.assertIsNone(decision.path)

    def test_unsafe_inheritance_missing_cwd_rejected(self):
        decision = self.evaluate(None, inherited="/gone/dir")
        self.assertEqual(decision.reason, "UNSAFE_INHERITANCE")

    def test_unsafe_inheritance_traversal_rejected(self):
        decision = self.evaluate(None, inherited="/home/user/../user2/docs")
        self.assertEqual(decision.reason, "UNSAFE_INHERITANCE")

    def test_safe_inheritance_allowed(self):
        decision = self.evaluate(None, inherited=HOME)
        self.assertEqual(decision.status, "ALLOWED")
        self.assertEqual(decision.path, HOME)
        self.assertTrue(decision.allowed)

    # Allowed paths and boundary handling.
    def test_allowed_absolute_directory(self):
        decision = self.evaluate(HOME)
        self.assertEqual(decision.status, "ALLOWED")
        self.assertEqual(decision.reason, "OK")
        self.assertEqual(decision.path, HOME)
        self.assertIsInstance(decision, Decision)

    def test_root_itself_allowed(self):
        self.assertEqual(self.evaluate(ROOT).path, ROOT)

    def test_sibling_prefix_root_not_allowed(self):
        # "/home/user2/docs" starts with the root string but is outside it.
        decision = self.evaluate("/home/user2/docs")
        self.assertEqual(decision.status, "REJECTED")
        self.assertEqual(decision.reason, "OUTSIDE_ALLOWED_ROOT")
        self.assertIsNone(decision.path)

    def test_explicit_traversal_rejected(self):
        decision = self.evaluate("/home/user/../user2/docs")
        self.assertEqual(decision.reason, "PATH_TRAVERSAL")

    def test_symlink_escape_rejected(self):
        fs = FakeFilesystem(
            (ROOT, "/home/user/link"),
            links={"/home/user/link": "/home/user2/docs"},
        )
        policy = WorkingDirectoryPolicy(
            (ROOT,), filesystem=fs, flavor="posix")
        decision = policy.evaluate("/home/user/link", ROOT)
        self.assertEqual(decision.status, "REJECTED")
        self.assertEqual(decision.reason, "OUTSIDE_ALLOWED_ROOT")
        self.assertIsNone(decision.path)

    def test_multiple_roots_allowed(self):
        policy = WorkingDirectoryPolicy(
            (ROOT, "/home/user2"), filesystem=self.fs, flavor="posix")
        self.assertEqual(policy.evaluate("/home/user2/docs", ROOT).status,
                         "ALLOWED")

    # Bounded inputs, configuration errors, and no secret/path leakage on reject.
    def test_oversized_and_null_byte_requests_rejected(self):
        self.assertEqual(self.evaluate("a" * 4097).reason, "INVALID_REQUEST")
        self.assertEqual(self.evaluate("/home/user/\x00").reason,
                         "INVALID_REQUEST")

    def test_invalid_configuration_raises(self):
        for roots in ((), ("relative",), ROOT, (ROOT,) * 33):
            with self.subTest(roots=roots):
                with self.assertRaises(WorkingDirectoryPolicyError):
                    WorkingDirectoryPolicy(roots, filesystem=self.fs,
                                           flavor="posix")
        with self.assertRaises(WorkingDirectoryPolicyError):
            WorkingDirectoryPolicy((ROOT,), filesystem=self.fs, flavor="dos")
        with self.assertRaises(WorkingDirectoryPolicyError):
            self.policy.evaluate(HOME, inherited="relative")
        with self.assertRaises(WorkingDirectoryPolicyError):
            WorkingDirectoryPolicy((ROOT,), filesystem=object(), flavor="posix")

    def test_rejection_does_not_carry_untrusted_path(self):
        decision = self.evaluate("/secret/path/that/must/not/appear")
        self.assertIsNone(decision.path)

    def test_decision_is_immutable(self):
        decision = self.evaluate(HOME)
        with self.assertRaises(Exception):
            decision.path = "/other"


class HostFilesystemTests(unittest.TestCase):
    """Real filesystem check on the host running this suite (no Mint claim)."""

    def test_real_directory_with_host_flavor(self):
        with tempfile.TemporaryDirectory() as temp:
            base = os.path.realpath(temp)
            work = os.path.join(base, "work")
            os.mkdir(work)
            policy = WorkingDirectoryPolicy((base,))
            self.assertIsInstance(policy._filesystem, SystemFilesystem)
            allowed = policy.evaluate(work, base)
            self.assertEqual(allowed.status, "ALLOWED")
            self.assertEqual(allowed.path, work)
            missing = policy.evaluate(os.path.join(base, "absent"), base)
            self.assertEqual(missing.reason, "MISSING_DIRECTORY")
            inherited = policy.evaluate(None, work)
            self.assertEqual(inherited.status, "ALLOWED")
        self.assertFalse(os.path.exists(base))

    def test_real_filesystem_outside_root_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = os.path.realpath(temp)
            elsewhere = os.path.realpath(
                str(Path(temp).parent))
            policy = WorkingDirectoryPolicy((base,))
            decision = policy.evaluate(elsewhere, base)
            self.assertEqual(decision.status, "REJECTED")
            self.assertEqual(decision.reason, "OUTSIDE_ALLOWED_ROOT")


if __name__ == "__main__":
    unittest.main()
