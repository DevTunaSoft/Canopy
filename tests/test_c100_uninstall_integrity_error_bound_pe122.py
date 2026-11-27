"""Regression tests: uninstall integrity diagnostics must stay bounded.

PE-118/PE-122: ``normalize_manifest`` and ``plan_uninstall`` copied raw
manifest paths into exception messages and blocker strings. A 5030-character
path could inflate an exception to arbitrary size, and control characters or
non-string keys could be reflected verbatim into logs. These tests pin
fixed-token, component-capped diagnostics without changing plan semantics.
"""
import hashlib
from pathlib import Path
import tempfile
import unittest

from canopy_features.installer.uninstall_integrity import (
    UninstallIntegrityError,
    normalize_manifest,
    plan_uninstall,
)

MAX_DIAGNOSTIC = 400


def digest(data):
    return hashlib.sha256(data).hexdigest()


class _HugeRepr:
    """Hashable key whose repr would inflate a diagnostic by 4096 chars."""

    def __repr__(self):
        return "H" * 4096


class UninstallErrorBoundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="canopy-uii-bound-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "install"
        self.root.mkdir()

    def assert_bounded(self, text, token):
        self.assertIsInstance(text, str)
        self.assertLessEqual(len(text), MAX_DIAGNOSTIC, text[:120])
        self.assertIn(token, text)
        self.assertFalse(
            any(ord(char) < 0x20 or ord(char) == 0x7F for char in text),
            "control character leaked into diagnostic",
        )

    def error_text(self, payload):
        with self.assertRaises(UninstallIntegrityError) as ctx:
            normalize_manifest(payload)
        return str(ctx.exception)

    def test_huge_absolute_path_diagnostic_is_bounded(self):
        rel = "/" + "x" * 5000
        text = self.error_text({"schema": 1, "files": {rel: digest(b"x")}})
        self.assert_bounded(text, "absolute owned path refused")
        self.assertNotIn("x" * 200, text)

    def test_huge_component_with_bad_digest_is_bounded(self):
        rel = "a" * 5000 + "/leaf"
        text = self.error_text({"schema": 1, "files": {rel: "bad"}})
        self.assert_bounded(text, "invalid digest")
        self.assertNotIn("a" * 200, text)

    def test_huge_component_unsafe_component_is_bounded(self):
        rel = "a" * 5000 + "/.."
        text = self.error_text({"schema": 1, "files": {rel: digest(b"x")}})
        self.assert_bounded(text, "unsafe component")
        self.assertNotIn("a" * 200, text)

    def test_drive_qualified_huge_path_is_bounded(self):
        rel = "C:" + "d" * 5000
        text = self.error_text({"schema": 1, "files": {rel: digest(b"x")}})
        self.assert_bounded(text, "drive-qualified")
        self.assertNotIn("d" * 200, text)

    def test_control_characters_are_not_copied_into_diagnostics(self):
        rel = "dir/\x1b[31m\x7fbad"
        text = self.error_text({"schema": 1, "files": {rel: "bad"}})
        self.assert_bounded(text, "invalid digest")
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x7f", text)
        # The missing-file blocker takes a different path: still bounded.
        plan = plan_uninstall(
            self.root, {"schema": 1, "files": {rel: digest(b"x")}})
        self.assertFalse(plan.safe)
        for blocker in plan.blockers:
            self.assert_bounded(blocker, "owned file")
        joined = "\n".join(plan.blockers)
        self.assertNotIn("\x1b", joined)
        self.assertNotIn("\x7f", joined)

    def test_non_string_keys_use_a_fixed_token(self):
        for key in (None, 123, 1.5, b"/etc/passwd", ("a", "b"), _HugeRepr()):
            with self.subTest(key=type(key).__name__):
                text = self.error_text(
                    {"schema": 1, "files": {key: digest(b"x")}})
                self.assert_bounded(text, "invalid owned path")
                self.assertIn("<non-string>", text)
                self.assertNotIn("H" * 200, text)

    def test_plan_does_not_copy_huge_paths_into_blockers(self):
        parts = ["seg%d" % index for index in range(40)] + ["x" * 5000]
        rel = "/".join(parts)
        plan = plan_uninstall(
            self.root, {"schema": 1, "files": {rel: digest(b"x")}})
        self.assertFalse(plan.safe)
        self.assertEqual(plan.remove_files, ())
        for blocker in plan.blockers:
            self.assertLessEqual(len(blocker), MAX_DIAGNOSTIC, blocker[:120])
        self.assertNotIn("x" * 200, "\n".join(plan.blockers))

    def test_short_paths_keep_their_informative_text(self):
        plan = plan_uninstall(
            self.root, {"schema": 1, "files": {"share/gone": digest(b"x")}})
        self.assertFalse(plan.safe)
        self.assertTrue(
            any("MISSING" in blocker and "share/gone" in blocker
                for blocker in plan.blockers),
            plan.blockers,
        )

    def test_valid_manifest_semantics_unchanged(self):
        payload = {"schema": 1, "files": {"a/b.txt": digest(b"data")}}
        path = self.root / "a" / "b.txt"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"data")
        plan = plan_uninstall(self.root, payload)
        self.assertTrue(plan.safe)
        self.assertEqual(plan.remove_files, ("a/b.txt",))
        self.assertEqual(plan.remove_dirs, ("a",))
        self.assertEqual(plan.blockers, ())


if __name__ == "__main__":
    unittest.main()
