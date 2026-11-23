"""Offline tests for the reversible-uninstall planner.

No real Mint session, Qt binary, package manager or privileged action is used.
"""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canopy_features.installer import uninstall_integrity as planner
from tools import register_classic_preview as menu


OWNER = "org.canopy.classic"
DESKTOP = "applications/org.canopy.ClassicPreview.desktop"


class UninstallIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "install root"
        self.root.mkdir()
        self.manifest = self.root / "ownership.json"

    def write(self, relative, data):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def record(self, relative, data):
        self.write(relative, data)
        return {relative: hashlib.sha256(data).hexdigest()}

    def save(self, files, owner=OWNER, schema=planner.SCHEMA, raw=None):
        if raw is None:
            raw = json.dumps({"schema": schema, "owner": owner, "files": files})
        self.manifest.write_text(raw, encoding="utf-8")

    def plan(self, **kwargs):
        return planner.plan_uninstall(self.root, self.manifest, **kwargs)

    def test_plan_removes_only_exact_owned_files(self):
        first = self.record(DESKTOP, b"owned desktop entry")
        second = self.record("canopy/classic-preview/asset.bin", b"owned asset")
        unrelated = self.write("applications/another-program.desktop", b"user entry")
        note = self.write("notes.txt", b"keep me")
        self.save({**first, **second})

        plan = self.plan(expected_owner=OWNER)

        self.assertTrue(plan.executable)
        self.assertEqual(plan.blockers, ())
        self.assertEqual(plan.removals, tuple(sorted(first) + sorted(second)))
        self.assertTrue(all(a.decision == planner.REMOVE for a in plan.actions))
        self.assertTrue(all(a.actual_sha256 == a.expected_sha256 for a in plan.actions))
        planned = {a.path for a in plan.actions}
        self.assertNotIn("applications/another-program.desktop", planned)
        self.assertNotIn("notes.txt", planned)
        # Planning is read-only: nothing was deleted, including directories.
        self.assertTrue(unrelated.is_file())
        self.assertTrue(note.is_file())
        self.assertTrue((self.root / "applications").is_dir())
        self.assertEqual(unrelated.read_bytes(), b"user entry")

    def test_missing_file_is_skipped_without_blocking(self):
        present = self.record("a.txt", b"still here")
        gone_digest = hashlib.sha256(b"deleted earlier").hexdigest()
        self.save({**present, "b.txt": gone_digest})

        plan = self.plan()

        self.assertTrue(plan.executable)
        self.assertEqual(plan.removals, ("a.txt",))
        by_path = {a.path: a for a in plan.actions}
        self.assertEqual(by_path["b.txt"].decision, planner.MISSING)
        self.assertIn("missing", by_path["b.txt"].reason)
        self.assertFalse((self.root / "b.txt").exists())
        self.assertEqual((self.root / "a.txt").read_bytes(), b"still here")

    def test_ownership_mismatch_blocks_whole_plan(self):
        original = b"exact installed bytes"
        self.record("a.txt", original)
        self.save({"a.txt": hashlib.sha256(original).hexdigest()})
        self.write("a.txt", b"user note added")

        plan = self.plan()

        self.assertFalse(plan.executable)
        self.assertEqual(plan.removals, ())
        self.assertEqual(len(plan.blockers), 1)
        action = plan.actions[0]
        self.assertEqual(action.decision, planner.MISMATCH)
        self.assertNotEqual(action.actual_sha256, action.expected_sha256)
        self.assertEqual(action.actual_sha256,
                         hashlib.sha256(b"user note added").hexdigest())
        self.assertEqual((self.root / "a.txt").read_bytes(), b"user note added")
        self.assertTrue(self.manifest.is_file())

    def test_symlinked_record_is_never_planned(self):
        outside = self.base / "private.txt"
        outside.write_bytes(b"private")
        link = self.root / "link.txt"
        link.symlink_to(outside)
        self.save({"link.txt": hashlib.sha256(b"private").hexdigest()})

        plan = self.plan()

        self.assertFalse(plan.executable)
        self.assertEqual(plan.removals, ())
        self.assertEqual(plan.actions[0].decision, planner.UNSAFE)
        self.assertTrue(link.is_symlink())
        self.assertEqual(outside.read_bytes(), b"private")

    def test_symlinked_parent_directory_is_never_followed(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "file.txt").write_bytes(b"do not delete")
        (self.root / "sub").symlink_to(outside, target_is_directory=True)
        self.save({"sub/file.txt": hashlib.sha256(b"do not delete").hexdigest()})

        plan = self.plan()

        self.assertFalse(plan.executable)
        self.assertEqual(plan.actions[0].decision, planner.UNSAFE)
        self.assertEqual((outside / "file.txt").read_bytes(), b"do not delete")

    def test_directory_record_is_not_a_removal(self):
        self.write("keepdir/user.txt", b"unrelated")
        self.save({"keepdir": "0" * 64})

        plan = self.plan()

        self.assertFalse(plan.executable)
        self.assertEqual(plan.removals, ())
        self.assertEqual(plan.actions[0].decision, planner.NOT_REGULAR)
        self.assertEqual((self.root / "keepdir" / "user.txt").read_bytes(), b"unrelated")

    def test_traversal_and_non_portable_paths_rejected(self):
        outside = self.base / "outside.txt"
        outside.write_bytes(b"precious")
        for relative in ("../outside.txt", "/etc/passwd", "a/../../outside.txt",
                         "sub\\outside.txt", "a//outside.txt", "CON"):
            with self.subTest(relative=relative):
                self.save({relative: "0" * 64})
                with self.assertRaisesRegex(planner.RegistrationError,
                                            "path|absolute|traversal|reserved"):
                    self.plan()
        self.assertEqual(outside.read_bytes(), b"precious")

    def test_invalid_manifest_fields_rejected(self):
        cases = (
            '{"schema":2,"files":{}}',
            '{"schema":true,"files":{}}',
            '{"schema":1,"files":{"a.txt":"bad"}}',
            '{"schema":1,"owner":"","files":{}}',
            '{"schema":1,"files":[],"owner":"org.canopy.classic"}',
            "not json at all",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.save({}, raw=raw)
                with self.assertRaises(planner.RegistrationError):
                    self.plan()

    def test_expected_owner_mismatch_rejected(self):
        self.record("a.txt", b"owned")
        self.save({"a.txt": hashlib.sha256(b"owned").hexdigest()},
                  owner="org.someone.else")
        with self.assertRaisesRegex(planner.RegistrationError, "ownership mismatch"):
            self.plan(expected_owner=OWNER)
        self.assertEqual((self.root / "a.txt").read_bytes(), b"owned")

    def test_missing_or_symlinked_manifest_rejected(self):
        self.manifest.unlink(missing_ok=True)
        with self.assertRaises(planner.RegistrationError):
            self.plan()
        real = self.base / "real.json"
        real.write_text('{"schema":1,"files":{}}', encoding="utf-8")
        self.manifest.symlink_to(real)
        with self.assertRaises(planner.RegistrationError):
            self.plan()
        self.assertTrue(real.is_file())

    def test_large_file_is_hashed_in_fixed_chunks(self):
        data = bytes(range(256)) * 24
        self.record("big.bin", data)
        self.save({"big.bin": hashlib.sha256(data).hexdigest()})
        with patch.object(planner, "CHUNK", 7):
            plan = self.plan()
        self.assertEqual(plan.removals, ("big.bin",))
        self.assertEqual(plan.actions[0].actual_sha256,
                         hashlib.sha256(data).hexdigest())

    def test_existing_classic_preview_marker_is_reused(self):
        # Build a marker in the exact format read by the existing tool.
        # Running tools/register_classic_preview.py install is not portable to
        # a Windows host: its desktop Exec quoting rejects "\\" and ":".
        home = self.base / "xdg home"
        apps = home / "applications"
        apps.mkdir(parents=True)
        payload = b"[Desktop Entry]\nType=Application\nName=Canopy Classic Preview\n"
        desktop = apps / menu.DESKTOP
        desktop.write_bytes(payload)
        folder = home / "canopy" / "classic-preview"
        folder.mkdir(parents=True)
        marker = {"schema": planner.SCHEMA, "sha256": menu._sha(payload)}
        marker_file = folder / "ownership.json"
        marker_file.write_text(json.dumps(marker), encoding="utf-8")
        self.assertEqual(menu.status(home), "INSTALLED")

        shared = self.base / "shared-ownership.json"
        shared.write_text(json.dumps({
            "schema": planner.SCHEMA,
            "owner": OWNER,
            "files": {DESKTOP: marker["sha256"]},
        }), encoding="utf-8")
        plan = planner.plan_uninstall(home, shared, expected_owner=OWNER)

        self.assertTrue(plan.executable)
        self.assertEqual(plan.removals, (DESKTOP,))
        self.assertEqual(plan.actions[0].actual_sha256, marker["sha256"])
        self.assertEqual(desktop.read_bytes(), payload)
        # The existing ownership marker is unrelated to this new manifest.
        self.assertTrue(marker_file.is_file())


if __name__ == "__main__":
    unittest.main()
