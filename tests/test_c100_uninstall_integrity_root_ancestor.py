"""Regression tests: uninstall planning must reject symlinked path ancestors.

``plan_uninstall`` blocks a symlinked install *root* and a symlinked parent
*inside* the root, but accepted a real root reached through an aliased parent.
``read_manifest`` likewise blocked a symlinked manifest file but accepted a
real manifest reached through an aliased parent. In both cases the planner
could propose removing files whose real location is outside the declared
tree, contradicting the module's fail-closed "unsafe path" contract.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from canopy_features.installer.uninstall_integrity import (
    UninstallIntegrityError,
    plan_uninstall,
    plan_uninstall_file,
    read_manifest,
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class UninstallRootAncestorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="canopy-uninstall-ancestor-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

        self.real_parent = self.base / "real-parent"
        self.real_root = self.real_parent / "install"
        self.real_root.mkdir(parents=True)
        (self.real_root / "owned.txt").write_bytes(b"owned")

        self.alias_parent = self.base / "alias-parent"
        self.alias_parent.mkdir()
        try:
            (self.alias_parent / "link").symlink_to(
                self.real_parent, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("directory symlinks unavailable: " + str(exc))
        self.aliased_root = self.alias_parent / "link" / "install"

        self.manifest = {"schema": 1,
                         "files": {"owned.txt": digest(b"owned")}}
        self.manifest_path = self.base / "ownership.json"
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_symlinked_ancestor_of_install_root_blocks_plan(self):
        # The final component is a real directory; only an ancestor is aliased.
        self.assertFalse(self.aliased_root.is_symlink())
        plan = plan_uninstall(self.aliased_root, self.manifest)
        self.assertFalse(plan.safe)
        self.assertEqual(plan.remove_files, ())
        self.assertTrue(any("ancestor" in reason and "symlink" in reason
                            for reason in plan.blockers), plan.blockers)

    def test_plan_uninstall_file_blocks_aliased_root(self):
        plan = plan_uninstall_file(self.aliased_root, self.manifest_path)
        self.assertFalse(plan.safe)
        self.assertEqual(plan.remove_files, ())
        self.assertTrue((self.real_root / "owned.txt").is_file())

    def test_symlinked_ancestor_of_manifest_rejected(self):
        real_cfg = self.base / "real-cfg"
        real_cfg.mkdir()
        cfg = real_cfg / "ownership.json"
        cfg.write_text(json.dumps(self.manifest), encoding="utf-8")
        alias_cfg_parent = self.base / "cfg-alias"
        alias_cfg_parent.mkdir()
        try:
            (alias_cfg_parent / "link").symlink_to(
                real_cfg, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("directory symlinks unavailable: " + str(exc))
        aliased_manifest = alias_cfg_parent / "link" / "ownership.json"
        self.assertFalse(aliased_manifest.is_symlink())
        with self.assertRaisesRegex(UninstallIntegrityError, "ancestor"):
            read_manifest(aliased_manifest)

    def test_dotdot_in_root_refused(self):
        tricky = self.alias_parent / ".." / "alias-parent" / "link" / "install"
        plan = plan_uninstall(tricky, self.manifest)
        self.assertFalse(plan.safe)
        self.assertEqual(plan.remove_files, ())

    def test_leaf_root_symlink_still_blocked_with_original_reason(self):
        alias = self.base / "root-alias"
        try:
            alias.symlink_to(self.real_root, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("directory symlinks unavailable: " + str(exc))
        plan = plan_uninstall(alias, self.manifest)
        self.assertFalse(plan.safe)
        self.assertTrue(any("install root is a symlink" in reason
                            for reason in plan.blockers), plan.blockers)

    def test_real_paths_still_accepted(self):
        plan = plan_uninstall_file(self.real_root, self.manifest_path)
        self.assertTrue(plan.safe)
        self.assertEqual(plan.remove_files, ("owned.txt",))
        self.assertEqual(plan.blockers, ())

    def test_missing_root_component_does_not_crash(self):
        # A missing component stops the walk; normal MISSING-file handling
        # still applies rather than an ancestor-symlink blocker.
        missing = self.real_parent / "not-created" / "install"
        plan = plan_uninstall(missing, self.manifest)
        self.assertFalse(plan.safe)
        self.assertTrue(any("MISSING" in reason for reason in plan.blockers),
                        plan.blockers)


if __name__ == "__main__":
    unittest.main()
