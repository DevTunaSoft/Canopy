"""Metadata-only Shell Pack registry regression and negative-control tests."""

import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from canopy_core.registry import (
    MAX_PACK_DIRECTORIES,
    PackScan,
    ShellPackInfo,
    scan_shell_packs,
)
from tools.check_shell_pack import PackValidationError


class ShellPackRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "packs"
        self.root.mkdir()

    def add_pack(self, folder, pack_id, caps=None):
        directory = self.root / folder
        directory.mkdir()
        (directory / "ui").mkdir()
        (directory / "ui" / "Main.qml").write_text(
            "import QtQuick\nItem {}\n", encoding="utf-8"
        )
        manifest = {
            "manifest_version": 1,
            "id": pack_id,
            "name": "Pack " + folder,
            "description": "Independent sample presentation",
            "shell_api": 1,
            "kind": "presentation",
            "ui_engine": "qt-qml",
            "entrypoint": "ui/Main.qml",
            "capabilities": caps if caps is not None else ["dock"],
            "switch_strategy": "same-session",
            "permissions": [],
        }
        self.write_manifest(directory, manifest)
        return directory, manifest

    def write_manifest(self, folder, manifest):
        (folder / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def test_empty_catalog(self):
        report = scan_shell_packs(self.root)
        self.assertIsInstance(report, PackScan)
        self.assertEqual(report.packs, ())
        self.assertEqual(report.problems, ())
        self.assertEqual(report.checked_directories, 0)

    def test_more_than_two_independent_packs_with_no_core_changes(self):
        for folder, pack in (
            ("classic", "com.example.classic"),
            ("modern", "com.example.modern"),
            ("extra", "com.example.focus"),
        ):
            self.add_pack(folder, pack)
        report = scan_shell_packs(self.root)
        self.assertEqual(
            [p.pack_id for p in report.packs],
            ["com.example.classic", "com.example.focus", "com.example.modern"]
        )
        self.assertEqual(report.checked_directories, 3)
        self.assertEqual(report.problems, ())

    def test_metadata_only_and_immutable_catalog(self):
        self.add_pack("minimal", "com.example.minimal")
        report = scan_shell_packs(self.root)
        info = report.packs[0]
        self.assertIsInstance(info, ShellPackInfo)
        self.assertEqual(info.entrypoint, "ui/Main.qml")
        self.assertEqual(info.ui_engine, "qt-qml")
        self.assertEqual(info.shell_api, 1)
        self.assertEqual(info.capabilities, frozenset({"dock"}))
        with self.assertRaises(AttributeError):
            info.name = "mutated"

    def test_exact_id_selection(self):
        self.add_pack("minimal", "com.example.minimal")
        report = scan_shell_packs(self.root)
        self.assertIsNotNone(report.get("com.example.minimal"))
        self.assertIsNone(report.get("COM.EXAMPLE.MINIMAL"))
        self.assertIsNone(report.get("../../etc/passwd"))

    def test_capability_filter_never_grants_permissions(self):
        self.add_pack("small", "com.example.small", ["dock"])
        self.add_pack("large", "com.example.large", ["dock", "workspace-list"])
        report = scan_shell_packs(self.root)
        self.assertEqual(
            [p.pack_id for p in report.compatible(frozenset({"dock"}))],
            ["com.example.small"],
        )
        self.assertEqual(
            len(report.compatible(frozenset({"dock", "workspace-list"}))), 2
        )
        with self.assertRaises(TypeError):
            report.compatible(["dock"])

    def test_duplicate_ids_exclude_all_colliding_packs(self):
        self.add_pack("a", "com.example.duplicate")
        self.add_pack("b", "com.example.duplicate")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertEqual(len(report.problems), 2)
        self.assertTrue(all("duplicate" in p.reason for p in report.problems))

    def test_duplicate_id_does_not_prevent_other_valid_pack(self):
        self.add_pack("a", "com.example.duplicate")
        self.add_pack("b", "com.example.duplicate")
        self.add_pack("c", "com.example.distinct")
        report = scan_shell_packs(self.root)
        self.assertEqual([p.pack_id for p in report.packs], ["com.example.distinct"])

    def test_three_duplicate_ids_are_all_rejected(self):
        for name in ["a", "b", "c"]:
            self.add_pack(name, "com.example.duplicate")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertEqual(len(report.problems), 3)

    def test_invalid_manifest_skipped_not_executed(self):
        folder, manifest = self.add_pack("unsafe", "com.example.unsafe")
        manifest["permissions"] = ["run-shell"]
        self.write_manifest(folder, manifest)
        self.add_pack("safe", "com.example.safe")
        report = scan_shell_packs(self.root)
        self.assertEqual([p.pack_id for p in report.packs], ["com.example.safe"])
        self.assertEqual(len(report.problems), 1)
        self.assertIn("permissions", report.problems[0].reason)

    def test_symlink_to_outside_catalog_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "escape").symlink_to(Path(outside), target_is_directory=True)
            report = scan_shell_packs(self.root)
            self.assertEqual(report.packs, ())
            self.assertEqual(len(report.problems), 1)
            self.assertIn("symlink", report.problems[0].reason)

    def test_symlink_to_local_pack_rejected_not_duplicated(self):
        self.add_pack("real", "com.example.real")
        (self.root / "link").symlink_to(self.root / "real", target_is_directory=True)
        report = scan_shell_packs(self.root)
        self.assertEqual(len(report.packs), 1)
        self.assertEqual(len(report.problems), 1)

    def test_regular_files_not_interpreted_as_pack_code(self):
        (self.root / "README.md").write_text("just documentation", encoding="utf-8")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.checked_directories, 0)
        self.assertEqual(report.problems, ())

    def test_missing_catalog_rejected(self):
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            scan_shell_packs(self.root / "missing")

    def test_symlink_catalog_root_rejected(self):
        (Path(self.temp.name) / "alias").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            scan_shell_packs(Path(self.temp.name) / "alias")

    def test_catalog_directory_entry_bound(self):
        for n in range(MAX_PACK_DIRECTORIES + 1):
            (self.root / f"entry-{n:03}").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(PackValidationError, "64 entries"):
            scan_shell_packs(self.root)

    def test_exact_limit_supported(self):
        for n in range(MAX_PACK_DIRECTORIES):
            (self.root / f"readme-{n:03}").write_text("x", encoding="utf-8")
        report = scan_shell_packs(self.root)
        self.assertEqual(report.packs, ())
        self.assertEqual(report.problems, ())

    def test_unsupported_api_rejected_without_stopping_other_packs(self):
        folder, manifest = self.add_pack("future", "com.example.future")
        manifest["shell_api"] = 99
        self.write_manifest(folder, manifest)
        self.add_pack("current", "com.example.current")
        report = scan_shell_packs(self.root)
        self.assertEqual(len(report.packs), 1)
        self.assertEqual(report.packs[0].pack_id, "com.example.current")
        self.assertIn("unsupported shell_api", report.problems[0].reason)

    def test_cli_json_discovers_multiple_packs_without_execution(self):
        self.add_pack("classic", "com.example.classic")
        self.add_pack("modern", "com.example.modern")
        cmd = [sys.executable, "-m", "canopy_core", str(self.root), "--json"]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=False,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["count"], 2)
        self.assertTrue(result["metadata_only"])
        self.assertFalse(result["runtime_loading_enabled"])
        self.assertTrue(all(not row["trusted"] for row in result["packs"]))
        self.assertNotIn("directory", result["packs"][0])

    def test_cli_invalid_pack_fails_closed_with_structured_problem(self):
        folder, manifest = self.add_pack("bad", "com.example.bad")
        manifest["permissions"] = ["root"]
        self.write_manifest(folder, manifest)
        proc = subprocess.run(
            [sys.executable, "-m", "canopy_core", str(self.root), "--json"],
            capture_output=True, text=True, check=False,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["count"], 0)
        self.assertIn("permissions", report["problems"][0]["reason"])

    def test_cli_missing_catalog_nonzero(self):
        proc = subprocess.run(
            [sys.executable, "-m", "canopy_core",
             str(self.root / "not-installed")],
            capture_output=True, text=True, check=False,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("CANOPY_PACK_SCAN_FAIL", proc.stderr)

    def test_no_qml_execution_even_if_file_contains_executable_text(self):
        folder, manifest = self.add_pack("inert", "com.example.inert")
        malicious_effect = Path(self.temp.name) / "would-be-side-effect.txt"
        (folder / "ui" / "Main.qml").write_text(
            "DANGEROUS INVALID QML\n// would create " + str(malicious_effect),
            encoding="utf-8",
        )
        report = scan_shell_packs(self.root)
        self.assertEqual(len(report.packs), 1)
        self.assertFalse(malicious_effect.exists())
        # The metadata scanner only checks file existence and bounded size.
        # Running QML requires separate security, Qt parsing and trust gates.


if __name__ == "__main__":
    unittest.main()
