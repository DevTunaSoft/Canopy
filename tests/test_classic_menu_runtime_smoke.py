"""Negative controls for real compiled Qt menu-launch smoke instrumentation.

Unit tests deliberately do not claim X11, GIO, Mint or Qt acceptance.
Those require the separate actual compiled-runtime job in CI.
"""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import classic_menu_runtime_smoke as smoke


class ClassicMenuRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.executable = Path(self.tmp.name) / "canopy-preview"
        self.executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.executable.chmod(0o700)

    def test_real_executable_identity_and_pinned_sha(self):
        digest = hashlib.sha256(self.executable.read_bytes()).hexdigest()
        ident = smoke.verified_executable(self.executable, digest)
        st = self.executable.stat()
        self.assertEqual(ident, (st.st_dev, st.st_ino))
        self.assertTrue(stat.S_ISREG(st.st_mode))

    def test_wrong_sha_and_invalid_digest_are_rejected(self):
        with self.assertRaisesRegex(smoke.MenuRuntimeError, "match pinned"):
            smoke.verified_executable(self.executable, "0" * 64)
        with self.assertRaisesRegex(smoke.MenuRuntimeError, "lowercase hex"):
            smoke.verified_executable(self.executable, "A" * 64)

    def test_symlink_is_never_accepted_as_compiled_binary(self):
        shortcut = Path(self.tmp.name) / "symlink-binary"
        shortcut.symlink_to(self.executable)
        with self.assertRaisesRegex(smoke.MenuRuntimeError, "non-symlink"):
            smoke.verified_executable(shortcut)

    def test_relative_and_missing_binary_rejected(self):
        with self.assertRaisesRegex(smoke.MenuRuntimeError, "absolute"):
            smoke.verified_executable(Path("canopy-preview"))
        with self.assertRaisesRegex(smoke.MenuRuntimeError, "regular"):
            smoke.verified_executable(Path(self.tmp.name) / "missing")

    def test_nonexecutable_binary_rejected(self):
        self.executable.chmod(0o600)
        with self.assertRaisesRegex(smoke.MenuRuntimeError, "executable"):
            smoke.verified_executable(self.executable)

    def test_window_title_requires_both_identifiers_in_single_line(self):
        def fake(returncode, stdout):
            return subprocess.CompletedProcess(["xwininfo"], returncode, stdout, "")
        with mock.patch.object(smoke.subprocess, "run", return_value=fake(
            0, '0x1 "Canopy Classic — Technology Spike": () 1200x750+0+0')):
            self.assertTrue(smoke._has_window())
        with mock.patch.object(smoke.subprocess, "run", return_value=fake(
            0, 'Canopy Classic\nTechnology Spike\n')):
            self.assertFalse(smoke._has_window())
        with mock.patch.object(smoke.subprocess, "run", return_value=fake(
            1, '0x1 "Canopy Classic — Technology Spike"')):
            self.assertFalse(smoke._has_window())

    def test_without_display_fails_before_any_menu_install(self):
        with mock.patch.dict(os.environ, {"DISPLAY": ""}):
            with mock.patch.object(smoke.menu, "install") as install:
                with self.assertRaisesRegex(smoke.MenuRuntimeError, "DISPLAY"):
                    smoke.run(self.executable)
                install.assert_not_called()

    def test_timeout_outside_bounded_range_rejected(self):
        with mock.patch.object(smoke.os, "geteuid", return_value=1000):
            with mock.patch.dict(os.environ, {"DISPLAY": ":99"}):
                with self.assertRaisesRegex(smoke.MenuRuntimeError, "safe bounds"):
                    smoke.run(self.executable, timeout=999)

    def test_no_shell_or_full_user_desktop_mutation(self):
        source = Path(smoke.__file__).read_text(encoding="utf-8")
        self.assertIn('["gio", "launch", str(desktop)]', source)
        self.assertIn('["xwininfo", "-root", "-tree"]', source)
        self.assertIn("menu.install(data, binary)", source)
        self.assertIn('menu.status(data) == "INSTALLED"', source)
        self.assertIn("menu.uninstall(data)", source)
        self.assertIn("previously_running = _matching_pids(identity)", source)
        self.assertIn("if pid not in _matching_pids(exe_identity)", source)
        for unsafe in ("shell=True", "os.system(", "sudo ", "chmod -R",
                       "pkill", "killall", "git push"):
            self.assertNotIn(unsafe, source)


if __name__ == "__main__":
    unittest.main()
