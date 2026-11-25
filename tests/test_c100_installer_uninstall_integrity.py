"""Offline unit tests for reversible-uninstall planning.

Every test uses temporary files only. No installer is executed, no package
manager is called, and no path outside the temp tree is touched.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from canopy_features.installer.uninstall_integrity import (
    UninstallIntegrityError,
    _digest_hex,
    normalize_manifest,
    plan_uninstall,
    plan_uninstall_file,
    read_manifest,
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class UninstallIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "install"
        self.root.mkdir()
        self.manifest_path = self.base / "ownership.json"

    def add(self, rel, data):
        path = self.root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_manifest(self, files, *, schema=1):
        payload = {"schema": schema, "files": files}
        self.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def symlink_or_skip(self, target, link, *, target_is_directory=False):
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlinks unavailable on this host: " + str(exc))
        return link

    # -- happy path -------------------------------------------------------

    def test_plan_is_side_effect_free_and_removes_only_owned_files(self):
        first = self.add("bin/app", b"app bytes")
        second = self.add("share/data.txt", b"data bytes")
        unrelated = self.add("share/user.txt", b"keep me")
        self.write_manifest({
            "bin/app": digest(b"app bytes"),
            "share/data.txt": digest(b"data bytes"),
        })

        plan = plan_uninstall_file(self.root, self.manifest_path)

        self.assertTrue(plan.safe)
        self.assertEqual(plan.remove_files, ("bin/app", "share/data.txt"))
        self.assertEqual(plan.blockers, ())
        self.assertIn("bin", plan.remove_dirs)
        self.assertNotIn("share", plan.remove_dirs)
        self.assertTrue(any("share/user.txt" in reason for reason in plan.preserved))
        # Planning must not delete or alter anything.
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        self.assertEqual(unrelated.read_bytes(), b"keep me")

    def test_empty_owned_directories_removed_deepest_first(self):
        self.add("a/b/c/file.txt", b"content")
        self.write_manifest({"a/b/c/file.txt": digest(b"content")})

        plan = plan_uninstall_file(self.root, self.manifest_path)

        self.assertTrue(plan.safe)
        self.assertEqual(plan.remove_dirs, ("a/b/c", "a/b", "a"))

    def test_root_itself_is_never_removed(self):
        self.add("top.txt", b"content")
        self.write_manifest({"top.txt": digest(b"content")})

        plan = plan_uninstall_file(self.root, self.manifest_path)

        self.assertTrue(plan.safe)
        self.assertEqual(plan.remove_dirs, ())

    def test_unrelated_file_blocks_only_its_directory_not_the_plan(self):
        self.add("cfg/settings", b"owned")
        self.add("cfg/other", b"unrelated")
        self.write_manifest({"cfg/settings": digest(b"owned")})

        plan = plan_uninstall_file(self.root, self.manifest_path)

        self.assertTrue(plan.safe)
        self.assertIn("cfg/settings", plan.remove_files)
        self.assertNotIn("cfg", plan.remove_dirs)
        self.assertTrue(any("cfg/other" in reason for reason in plan.preserved))

    def test_empty_manifest_produces_safe_no_op_plan(self):
        self.write_manifest({})
        plan = plan_uninstall_file(self.root, self.manifest_path)
        self.assertTrue(plan.safe)
        self.assertEqual(plan.remove_files, ())
        self.assertEqual(plan.remove_dirs, ())

    # -- explicit missing-file coverage ----------------------------------

    def test_missing_owned_file_blocks_all_removals(self):
        survivor = self.add("bin/app", b"present")
        self.add("share/gone", b"deleted by someone")
        (self.root / "share" / "gone").unlink()
        self.write_manifest({
            "bin/app": digest(b"present"),
            "share/gone": digest(b"deleted by someone"),
        })

        plan = plan_uninstall_file(self.root, self.manifest_path)

        self.assertFalse(plan.safe)
        self.assertEqual(plan.remove_files, ())
        self.assertEqual(plan.remove_dirs, ())
        self.assertTrue(any("MISSING" in reason and "share/gone" in reason
                            for reason in plan.blockers))
        self.assertTrue(survivor.is_file())

    def test_missing_owned_file_does_not_remove_its_parent_directory(self):
        self.add("onlychild/file", b"gone")
        (self.root / "onlychild" / "file").unlink()
        self.write_manifest({"onlychild/file": digest(b"gone")})

        plan = plan_uninstall_file(self.root, self.manifest_path)

        self.assertFalse(plan.safe)
        self.assertNotIn("onlychild", plan.remove_dirs)
        self.assertTrue((self.root / "onlychild").is_dir())

    # -- explicit ownership-mismatch coverage ----------------------------

    def test_ownership_mismatch_blocks_all_removals(self):
        target = self.add("bin/app", b"original")
        target.write_bytes(b"user edited this")
        self.write_manifest({"bin/app": digest(b"original")})

        plan = plan_uninstall_file(self.root, self.manifest_path)

        self.assertFalse(plan.safe)
        self.assertEqual(plan.remove_files, ())
        self.assertEqual(plan.remove_dirs, ())
        self.assertTrue(any("OWNERSHIP MISMATCH" in reason
                            for reason in plan.blockers))
        self.assertEqual(target.read_bytes(), b"user edited this")

    def test_owned_path_that_became_a_directory_is_blocked(self):
        path = self.add("bin/app", b"original")
        path.unlink()
        path.mkdir()
        self.write_manifest({"bin/app": digest(b"original")})

        plan = plan_uninstall_file(self.root, self.manifest_path)

        self.assertFalse(plan.safe)
        self.assertTrue(any("not a regular file" in reason
                            for reason in plan.blockers))
        self.assertTrue(path.is_dir())

    # -- symlink and traversal safety ------------------------------------

    def test_symlinked_owned_file_blocked_and_target_preserved(self):
        outside = self.base / "outside.txt"
        outside.write_bytes(b"secret")
        link = self.root / "link.txt"
        self.symlink_or_skip(outside, link)
        self.write_manifest({"link.txt": digest(b"secret")})

        plan = plan_uninstall_file(self.root, self.manifest_path)

        self.assertFalse(plan.safe)
        self.assertEqual(plan.remove_files, ())
        self.assertTrue(any("symlink" in reason for reason in plan.blockers))
        self.assertEqual(outside.read_bytes(), b"secret")

    def test_symlinked_parent_directory_blocked(self):
        outside = self.base / "outside-dir"
        outside.mkdir()
        (outside / "file").write_bytes(b"content")
        linked_parent = self.root / "escape"
        self.symlink_or_skip(outside, linked_parent, target_is_directory=True)
        self.write_manifest({"escape/file": digest(b"content")})

        plan = plan_uninstall_file(self.root, self.manifest_path)

        self.assertFalse(plan.safe)
        self.assertTrue(any("symlinked parent" in reason
                            for reason in plan.blockers))
        self.assertEqual((outside / "file").read_bytes(), b"content")

    def test_symlinked_install_root_blocked(self):
        real_root = self.base / "real-root"
        real_root.mkdir()
        (real_root / "file").write_bytes(b"content")
        alias = self.base / "install-alias"
        self.symlink_or_skip(real_root, alias, target_is_directory=True)
        self.write_manifest({"file": digest(b"content")})

        plan = plan_uninstall(alias, read_manifest(self.manifest_path))

        self.assertFalse(plan.safe)
        self.assertTrue((real_root / "file").is_file())

    def test_path_traversal_and_absolute_paths_rejected(self):
        for rel in ("../escape", "/etc/passwd", "a/../b", "a/./b",
                    "a//b", "a\\b", "C:evil", ""):
            with self.subTest(path=rel):
                with self.assertRaises(UninstallIntegrityError):
                    normalize_manifest({
                        "schema": 1,
                        "files": {rel: digest(b"x")},
                    })

    # -- manifest validation ---------------------------------------------

    def test_malformed_manifests_rejected(self):
        bad = [
            [],
            {"files": {}},
            {"schema": 2, "files": {}},
            {"schema": True, "files": {}},
            {"schema": 1, "files": []},
            {"schema": 1, "files": {"a": "not-a-digest"}},
            {"schema": 1, "files": {"a": "A" * 64}},
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                with self.assertRaises(UninstallIntegrityError):
                    normalize_manifest(payload)

    def test_read_manifest_rejects_missing_symlink_and_oversize(self):
        with self.assertRaises(UninstallIntegrityError):
            read_manifest(self.base / "does-not-exist.json")

        real = self.base / "real.json"
        real.write_text(json.dumps({"schema": 1, "files": {}}), encoding="utf-8")
        link = self.base / "linked.json"
        self.symlink_or_skip(real, link)
        with self.assertRaises(UninstallIntegrityError):
            read_manifest(link)

        oversize = self.base / "oversize.json"
        oversize.write_text("x" * ((1 << 20) + 1), encoding="utf-8")
        with self.assertRaises(UninstallIntegrityError):
            read_manifest(oversize)

    def test_invalid_json_rejected(self):
        self.manifest_path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(UninstallIntegrityError):
            read_manifest(self.manifest_path)

    def test_digest_helper_matches_hashlib(self):
        self.assertEqual(_digest_hex(b"abc"), hashlib.sha256(b"abc").hexdigest())


if __name__ == "__main__":
    unittest.main()
