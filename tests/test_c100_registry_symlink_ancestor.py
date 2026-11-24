"""Regression tests: Shell Pack catalogs reached through symlinked ancestors.

The catalog and pack validators document that roots must be real local
directories and that symlinks are rejected. Checking only the final path
component lets a symlink in any ancestor alias the whole tree outside the
declared path; these tests fail closed on both public boundaries.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from canopy_core.registry import scan_shell_packs
from tools.check_shell_pack import PackValidationError, validate_pack


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_shell_pack.py"

MANIFEST = {
    "manifest_version": 1,
    "id": "com.example.aliased",
    "name": "Aliased Pack",
    "description": "catalog root reached through a symlinked ancestor",
    "shell_api": 1,
    "kind": "presentation",
    "ui_engine": "qt-qml",
    "entrypoint": "ui/Main.qml",
    "capabilities": ["dock"],
    "switch_strategy": "same-session",
    "permissions": [],
}


def make_pack(pack_dir):
    (pack_dir / "ui").mkdir(parents=True, exist_ok=True)
    (pack_dir / "ui" / "Main.qml").write_text(
        "import QtQuick\nItem {}\n", encoding="utf-8"
    )
    (pack_dir / "manifest.json").write_text(
        json.dumps(MANIFEST), encoding="utf-8"
    )


def symlink_or_skip(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        raise unittest.SkipTest(f"symlinks unavailable on this host: {exc}")


class SymlinkedAncestorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.real_root = self.base / "real_root"
        self.real_catalog = self.real_root / "catalog"
        make_pack(self.real_catalog / "packA")
        self.alias = self.base / "link_parent"
        symlink_or_skip(self.alias, self.real_root)
        self.declared_catalog = self.alias / "catalog"

    def test_scan_rejects_symlinked_ancestor_of_catalog_root(self):
        # The leaf itself is not a symlink; only its parent is.
        self.assertFalse(self.declared_catalog.is_symlink())
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            scan_shell_packs(self.declared_catalog)

    def test_validate_pack_rejects_symlinked_ancestor_of_pack_root(self):
        with self.assertRaisesRegex(PackValidationError, "real local directory"):
            validate_pack(self.declared_catalog / "packA")

    def test_scan_rejects_two_nested_symlinked_ancestors(self):
        outer = self.base / "outer_alias"
        symlink_or_skip(outer, self.alias)
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            scan_shell_packs(outer / "catalog")

    def test_scan_cli_via_aliased_ancestor_fails_closed(self):
        proc = subprocess.run(
            [sys.executable, "-m", "canopy_core", str(self.declared_catalog), "--json"],
            capture_output=True, text=True, check=False, cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("CANOPY_PACK_SCAN_FAIL", proc.stderr)

    def test_pack_checker_cli_via_aliased_ancestor_fails_closed(self):
        proc = subprocess.run(
            [sys.executable, str(CHECKER), str(self.declared_catalog / "packA")],
            capture_output=True, text=True, check=False, cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("SHELL_PACK_FAIL", proc.stderr)

    def test_real_catalog_without_symlink_components_accepted(self):
        report = scan_shell_packs(self.real_catalog)
        self.assertEqual([p.pack_id for p in report.packs], [MANIFEST["id"]])
        self.assertEqual(report.problems, ())

    def test_relative_catalog_path_without_symlinks_accepted(self):
        # Walk from an anchor, not the current directory string: a relative
        # catalog must keep working when none of its components is a link.
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(str(self.real_root))
        report = scan_shell_packs(Path("catalog"))
        self.assertEqual([p.pack_id for p in report.packs], [MANIFEST["id"]])

    def test_symlink_catalog_leaf_still_rejected(self):
        leaf_alias = self.base / "leaf_alias"
        symlink_or_skip(leaf_alias, self.real_catalog)
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            scan_shell_packs(leaf_alias)

    def test_missing_ancestor_component_rejected(self):
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            scan_shell_packs(self.base / "missing" / "catalog")


if __name__ == "__main__":
    unittest.main()
