"""Offline unit tests: reverse only partially installed, owned files."""
from pathlib import Path
import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

from canopy_features.installer import rollback_ownership as rollback
from tools import register_classic_preview as menu


def _digest(data):
    return hashlib.sha256(data).hexdigest()


class RollbackOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.desktop = self.base / "org.canopy.ClassicPreview.desktop"
        self.manifest = self.base / "ownership.json"
        self.desktop_bytes = b"owned desktop payload"
        self.manifest_bytes = b'{"schema":1}'

    def _owned(self, path, data):
        return rollback.OwnedFile(path, _digest(data))

    def _pair(self):
        return [self._owned(self.desktop, self.desktop_bytes),
                self._owned(self.manifest, self.manifest_bytes)]

    def _reconcile(self):
        return rollback.reconcile_partial(self._pair())

    def test_no_poll_or_network_imports(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/installer/rollback_ownership.py").read_text()
        for banned in ("QTimer", "asyncio", "subprocess", "import socket",
                       "Thread(", "importlib", "time.sleep"):
            with self.subTest(token=banned):
                self.assertNotIn(banned, code)

    def test_invalid_owned_set_rejected(self):
        def empty():
            return rollback.reconcile_partial([])

        def relative():
            return rollback.reconcile_partial(
                [rollback.OwnedFile(Path("relative"), _digest(b"x"))])

        def not_path():
            return rollback.reconcile_partial(
                [rollback.OwnedFile(str(self.desktop), _digest(b"x"))])

        def bad_sha():
            return rollback.reconcile_partial(
                [rollback.OwnedFile(self.desktop, "bad")])

        def duplicate():
            return rollback.reconcile_partial(
                [self._owned(self.desktop, b"x"),
                 self._owned(self.desktop, b"y")])

        def wrong_type():
            return rollback.reconcile_partial(["not-an-owned-file"])

        for action in (empty, relative, not_path, bad_sha, duplicate,
                       wrong_type):
            with self.subTest(action=action.__name__):
                with self.assertRaises(rollback.RollbackError):
                    action()
        self.assertFalse(self.desktop.exists())

    def test_interrupted_install_removes_only_existing_owned_file(self):
        self.desktop.write_bytes(self.desktop_bytes)
        result = self._reconcile()
        self.assertTrue(result.partial)
        self.assertEqual(result.removed, (self.desktop,))
        self.assertEqual(result.missing, (self.manifest,))
        self.assertEqual(result.kept_foreign, ())
        self.assertEqual(result.retained, ())
        self.assertFalse(self.desktop.exists())

    def test_foreign_file_at_owned_path_is_preserved(self):
        self.desktop.write_bytes(self.desktop_bytes)
        foreign = b"another program wrote this"
        self.manifest.write_bytes(foreign)
        result = self._reconcile()
        self.assertTrue(result.partial)
        self.assertEqual(result.removed, (self.desktop,))
        self.assertEqual(result.kept_foreign, (self.manifest,))
        self.assertEqual(result.missing, ())
        self.assertFalse(self.desktop.exists())
        self.assertEqual(self.manifest.read_bytes(), foreign)

    def test_foreign_directory_oversized_and_unreadable_preserved(self):
        for kind in ("directory", "oversized", "unreadable"):
            with self.subTest(kind=kind):
                temporary = tempfile.TemporaryDirectory()
                self.addCleanup(temporary.cleanup)
                base = Path(temporary.name)
                desktop = base / "desktop"
                manifest = base / "ownership.json"
                desktop_data = b"abc"
                manifest_data = b"x" * 32
                desktop.write_bytes(desktop_data)

                if kind == "directory":
                    manifest.mkdir()
                    result = rollback.reconcile_partial([
                        rollback.OwnedFile(desktop, _digest(desktop_data)),
                        rollback.OwnedFile(manifest, _digest(manifest_data)),
                    ])
                elif kind == "oversized":
                    manifest.write_bytes(manifest_data)
                    with patch.object(rollback, "MAX_OWNED_BYTES", 8):
                        result = rollback.reconcile_partial([
                            rollback.OwnedFile(desktop, _digest(desktop_data)),
                            rollback.OwnedFile(manifest, _digest(manifest_data)),
                        ])
                else:
                    manifest.write_bytes(manifest_data)
                    original = Path.open

                    def refuse(path, *args, **kwargs):
                        if path == manifest:
                            raise OSError("simulated permission denial")
                        return original(path, *args, **kwargs)

                    with patch.object(Path, "open", autospec=True,
                                      side_effect=refuse):
                        result = rollback.reconcile_partial([
                            rollback.OwnedFile(desktop, _digest(desktop_data)),
                            rollback.OwnedFile(manifest, _digest(manifest_data)),
                        ])

                self.assertTrue(result.partial)
                self.assertEqual(result.removed, (desktop,))
                self.assertEqual(result.kept_foreign, (manifest,))
                self.assertFalse(desktop.exists())
                if kind == "directory":
                    self.assertTrue(manifest.is_dir())
                else:
                    self.assertEqual(manifest.read_bytes(), manifest_data)

    def test_complete_install_is_left_intact(self):
        self.desktop.write_bytes(self.desktop_bytes)
        self.manifest.write_bytes(self.manifest_bytes)
        result = self._reconcile()
        self.assertFalse(result.partial)
        self.assertEqual(result.removed, ())
        self.assertEqual(result.retained, (self.desktop, self.manifest))
        self.assertTrue(self.desktop.is_file())
        self.assertTrue(self.manifest.is_file())

    def test_nothing_installed_is_noop(self):
        result = self._reconcile()
        self.assertFalse(result.partial)
        self.assertEqual(result.removed, ())
        self.assertEqual(result.missing, (self.desktop, self.manifest))

    def test_unrelated_files_and_parent_directories_never_touched(self):
        sentinel = self.base / "user-notes.txt"
        sentinel.write_bytes(b"keep")
        self.desktop.write_bytes(self.desktop_bytes)
        self._reconcile()
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertTrue(self.base.is_dir())

    def test_symlink_at_owned_path_is_foreign_when_supported(self):
        target = self.base / "elsewhere.json"
        target.write_bytes(self.manifest_bytes)
        self.desktop.write_bytes(self.desktop_bytes)
        try:
            self.manifest.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlink creation unavailable: " + str(exc))
        result = self._reconcile()
        self.assertTrue(result.partial)
        self.assertEqual(result.kept_foreign, (self.manifest,))
        self.assertTrue(self.manifest.is_symlink())
        self.assertEqual(target.read_bytes(), self.manifest_bytes)
        self.assertFalse(self.desktop.exists())

    def test_reuses_real_installer_ownership_and_interrupt(self):
        home = self.base / "xdg data with spaces"
        home.mkdir()
        binary = self.base / "canopy-classic"
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o755)
        if hasattr(os, "geteuid"):
            euid = patch("tools.register_classic_preview.os.geteuid",
                         return_value=1000)
            euid.start()
            self.addCleanup(euid.stop)
        # The tool's cross-platform Exec quoting rejects Windows backslashes;
        # this test reuses only its ownership layout and exact-byte marker.
        quote = patch("tools.register_classic_preview._quote",
                      side_effect=lambda value: '"' + value + '"')
        quote.start()
        self.addCleanup(quote.stop)
        desktop = menu.install(home, binary)
        manifest = menu.paths(home)["manifest"]
        other = menu.paths(home)["apps"] / "another.desktop"
        other.write_bytes(b"unrelated entry")

        owned = [
            rollback.OwnedFile(desktop, _digest(desktop.read_bytes())),
            rollback.OwnedFile(manifest, _digest(manifest.read_bytes())),
        ]
        manifest.unlink()  # interrupted before the ownership marker was written

        result = rollback.reconcile_partial(owned)
        self.assertTrue(result.partial)
        self.assertEqual(result.removed, (desktop,))
        self.assertEqual(result.missing, (manifest,))
        self.assertFalse(desktop.exists())
        self.assertEqual(other.read_bytes(), b"unrelated entry")
        self.assertEqual(menu.status(home), "NOT_INSTALLED")


if __name__ == "__main__":
    unittest.main()
