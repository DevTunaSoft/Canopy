"""Regression: an explicit TryExec PATH must not silently search the cwd.

On Windows, ``shutil.which`` prepends ``.`` to an explicitly supplied PATH
(``NeedCurrentDirectoryForExePath``). A caller that passes an isolated
``search_path`` therefore still gets a True verdict for an executable sitting
in the process working directory, which is not on that path. Relative
path-looking values with a directory component (for example ``C:tool``) also
bypass ``search_path`` and consult the cwd. Both are false launchable claims.

Offline and bounded: temporary directories only, no process execution.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_features.launcher.desktop_entry_tryexec import (  # noqa: E402
    is_tryexec_available,
    tryexec_available_for_entry,
)

EXE_SUFFIX = ".exe" if os.name == "nt" else ""


class ExplicitSearchPathIsolationTests(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.cwd_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.cwd_dir.cleanup)
        self.search_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.search_dir.cleanup)
        self.cwd_root = Path(self.cwd_dir.name)
        self.search_root = Path(self.search_dir.name)
        self.cwd_exe = self.cwd_root / ("tool" + EXE_SUFFIX)
        self.cwd_exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        if os.name != "nt":
            self.cwd_exe.chmod(0o755)
        os.chdir(self.cwd_root)
        self.addCleanup(os.chdir, self.original_cwd)

    @unittest.skipUnless(os.name == "nt",
                         "shutil.which injects the cwd only on Windows")
    def test_windows_explicit_path_does_not_find_cwd_executable(self):
        self.assertIs(
            is_tryexec_available("tool", search_path=str(self.search_root)),
            False,
        )

    @unittest.skipUnless(os.name == "nt",
                         "shutil.which injects the cwd only on Windows")
    def test_windows_entry_explicit_path_does_not_find_cwd_executable(self):
        self.assertIs(
            tryexec_available_for_entry(
                {"TryExec": "tool"}, search_path=str(self.search_root)
            ),
            False,
        )

    @unittest.skipUnless(os.name == "nt",
                         "drive-relative paths are a Windows path form")
    def test_drive_relative_value_cannot_bypass_explicit_path(self):
        drive, _ = os.path.splitdrive(str(self.cwd_root))
        if not drive:
            self.skipTest("cwd is not on a drive")
        self.assertIs(
            is_tryexec_available(drive + "tool",
                                 search_path=str(self.search_root)),
            False,
        )

    def test_search_path_hit_still_available(self):
        exe = self.search_root / ("tool" + EXE_SUFFIX)
        exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        if os.name != "nt":
            exe.chmod(0o755)
        self.assertIs(
            is_tryexec_available("tool", search_path=str(self.search_root)),
            True,
        )

    def test_absolute_path_still_available(self):
        self.assertIs(is_tryexec_available(str(self.cwd_exe)), True)

    def test_no_probe_and_type_contract_unchanged(self):
        self.assertIs(is_tryexec_available(None, search_path=7), True)  # type: ignore[arg-type]
        self.assertIs(is_tryexec_available("", search_path=7), True)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "TryExec"):
            is_tryexec_available(7)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "search_path"):
            is_tryexec_available("tool", search_path=7)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
