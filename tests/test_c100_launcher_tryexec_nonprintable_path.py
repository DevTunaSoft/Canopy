"""Regression: non-printable TryExec values must never pass the install probe.

A TryExec value is an install probe: returning True classifies the application
as launchable. This module already refuses NUL and field codes, but it calls
``str.strip()`` before those checks. Python treats C0 separators (0x1c-0x1f) as
whitespace, so a control-wrapped path is laundered into a clean name; and a
real executable whose name contains a format/bidi character still passes the
probe. Both produce a false launchable verdict.

All cases are offline and bounded: temporary files only, no process execution.
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
C0_SEPARATORS = ("\x1c", "\x1d", "\x1e", "\x1f")
FORMAT_CHARS = ("\u200b", "\u202e", "\u2066", "\ufeff")


def make_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o755)


class NonPrintableTryExecTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_control_wrapped_name_cannot_be_stripped_into_a_clean_hit(self):
        exe = self.root / ("tool" + EXE_SUFFIX)
        make_executable(exe)
        for control in C0_SEPARATORS:
            with self.subTest(control=repr(control)):
                # str.strip() removes 0x1c-0x1f, so the post-strip NUL check
                # never sees them and shutil.which finds the clean "tool".
                self.assertIs(
                    is_tryexec_available(
                        control + "tool" + control, search_path=str(self.root)
                    ),
                    False,
                )

    def test_format_char_named_executable_is_not_launchable(self):
        for char in FORMAT_CHARS:
            with self.subTest(char=repr(char)):
                exe = self.root / ("probe" + char + "evil" + EXE_SUFFIX)
                make_executable(exe)
                self.assertIs(
                    is_tryexec_available(exe.name, search_path=str(self.root)),
                    False,
                )
                self.assertIs(is_tryexec_available(str(exe)), False)
                exe.unlink()

    def test_nul_and_other_controls_are_still_refused(self):
        for control in ("\x00", "\x01", "\x1b", "\x7f"):
            with self.subTest(control=repr(control)):
                self.assertIs(is_tryexec_available("tool" + control), False)

    def test_entry_values_with_hostile_tryexec_is_not_launchable(self):
        exe = self.root / ("tool" + EXE_SUFFIX)
        make_executable(exe)
        for control in C0_SEPARATORS:
            with self.subTest(control=repr(control)):
                self.assertIs(
                    tryexec_available_for_entry(
                        {"TryExec": control + "tool" + control, "Exec": "tool"},
                        search_path=str(self.root),
                    ),
                    False,
                )

    # --- controls: valid behaviour must survive the new guard ---

    def test_clean_bare_name_still_available(self):
        exe = self.root / ("tool" + EXE_SUFFIX)
        make_executable(exe)
        self.assertIs(
            is_tryexec_available("tool", search_path=str(self.root)), True
        )

    def test_blank_tryexec_still_means_no_probe(self):
        self.assertIs(is_tryexec_available(None), True)
        self.assertIs(is_tryexec_available(""), True)
        self.assertIs(is_tryexec_available("   "), True)

    def test_field_codes_still_refused_and_type_contract_unchanged(self):
        self.assertIs(is_tryexec_available("%f"), False)
        with self.assertRaisesRegex(TypeError, "search_path"):
            is_tryexec_available("tool", search_path=7)
        with self.assertRaisesRegex(TypeError, "TryExec"):
            is_tryexec_available(7)


if __name__ == "__main__":
    unittest.main()
