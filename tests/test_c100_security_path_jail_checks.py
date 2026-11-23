"""Offline unit tests for canonical containment of user-selected paths.

No Qt runtime, Linux Mint guest, network or privileged operation is used.
Pure tests run on any host; filesystem tests use temporary directories and
skip only symlink cases when the host forbids creating them.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_features.security import path_jail_checks as jail  # noqa: E402


class IsContainedTests(unittest.TestCase):
    """Filesystem-free containment checks; exercise both host conventions."""

    ROOT = Path("/home/alice")

    def test_root_itself_and_descendant_are_contained(self):
        self.assertTrue(jail.is_contained(self.ROOT, self.ROOT, case_sensitive=True))
        self.assertTrue(jail.is_contained(
            self.ROOT / "docs" / "a.txt", self.ROOT, case_sensitive=True))

    def test_string_prefix_sibling_is_not_contained(self):
        # /home/alice2 must never pass as under /home/alice.
        self.assertFalse(jail.is_contained(
            Path("/home/alice2/secret.txt"), self.ROOT, case_sensitive=True))

    def test_case_sensitive_branch_rejects_case_mismatch(self):
        self.assertFalse(jail.is_contained(
            Path("/HOME/ALICE/a.txt"), self.ROOT, case_sensitive=True))

    def test_case_insensitive_branch_accepts_case_mismatch(self):
        self.assertTrue(jail.is_contained(
            Path("/HOME/ALICE/a.txt"), self.ROOT, case_sensitive=False))

    def test_unicode_components_compare_literally(self):
        root = Path("/home/林/café")
        self.assertTrue(jail.is_contained(
            root / "日本語" / "文件.txt", root, case_sensitive=True))
        outside = Path("/home/林/cafe\u0301/secret.txt")  # NFD lookalike
        self.assertFalse(jail.is_contained(outside, root, case_sensitive=True))


class ResolveWithinTests(unittest.TestCase):
    """Filesystem-backed checks: canonicalization, traversal and escapes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "jail"
        self.root.mkdir()
        self.outside = self.tmp / "outside"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("secret", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_root_and_absolute_path_inside_root_allowed(self):
        self.assertEqual(jail.resolve_within(self.root, self.root), self.root.resolve())
        sub = self.root / "sub"
        sub.mkdir()
        self.assertEqual(jail.resolve_within(self.root, str(sub)), sub.resolve())

    def test_relative_candidate_and_empty_candidate_use_root(self):
        doc = self.root / "doc.txt"
        doc.write_text("ok", encoding="utf-8")
        self.assertEqual(jail.resolve_within(self.root, "doc.txt"), doc.resolve())
        self.assertEqual(jail.resolve_within(self.root, "   "), self.root.resolve())
        self.assertEqual(jail.resolve_within(self.root, None), self.root.resolve())

    def test_dotdot_traversal_rejected(self):
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(self.root, "../outside/secret.txt")
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(self.root, "sub/../../outside/secret.txt")

    def test_unicode_traversal_rejected(self):
        folder = self.root / "café-日本語-📁"
        folder.mkdir()
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(self.root, "café-日本語-📁/../../outside/secret.txt")

    def test_unicode_inside_root_allowed(self):
        folder = self.root / "café-日本語-📁"
        folder.mkdir()
        result = jail.resolve_within(self.root, "café-日本語-📁")
        self.assertEqual(result, folder.resolve())
        self.assertTrue(jail.is_contained(result, self.root.resolve()))

    def test_unicode_lookalike_separators_stay_inside_root(self):
        # FULLWIDTH FULL STOP and FULLWIDTH SOLIDUS are filename characters,
        # not path separators, so they cannot traverse out of the root.
        literal = "．．／outside"
        result = jail.resolve_within(self.root, literal + "/secret.txt")
        self.assertTrue(jail.is_contained(result, self.root.resolve()))
        self.assertEqual(result.parent.name, literal)
        self.assertNotEqual(result, (self.outside / "secret.txt").resolve())

    def test_absolute_escape_rejected(self):
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(self.root, str(self.outside / "secret.txt"))
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(self.root, str(self.tmp / "jail2" / "x.txt"))

    def test_symlink_escape_rejected_after_canonicalization(self):
        link = self.root / "escape-link"
        try:
            link.symlink_to(self.outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not permitted on this host")
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(self.root, link / "secret.txt")
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(self.root, link / "secret.txt", must_exist=True)

    def test_symlinked_root_is_canonicalized(self):
        alias = self.tmp / "root-alias"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not permitted on this host")
        sub = self.root / "sub"
        sub.mkdir()
        self.assertEqual(jail.resolve_within(alias, "sub"), sub.resolve())

    def test_must_exist_controls_missing_final_component(self):
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(self.root, "missing.txt", must_exist=True)
        result = jail.resolve_within(self.root, "missing.txt")
        self.assertEqual(result, (self.root / "missing.txt").resolve())

    def test_embedded_nul_is_rejected(self):
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(self.root, "bad\x00name")

    def test_root_must_be_existing_directory(self):
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(self.tmp / "missing-root", "x")
        a_file = self.tmp / "a-file"
        a_file.write_text("x", encoding="utf-8")
        with self.assertRaises(jail.PathJailError):
            jail.resolve_within(a_file, "x")

    @unittest.skipUnless(os.name == "nt", "Windows host only")
    def test_windows_case_insensitive_default_on_host(self):
        self.assertFalse(jail._default_case_sensitive())
        sub = self.root / "Sub"
        sub.mkdir()
        result = jail.resolve_within(str(self.root).upper(), "sub")
        self.assertEqual(result, sub.resolve())


if __name__ == "__main__":
    unittest.main()
