"""Regression tests for reversible, unprivileged Classic application-menu entry."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import register_classic_preview as menu


ROOT = Path(__file__).resolve().parents[1]


class ClassicPreviewMenuTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.home = base / "xdg data with spaces"
        self.home.mkdir()
        self.binary = base / "canopy-classic"
        self.binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.binary.chmod(0o755)
        self.mark = base / "should-not-exist"
        self.art = base / "approved art"
        self.art.mkdir()
        self.wallpaper = base / "alpine wallpaper.png"
        self.wallpaper.write_bytes(b"simulated wallpaper")
        self.terminal = base / "candidate.png"
        self.terminal.write_bytes(b"simulated candidate")

    def install(self, **kwargs):
        with patch("tools.register_classic_preview.os.geteuid", return_value=1000):
            return menu.install(self.home, self.binary, **kwargs)

    def uninstall(self):
        with patch("tools.register_classic_preview.os.geteuid", return_value=1000):
            return menu.uninstall(self.home)

    def test_no_registration_initially(self):
        self.assertEqual(menu.status(self.home), "NOT_INSTALLED")

    def test_install_uninstall_round_trip_owns_only_two_files(self):
        desktop = self.install()
        self.assertTrue(desktop.is_file())
        self.assertEqual(menu.status(self.home), "INSTALLED")
        contents = desktop.read_text(encoding="utf-8")
        self.assertIn("Name=Canopy Classic Preview", contents)
        self.assertIn("not a replacement Cinnamon session", contents)
        self.assertNotIn("--enable-system-apps", contents)
        self.assertEqual(self.uninstall(), "UNINSTALLED")
        self.assertEqual(menu.status(self.home), "NOT_INSTALLED")
        self.assertTrue(self.home.is_dir())
        self.assertTrue((self.home / "applications").is_dir())

    def test_install_never_executes_binary(self):
        self.binary.write_text(
            "#!/bin/sh\ntouch " + str(self.mark) + "\n", encoding="utf-8"
        )
        self.binary.chmod(0o755)
        self.install()
        self.assertFalse(self.mark.exists())

    def test_desktop_entry_quotes_spaces_and_preserves_supported_flags(self):
        desktop = self.install(art=self.art, wallpaper=self.wallpaper,
                               terminal=self.terminal, native_apps=True)
        text = desktop.read_text(encoding="utf-8")
        self.assertIn('Exec="' + str(self.binary) + '"', text)
        self.assertIn('"--approved-art-dir" "' + str(self.art) + '"', text)
        self.assertIn('"--landscape-wallpaper" "' + str(self.wallpaper) + '"', text)
        self.assertIn('"--terminal-refinement" "' + str(self.terminal) + '"', text)
        self.assertIn('"--enable-system-apps"', text)
        self.assertNotIn("sh -c", text)
        self.assertEqual(menu.status(self.home), "INSTALLED")

    def test_existing_desktop_entry_not_overwritten(self):
        p = menu.paths(self.home)["desktop"]
        p.parent.mkdir(parents=True)
        p.write_text("user's desktop entry", encoding="utf-8")
        with self.assertRaisesRegex(menu.RegistrationError, "overwrite"):
            self.install()
        self.assertEqual(p.read_text(encoding="utf-8"), "user's desktop entry")

    def test_modified_managed_desktop_prevents_uninstall_without_deleting(self):
        desktop = self.install()
        desktop.write_text(desktop.read_text() + "# user note\n")
        self.assertEqual(menu.status(self.home), "MODIFIED_OR_UNMANAGED")
        with self.assertRaisesRegex(menu.RegistrationError, "removed nothing"):
            self.uninstall()
        self.assertTrue(desktop.is_file())
        self.assertTrue(menu.paths(self.home)["manifest"].is_file())

    def test_invalid_ownership_checksum_prevents_uninstall(self):
        desktop = self.install()
        marker = menu.paths(self.home)["manifest"]
        marker.write_text('{"schema":1,"sha256":"bad"}')
        self.assertEqual(menu.status(self.home), "MODIFIED_OR_UNMANAGED")
        with self.assertRaises(menu.RegistrationError):
            self.uninstall()
        self.assertTrue(desktop.is_file())

    def test_allows_unrelated_application_entries_to_survive(self):
        apps = self.home / "applications"
        apps.mkdir()
        other = apps / "another-program.desktop"
        other.write_text("other entry", encoding="utf-8")
        self.install()
        self.uninstall()
        self.assertEqual(other.read_text(), "other entry")

    def test_symlinked_desktop_entry_refused(self):
        other = Path(self.temp.name) / "external.desktop"
        other.write_text("private")
        destination = menu.paths(self.home)["desktop"]
        destination.parent.mkdir(parents=True)
        destination.symlink_to(other)
        self.assertEqual(menu.status(self.home), "UNSAFE")
        with self.assertRaises(menu.RegistrationError):
            self.install()
        self.assertEqual(other.read_text(), "private")

    def test_symlinked_registration_directory_refused(self):
        other = Path(self.temp.name) / "outside"
        other.mkdir()
        (self.home / "canopy").symlink_to(other, target_is_directory=True)
        self.assertEqual(menu.status(self.home), "UNSAFE")
        with self.assertRaises(menu.RegistrationError):
            self.install()
        self.assertEqual(list(other.iterdir()), [])

    def test_partial_write_failure_rolls_back_new_files(self):
        original = Path.open
        def refuse_manifest(path, *args, **kwargs):
            if path.name == "ownership.json" and "x" in args[0]:
                raise OSError("simulated full disk")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", autospec=True, side_effect=refuse_manifest):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual(menu.status(self.home), "NOT_INSTALLED")
        self.assertFalse(menu.paths(self.home)["desktop"].exists())

    def test_existing_unmanaged_folder_refused_without_cleanup(self):
        p = menu.paths(self.home)["folder"]
        p.mkdir(parents=True)
        note = p / "keep.txt"
        note.write_text("keep this")
        with self.assertRaisesRegex(menu.RegistrationError, "not empty"):
            self.install()
        self.assertEqual(note.read_text(), "keep this")

    def test_symlinked_binary_refused_even_if_executable(self):
        alias = Path(self.temp.name) / "linked-canopy"
        alias.symlink_to(self.binary)
        with self.assertRaisesRegex(menu.RegistrationError, "non-symlink"):
            self._try_binary(alias)
        self.assertEqual(menu.status(self.home), "NOT_INSTALLED")

    def test_binary_must_be_executable(self):
        self.binary.chmod(0o644)
        with self.assertRaisesRegex(menu.RegistrationError, "not executable"):
            self.install()
        self.assertEqual(menu.status(self.home), "NOT_INSTALLED")

    def test_missing_and_relative_resources_rejected(self):
        for filename in ("relative-executable", str(self.home / "missing")):
            with self.subTest(filename=filename):
                with self.assertRaises(menu.RegistrationError):
                    self._try_binary(filename)
        self.assertEqual(menu.status(self.home), "NOT_INSTALLED")

    def _try_binary(self, binary):
        with patch("tools.register_classic_preview.os.geteuid", return_value=1000):
            return menu.install(self.home, binary)

    def test_terminal_candidate_requires_original_art(self):
        with self.assertRaisesRegex(menu.RegistrationError, "requires approved art"):
            self.install(terminal=self.terminal)

    def test_special_exec_characters_rejected_before_creating_files(self):
        for char in ('"', "\\", "$", chr(96), "%", "\n"):
            with self.subTest(character=repr(char)):
                with self.assertRaises(menu.RegistrationError):
                    menu._quote("/tmp/name" + char + "unsafe")
        self.assertEqual(menu.status(self.home), "NOT_INSTALLED")

    def test_root_install_and_uninstall_both_refused(self):
        with patch("tools.register_classic_preview.os.geteuid", return_value=0):
            with self.assertRaisesRegex(menu.RegistrationError, "root"):
                menu.install(self.home, self.binary)
            with self.assertRaisesRegex(menu.RegistrationError, "root"):
                menu.uninstall(self.home)

    def test_custom_xdg_home_must_be_absolute(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "relative"}, clear=True):
            with self.assertRaisesRegex(menu.RegistrationError, "absolute"):
                menu.data_home()

    def test_cli_status_without_registration_no_side_effect(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.home)}, clear=False):
            process = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "register_classic_preview.py"),
                 "status"],
                check=False, capture_output=True, text=True
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("CANOPY_PREVIEW_NOT_INSTALLED", process.stdout)

    def test_install_twice_fails_without_overwriting(self):
        desktop = self.install()
        before = desktop.read_bytes()
        with self.assertRaises(menu.RegistrationError):
            self.install()
        self.assertEqual(desktop.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
