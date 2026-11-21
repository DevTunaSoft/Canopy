"""Offline regression checks for community-extensible Shell Pack v1 metadata.

No runtime loader, trusted package installer or live switching is claimed.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.check_shell_pack import PackValidationError, validate_pack

ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "examples" / "shell-pack-starter"
CHECKER = ROOT / "tools" / "check_shell_pack.py"


class ShellPackContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "new-pack"
        (self.root / "ui").mkdir(parents=True)
        (self.root / "ui" / "Main.qml").write_text(
            "import QtQuick\nItem {}\n", encoding="utf-8"
        )
        self.manifest = json.loads(
            (STARTER / "manifest.json").read_text(encoding="utf-8")
        )
        self.write_manifest()

    def write_manifest(self):
        (self.root / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2), encoding="utf-8"
        )

    def reject(self, key, value, message):
        self.manifest[key] = value
        self.write_manifest()
        with self.assertRaisesRegex(PackValidationError, message):
            validate_pack(self.root)

    def test_checked_in_starter_is_valid(self):
        self.assertEqual(validate_pack(STARTER)["id"],
                         "org.example.canopy.minimal")

    def test_copy_and_rebrand_without_core_changes(self):
        self.manifest["id"] = "com.community.shell.calm"
        self.manifest["name"] = "Calm Workspace"
        self.manifest["capabilities"] = ["top-bar", "workspace-list"]
        self.write_manifest()
        self.assertEqual(validate_pack(self.root)["name"], "Calm Workspace")

    def test_future_unsupported_host_api_fails_closed(self):
        self.reject("shell_api", 2, "unsupported shell_api")

    def test_boolean_host_api_fails_closed(self):
        self.reject("shell_api", True, "unsupported shell_api")

    def test_unknown_manifest_schema_fails_closed(self):
        self.reject("manifest_version", 2, "unsupported manifest_version")

    def test_duplicates_in_capabilities_rejected(self):
        self.reject("capabilities", ["dock", "dock"], "capabilities")

    def test_unknown_capability_rejected(self):
        self.reject("capabilities", ["arbitrary-process-execution"], "capabilities")

    def test_reject_nonempty_permissions(self):
        self.reject("permissions", ["root"], "permissions")

    def test_reject_invalid_permission_shape(self):
        self.reject("permissions", "none", "permissions")

    def test_reserved_core_identity_rejected(self):
        self.reject("id", "org.canopy.shell.classic", "nonreserved")

    def test_future_toolkit_not_implied_supported(self):
        self.reject("ui_engine", "gtk", "only supports Qt")

    def test_future_full_session_not_implied_supported(self):
        self.reject("kind", "compositor", "presentation")

    def test_entrypoint_path_traversal_rejected(self):
        self.reject("entrypoint", "ui/../../etc/passwd", "safe relative")

    def test_entrypoint_absolute_path_rejected(self):
        self.reject("entrypoint", "/tmp/evil.qml", "safe relative")

    def test_entrypoint_uri_rejected(self):
        self.reject("entrypoint", "https://invalid.test/Main.qml", "safe relative")

    def test_missing_entrypoint_rejected(self):
        self.reject("entrypoint", "ui/Absent.qml", "entrypoint QML file is missing")

    def test_symlinked_entrypoint_rejected(self):
        target = self.root / "ui" / "Main.qml"
        target.unlink()
        target.symlink_to(STARTER / "ui" / "Main.qml")
        with self.assertRaisesRegex(PackValidationError, "symlinks"):
            validate_pack(self.root)

    def test_symlinked_manifest_rejected(self):
        path = self.root / "manifest.json"
        path.unlink()
        path.symlink_to(STARTER / "manifest.json")
        with self.assertRaisesRegex(PackValidationError, "regular local file"):
            validate_pack(self.root)

    def test_duplicate_json_keys_rejected(self):
        path = self.root / "manifest.json"
        path.write_text(
            '{"id":"com.example.test","id":"com.other.test"}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(PackValidationError, "duplicate JSON key"):
            validate_pack(self.root)

    def test_unknown_fields_rejected(self):
        self.reject("execute_script", "/bin/sh", "unexpected manifest fields")

    def test_manifest_size_is_bounded(self):
        (self.root / "manifest.json").write_bytes(b" " * 16_385)
        with self.assertRaisesRegex(PackValidationError, "16 KiB"):
            validate_pack(self.root)

    def test_newline_in_display_name_rejected(self):
        self.reject("name", "Fake\nName", "clean string")

    def test_empty_capabilities_rejected(self):
        self.reject("capabilities", [], "capabilities")

    def test_cli_accepts_starter_and_rejects_missing_pack(self):
        good = subprocess.run(
            [sys.executable, str(CHECKER), str(STARTER)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn("SHELL_PACK_MANIFEST_PASS", good.stdout)
        bad = subprocess.run(
            [sys.executable, str(CHECKER), str(self.root / "missing")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(bad.returncode, 1)
        self.assertIn("SHELL_PACK_FAIL", bad.stderr)


if __name__ == "__main__":
    unittest.main()
