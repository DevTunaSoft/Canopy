"""Shell Pack developer scaffolding tests; never execute generated QML."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from canopy_core.registry import scan_shell_packs
from canopy_core.scaffold import STARTER, create_pack
from tools.check_shell_pack import PackValidationError, validate_pack


ROOT = Path(__file__).resolve().parents[1]


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.catalog = Path(self.temp.name) / "shells"
        self.catalog.mkdir()

    def create(self, pack_id="com.example.focus", name="Focus Desktop",
               description="Distraction-free interface", caps=("dock",)):
        return create_pack(self.catalog, pack_id, name, description, caps)

    def test_creates_working_manifest_and_safe_qml_stub(self):
        output = self.create()
        descriptor = validate_pack(output)
        self.assertEqual(descriptor["id"], "com.example.focus")
        self.assertEqual(descriptor["name"], "Focus Desktop")
        self.assertEqual(descriptor["capabilities"], ["dock"])
        self.assertEqual(descriptor["permissions"], [])
        self.assertTrue((output / "ui" / "Main.qml").is_file())
        self.assertEqual(
            (output / "ui" / "Main.qml").read_bytes(),
            (STARTER / "ui" / "Main.qml").read_bytes(),
        )
        self.assertIn("not an installed", (output / "README.md").read_text().lower())

    def test_three_original_packs_without_editing_shared_core(self):
        self.create("com.example.classic", "Classic")
        self.create("com.example.modern", "Modern")
        self.create("com.example.focus", "Focus")
        found = scan_shell_packs(self.catalog)
        self.assertEqual(len(found.packs), 3)
        self.assertEqual(found.problems, ())

    def test_repeat_same_pack_id_never_overwrites(self):
        output = self.create()
        manifest_before = (output / "manifest.json").read_bytes()
        with self.assertRaisesRegex(PackValidationError, "already exists"):
            self.create(name="Overwriting Attempt")
        self.assertEqual((output / "manifest.json").read_bytes(), manifest_before)

    def test_explicit_existing_target_directory_is_preserved(self):
        target = self.catalog / "com.example.focus"
        target.mkdir()
        (target / "owner.txt").write_text("precious", encoding="utf-8")
        with self.assertRaises(PackValidationError):
            self.create()
        self.assertEqual((target / "owner.txt").read_text(), "precious")

    def test_path_traversal_pack_id_rejected(self):
        for identity in ("../escape", "/tmp/escape", "com..example", "COM.example.bad"):
            with self.subTest(identity=identity):
                with self.assertRaises(PackValidationError):
                    self.create(pack_id=identity)
        self.assertEqual(list(self.catalog.iterdir()), [])

    def test_reserved_host_namespace_rejected(self):
        with self.assertRaisesRegex(PackValidationError, "reserved"):
            self.create(pack_id="org.canopy.shell.classic")

    def test_empty_or_control_character_name_rejected(self):
        for name in ("", "  ", "Name\nSpoof", " x ", "Null\0Byte"):
            with self.subTest(name=name):
                with self.assertRaises(PackValidationError):
                    self.create(name=name)

    def test_malformed_capability_rejected(self):
        for caps in ([], ["root"], ["dock", "dock"], ["dock", "exec"]):
            with self.subTest(caps=caps):
                with self.assertRaises(PackValidationError):
                    self.create(caps=caps)

    def test_catalog_symlink_root_rejected(self):
        alias = Path(self.temp.name) / "symlink"
        alias.symlink_to(self.catalog, target_is_directory=True)
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            create_pack(alias, "com.example.focus", "Focus", "Description")

    def test_catalog_missing_rejected(self):
        with self.assertRaisesRegex(PackValidationError, "real directory"):
            create_pack(self.catalog / "missing", "com.example.focus", "Focus", "Desc")

    def test_invalid_existing_manifest_blocks_creation(self):
        existing = self.catalog / "bad"
        existing.mkdir()
        (existing / "manifest.json").write_text('{"permissions":["root"]}', encoding="utf-8")
        with self.assertRaisesRegex(PackValidationError, "invalid or duplicate"):
            self.create()
        self.assertFalse((self.catalog / "com.example.focus").exists())

    def test_symlink_target_is_never_followed_or_overwritten(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        link = self.catalog / "com.example.focus"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(PackValidationError):
            self.create()
        self.assertTrue(link.is_symlink())
        self.assertEqual(list(outside.iterdir()), [])

    def test_rolls_back_partial_output_on_write_failure(self):
        with patch("canopy_core.scaffold.shutil.copyfile",
                   side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.create()
        self.assertFalse((self.catalog / "com.example.focus").exists())

    def test_checked_in_template_unchanged(self):
        source_before = (STARTER / "manifest.json").read_bytes()
        self.create()
        self.assertEqual((STARTER / "manifest.json").read_bytes(), source_before)

    def test_cli_creates_one_pack_then_fails_duplicate(self):
        args = [
            sys.executable, "-m", "canopy_core.scaffold", str(self.catalog),
            "--id", "com.example.focus", "--name", "Focus Workspace",
            "--capability", "dock", "--capability", "workspace-list",
        ]
        first = subprocess.run(args, capture_output=True, text=True,
                               check=False, cwd=ROOT)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("CANOPY_SCAFFOLD_PASS", first.stdout)
        self.assertEqual(
            json.loads((self.catalog / "com.example.focus" / "manifest.json").read_text())[
                "capabilities"
            ],
            ["dock", "workspace-list"],
        )
        second = subprocess.run(args, capture_output=True, text=True,
                                check=False, cwd=ROOT)
        self.assertEqual(second.returncode, 1)
        self.assertIn("CANOPY_SCAFFOLD_FAIL", second.stderr)

    def test_catalog_limit_refuses_another_pack(self):
        for idx in range(64):
            (self.catalog / f"readme-{idx:03}").mkdir()
            # Invalid dirs cause an even earlier fail-closed check.
        with self.assertRaises(PackValidationError):
            self.create()
        self.assertFalse((self.catalog / "com.example.focus").exists())


if __name__ == "__main__":
    unittest.main()
