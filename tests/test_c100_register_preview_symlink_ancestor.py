"""Regression tests: symlinked ancestors must not bypass Classic preview guards.

The registration tool checks only the final path component for symlinks, so a
real file/directory reached through an aliased parent resolves outside the
declared tree while the caller still records the declared path. These tests
pin the fail-closed contract at both internal boundaries (resources and
registration directories) and cover the end-to-end install on POSIX, where
the desktop Exec writer accepts the path syntax.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import register_classic_preview as menu


class PreviewSymlinkAncestorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.real = self.base / "real"
        self.real.mkdir()
        self.alias = self.base / "alias"
        try:
            self.alias.symlink_to(self.real, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinked directories unavailable: {exc}")
        self.home = self.base / "xdg-home"
        self.home.mkdir()
        self.binary = self.real / "canopy-classic"
        self.binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    def test_resource_binary_behind_symlinked_ancestor_rejected(self):
        with self.assertRaisesRegex(menu.RegistrationError, "non-symlink"):
            menu._resource(str(self.alias / "canopy-classic"), "Canopy binary")

    def test_resource_art_directory_behind_symlinked_ancestor_rejected(self):
        (self.real / "approved-art").mkdir()
        with self.assertRaisesRegex(menu.RegistrationError, "non-symlink"):
            menu._resource(str(self.alias / "approved-art"),
                           "approved artwork", directory=True)

    def test_resource_wallpaper_behind_symlinked_ancestor_rejected(self):
        (self.real / "wallpaper.png").write_bytes(b"wallpaper")
        with self.assertRaisesRegex(menu.RegistrationError, "non-symlink"):
            menu._resource(str(self.alias / "wallpaper.png"), "wallpaper")

    def test_safe_folders_rejects_home_behind_symlinked_ancestor(self):
        (self.real / "xdg-home").mkdir()
        with self.assertRaisesRegex(menu.RegistrationError, "registration directory"):
            menu._safe_folders(menu.paths(self.alias / "xdg-home"))

    def test_status_reports_unsafe_for_home_behind_symlinked_ancestor(self):
        (self.real / "xdg-home").mkdir()
        self.assertEqual(menu.status(self.alias / "xdg-home"), "UNSAFE")

    def test_resource_dotdot_path_rejected(self):
        aliased = self.alias / ".." / "alias" / "canopy-classic"
        with self.assertRaises(menu.RegistrationError):
            menu._resource(str(aliased), "Canopy binary")

    def test_leaf_symlink_still_rejected(self):
        linked = self.base / "linked-canopy"
        linked.symlink_to(self.binary)
        with self.assertRaisesRegex(menu.RegistrationError, "non-symlink"):
            menu._resource(str(linked), "Canopy binary")

    def test_real_paths_still_accepted(self):
        art = self.real / "approved-art"
        art.mkdir()
        self.assertEqual(menu._resource(str(self.binary), "Canopy binary"),
                         str(self.binary))
        self.assertEqual(menu._resource(str(art), "approved artwork",
                                        directory=True), str(art))
        menu._safe_folders(menu.paths(self.home))
        self.assertEqual(menu.status(self.home), "NOT_INSTALLED")

    @unittest.skipIf(os.name == "nt",
                     "desktop Exec writer rejects Windows path separators")
    def test_end_to_end_install_refuses_aliased_home_and_binary(self):
        (self.real / "xdg-home").mkdir()
        with patch("tools.register_classic_preview.os.geteuid",
                   return_value=1000, create=True):
            with self.assertRaises(menu.RegistrationError):
                menu.install(self.alias / "xdg-home", self.alias / "canopy-classic")
            with self.assertRaises(menu.RegistrationError):
                menu.install(self.home, self.alias / "canopy-classic")
        self.assertEqual(list((self.real / "xdg-home").iterdir()), [])
        self.assertEqual(menu.status(self.home), "NOT_INSTALLED")


if __name__ == "__main__":
    unittest.main()
