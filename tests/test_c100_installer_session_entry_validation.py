"""Offline tests for user-level session-entry metadata validation.

No desktop session, display manager, Qt binary or Linux Mint guest is needed.
The binary fixtures are never executed; they only let the validator check
absolute-path and existence rules.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from canopy_features.installer.session_entry_validation import (  # noqa: E402
    MAX_ENTRY_BYTES,
    validate_session_entry,
)


class SessionEntryValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "xdg data home"
        self.binary = self.base / "canopy-classic-session"
        self.binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        if os.name == "posix":
            self.binary.chmod(0o755)
        self.marker = self.base / "executed"

    def executable(self, name="canopy-classic-session"):
        path = self.base / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        if os.name == "posix":
            path.chmod(0o755)
        return path

    def entry_text(self, *, binary=None, extra=""):
        target = (binary or self.binary).as_posix()
        return ("[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Canopy Classic\n"
                "Comment=User-level preview entry\n"
                "Exec=" + target + "\n" + extra)

    def write_entry(self, text, *, session="xsessions", home=None,
                    name="org.canopy.Classic.desktop"):
        directory = (home or self.home) / session
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(text, encoding="utf-8")
        return path

    def codes(self, report):
        return tuple(error.split(":", 1)[0] for error in report.errors)

    def test_valid_user_xsession_entry(self):
        entry = self.write_entry(self.entry_text(
            extra="TryExec=" + self.binary.as_posix() + "\n"))
        report = validate_session_entry(entry, data_home=self.home)
        self.assertTrue(report.valid, report.errors)
        self.assertEqual(report.errors, ())
        self.assertEqual(report.name, "Canopy Classic")
        self.assertEqual(report.exec_path, str(self.binary))
        self.assertEqual(report.session, "xsessions")

    def test_valid_user_wayland_session_entry(self):
        entry = self.write_entry(self.entry_text(), session="wayland-sessions")
        report = validate_session_entry(entry, data_home=self.home)
        self.assertTrue(report.valid, report.errors)
        self.assertEqual(report.session, "wayland-sessions")

    def test_quoted_exec_path_with_spaces(self):
        binary = self.executable("canopy classic with spaces")
        entry = self.write_entry(self.entry_text(binary=binary))
        text = entry.read_text(encoding="utf-8").replace(
            "Exec=" + binary.as_posix(), 'Exec="' + binary.as_posix() + '"')
        entry.write_text(text, encoding="utf-8")
        report = validate_session_entry(entry, data_home=self.home)
        self.assertTrue(report.valid, report.errors)
        self.assertEqual(report.exec_path, str(binary))

    def test_unsafe_exec_shell_c_refused_without_executing(self):
        # If the validator ever spawned a shell, this fixture would create the
        # marker. It also proves validation is read-only and shell-free.
        dangerous = ("Exec=/bin/sh -c 'touch " + self.marker.as_posix() + "'")
        entry = self.write_entry(
            "[Desktop Entry]\nType=Application\nName=Canopy\n" + dangerous + "\n")
        before = sorted(str(p) for p in self.base.rglob("*"))
        report = validate_session_entry(entry, data_home=self.home)
        self.assertFalse(report.valid)
        self.assertIn("UNSAFE_EXEC", self.codes(report))
        self.assertFalse(self.marker.exists())
        self.assertEqual(sorted(str(p) for p in self.base.rglob("*")), before)

    def test_unsafe_exec_forms_refused(self):
        dangerous = (
            "sh -c echo bad",
            "/bin/bash -c echo bad",
            "/usr/bin/env canopy-classic",
            "sudo /usr/bin/canopy-classic",
            "/usr/sbin/gdm3",
            "relative/canopy-classic",
            "../canopy-classic",
            "/usr/bin/canopy-classic %f",
            "/usr/bin/canopy-classic;touch /tmp/bad",
            "/usr/bin/canopy-classic | tee /tmp/bad",
            "/usr/bin/canopy-classic $HOME",
            "/usr/bin/canopy-classic `id`",
            "/usr/bin/canopy-classic && touch /tmp/bad",
        )
        for value in dangerous:
            with self.subTest(exec=value):
                entry = self.write_entry(self.entry_text().replace(
                    "Exec=" + self.binary.as_posix(), "Exec=" + value))
                report = validate_session_entry(entry, data_home=self.home)
                self.assertFalse(report.valid)
                self.assertIn("UNSAFE_EXEC", self.codes(report))

    def test_missing_session_binary_reported(self):
        missing = self.base / "no-such-session-binary"
        entry = self.write_entry(self.entry_text(binary=missing))
        report = validate_session_entry(entry, data_home=self.home)
        self.assertFalse(report.valid)
        self.assertIn("MISSING_SESSION_BINARY", self.codes(report))
        self.assertEqual(report.exec_path, str(missing))

    def test_missing_tryexec_binary_reported(self):
        missing = self.base / "no-such-tryexec-binary"
        entry = self.write_entry(self.entry_text(
            extra="TryExec=" + missing.as_posix() + "\n"))
        report = validate_session_entry(entry, data_home=self.home)
        self.assertFalse(report.valid)
        self.assertIn("MISSING_TRYEXEC_BINARY", self.codes(report))

    def test_tryexec_with_arguments_refused(self):
        entry = self.write_entry(self.entry_text(
            extra="TryExec=" + self.binary.as_posix() + " --verbose\n"))
        report = validate_session_entry(entry, data_home=self.home)
        self.assertFalse(report.valid)
        self.assertIn("UNSAFE_TRYEXEC", self.codes(report))

    @unittest.skipUnless(os.name == "posix", "POSIX execute bits only")
    def test_non_executable_binary_refused(self):
        self.binary.chmod(0o644)
        entry = self.write_entry(self.entry_text())
        report = validate_session_entry(entry, data_home=self.home)
        self.assertFalse(report.valid)
        self.assertIn("NOT_EXECUTABLE", self.codes(report))

    def test_exec_target_directory_refused(self):
        entry = self.write_entry(self.entry_text(binary=self.base))
        report = validate_session_entry(entry, data_home=self.home)
        self.assertFalse(report.valid)
        self.assertIn("UNSAFE_SESSION_BINARY", self.codes(report))

    def test_entry_outside_user_session_directories_refused(self):
        elsewhere = self.write_entry(self.entry_text(), home=self.base / "other")
        application = self.write_entry(self.entry_text(), session="applications")
        for entry in (elsewhere, application):
            with self.subTest(entry=entry):
                report = validate_session_entry(entry, data_home=self.home)
                self.assertFalse(report.valid)
                self.assertIn("UNSAFE_ENTRY_PATH", self.codes(report))

    def test_symlinked_entry_refused(self):
        real = self.write_entry(self.entry_text(), name="real.desktop")
        linked = real.parent / "org.canopy.Linked.desktop"
        try:
            linked.symlink_to(real)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlinks unavailable: " + str(exc))
        report = validate_session_entry(linked, data_home=self.home)
        self.assertFalse(report.valid)
        self.assertIn("UNSAFE_ENTRY_PATH", self.codes(report))

    def test_entry_size_is_bounded(self):
        entry = self.write_entry("[Desktop Entry]\n" + "X=1\n" * MAX_ENTRY_BYTES)
        report = validate_session_entry(entry, data_home=self.home)
        self.assertFalse(report.valid)
        self.assertIn("ENTRY_TOO_LARGE", self.codes(report))

    def test_missing_or_malformed_metadata_reported(self):
        cases = (
            ("[Other]\nName=Canopy\nExec=" + self.binary.as_posix() + "\n", "MISSING_DESKTOP_ENTRY"),
            ("[Desktop Entry]\nType=Application\nExec=" + self.binary.as_posix() + "\n", "MISSING_NAME"),
            ("[Desktop Entry]\nType=Application\nName=Canopy\n", "MISSING_EXEC"),
            ("[Desktop Entry]\nType=Session\nName=Canopy\nExec=" + self.binary.as_posix() + "\n",
             "UNSUPPORTED_SESSION_TYPE"),
            ("[Desktop Entry]\nType=Application\nName=Canopy\nExec=a\nExec=b\n",
             "MALFORMED_DESKTOP_ENTRY"),
        )
        for text, expected in cases:
            with self.subTest(expected=expected):
                entry = self.write_entry(text)
                report = validate_session_entry(entry, data_home=self.home)
                self.assertFalse(report.valid)
                self.assertIn(expected, self.codes(report))

    def test_xdg_data_home_environment_is_reused(self):
        entry = self.write_entry(self.entry_text())
        with patch.dict(os.environ, {"XDG_DATA_HOME": self.home.as_posix()}):
            report = validate_session_entry(entry)
        self.assertTrue(report.valid, report.errors)


if __name__ == "__main__":
    unittest.main()
