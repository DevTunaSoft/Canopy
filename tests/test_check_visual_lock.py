"""Tests for the read-only visual-lock checker."""
from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

from tools.check_visual_lock import AWAITING, check, main

ICON = b"approved-icon-bytes"
WALL = b"approved-wallpaper-bytes"
MANIFEST_PATH = Path("prototype/classic/assets/approved/manifest.json")


class VisualLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        icon = self.root / MANIFEST_PATH.parent / "icons" / "Browser_Option_3.png"
        icon.parent.mkdir(parents=True)
        icon.write_bytes(ICON)
        wall = self.root / MANIFEST_PATH.parent / "wallpaper" / "canopy-wave-preview.png"
        wall.parent.mkdir(parents=True)
        wall.write_bytes(WALL)
        self.manifest = {
            "icons": [{"name": "Browser", "path": "icons/Browser_Option_3.png",
                       "sha256": hashlib.sha256(ICON).hexdigest()}],
            "wallpaper": {"path": "wallpaper/canopy-wave-preview.png",
                          "sha256": hashlib.sha256(WALL).hexdigest()},
        }
        self._write_manifest(self.manifest)
        self.qml = self.root / "prototype/classic/DockTile.qml"
        self.qml.write_text('Image { source: "image://canopy-dock/Browser_Option_3.png" }',
                            encoding="utf-8")

    def _write_manifest(self, data):
        path = self.root / MANIFEST_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def _baseline(self, relative="prototype/classic/DockTile.qml", digest=None):
        data = {"files": [{"path": relative,
                           "sha256": digest or hashlib.sha256(
                               self.qml.read_bytes()).hexdigest()}]}
        path = self.root / "owner-baseline.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_approved_assets_without_baseline_await_owner(self):
        result = check(self.root)
        self.assertEqual(result["status"], AWAITING, result["problems"])
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["baseline"], "none")

    def test_tampered_asset_fails(self):
        (self.root / MANIFEST_PATH.parent / "icons" / "Browser_Option_3.png").write_bytes(
            b"replaced")
        result = check(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("modified" in p for p in result["problems"]))

    def test_missing_asset_fails(self):
        (self.root / MANIFEST_PATH.parent / "icons" / "Browser_Option_3.png").unlink()
        result = check(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("missing" in p for p in result["problems"]))

    def test_traversal_path_fails(self):
        data = dict(self.manifest)
        data["icons"] = [{"path": "../outside.png",
                          "sha256": hashlib.sha256(ICON).hexdigest()}]
        self._write_manifest(data)
        result = check(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("unsafe" in p for p in result["problems"]))

    def test_missing_manifest_fails(self):
        (self.root / MANIFEST_PATH).unlink()
        self.assertEqual(check(self.root)["status"], "FAIL")

    def test_owner_baseline_match_passes(self):
        result = check(self.root, self._baseline())
        self.assertEqual(result["status"], "PASS", result["problems"])

    def test_changed_protected_source_fails(self):
        baseline = self._baseline()
        self.qml.write_text("Image {}", encoding="utf-8")
        result = check(self.root, baseline)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("protected source changed" in p for p in result["problems"]))

    def test_unapproved_imagery_still_awaits_owner(self):
        self.qml.write_text('Image { source: "new-wallpaper.svg" }', encoding="utf-8")
        result = check(self.root, self._baseline())
        self.assertEqual(result["status"], AWAITING)
        self.assertEqual(result["problems"], [])

    def test_checker_never_writes_assets(self):
        icon = self.root / MANIFEST_PATH.parent / "icons" / "Browser_Option_3.png"
        before = icon.read_bytes()
        manifest_before = (self.root / MANIFEST_PATH).read_bytes()
        check(self.root)
        check(self.root, self._baseline())
        self.assertEqual(icon.read_bytes(), before)
        self.assertEqual((self.root / MANIFEST_PATH).read_bytes(), manifest_before)

    def test_cli_exit_zero_when_awaiting_owner(self):
        """CI gate must not fail merely because no owner baseline exists."""
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--root", str(self.root), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], AWAITING)

    def test_cli_exit_nonzero_on_tampered_asset(self):
        """CI gate must fail closed when an approved asset is modified."""
        (self.root / MANIFEST_PATH.parent / "icons" / "Browser_Option_3.png").write_bytes(
            b"tampered")
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--root", str(self.root), "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["status"], "FAIL")

    def test_foundation_ci_runs_visual_lock_gate(self):
        """The Foundation workflow must actually execute the visual-lock gate."""
        repo_root = Path(__file__).resolve().parent.parent
        workflow = (repo_root / ".github" / "workflows" / "foundation.yml").read_text(
            encoding="utf-8")
        self.assertIn("tools/check_visual_lock.py", workflow)
        self.assertIn("--json", workflow)


if __name__ == "__main__":
    unittest.main()
