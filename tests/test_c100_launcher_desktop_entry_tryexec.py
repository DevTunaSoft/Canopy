"""Offline unit tests for TryExec availability evaluation.

No Qt, GIO, desktop session, network or binary execution is involved. The
tests create only temporary files and pass an explicit ``search_path`` so
results never depend on the host PATH. POSIX-only cases are skipped on
Windows, where the executable bit has no meaning.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canopy_features.launcher.desktop_entry_tryexec import (
    is_tryexec_available,
    tryexec_available_for_entry,
)

EXE_SUFFIX = ".exe" if os.name == "nt" else ""


def make_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o755)


class TryExecAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_no_tryexec_means_no_probe(self):
        self.assertTrue(is_tryexec_available(None))
        self.assertTrue(is_tryexec_available(""))
        self.assertTrue(is_tryexec_available("   "))

    def test_missing_absolute_executable_is_unavailable(self):
        missing = self.root / ("does-not-exist" + EXE_SUFFIX)
        self.assertFalse(is_tryexec_available(str(missing)))

    def test_missing_bare_name_is_unavailable(self):
        self.assertFalse(is_tryexec_available("not-on-any-path", search_path=str(self.root)))

    def test_search_path_override_ignores_host_path(self):
        # A real host binary must not leak into an isolated probe.
        host_name = "python.exe" if os.name == "nt" else "python3"
        self.assertFalse(is_tryexec_available(host_name, search_path=str(self.root)))

    def test_absolute_path_to_executable_is_available(self):
        exe = self.root / ("tool" + EXE_SUFFIX)
        make_executable(exe)
        self.assertTrue(is_tryexec_available(str(exe)))

    def test_bare_name_resolves_against_explicit_path(self):
        exe = self.root / ("tool" + EXE_SUFFIX)
        make_executable(exe)
        self.assertTrue(is_tryexec_available(exe.name, search_path=str(self.root)))

    def test_spoofed_directory_is_not_an_executable(self):
        fake = self.root / ("spoof" + EXE_SUFFIX)
        fake.mkdir()
        self.assertFalse(is_tryexec_available(str(fake)))
        self.assertFalse(is_tryexec_available(fake.name, search_path=str(self.root)))

    @unittest.skipUnless(os.name == "posix", "executable bit is POSIX-only")
    def test_spoofed_file_without_executable_bit_is_refused(self):
        fake = self.root / "spoof"
        fake.write_text("not executable\n", encoding="utf-8")
        fake.chmod(0o644)
        self.assertFalse(is_tryexec_available(str(fake)))
        self.assertFalse(is_tryexec_available(fake.name, search_path=str(self.root)))

    def test_field_codes_and_arguments_are_refused(self):
        self.assertFalse(is_tryexec_available("/usr/bin/app %f"))
        self.assertFalse(is_tryexec_available("/usr/bin/app --version"))
        self.assertFalse(is_tryexec_available("/usr/bin/app\x00"))

    def test_evaluation_never_runs_the_named_binary(self):
        marker = self.root / "marker"
        script = self.root / ("probe" + EXE_SUFFIX)
        script.write_text(
            "#!/bin/sh\n: > " + str(marker) + "\n", encoding="utf-8"
        )
        if os.name != "nt":
            script.chmod(0o755)
        self.assertTrue(is_tryexec_available(str(script)))
        self.assertFalse(marker.exists(), "TryExec probe must not execute the binary")

    def test_non_string_input_is_rejected(self):
        with self.assertRaises(TypeError):
            is_tryexec_available(123)

    def test_entry_values_mapping_is_supported(self):
        exe = self.root / ("tool" + EXE_SUFFIX)
        make_executable(exe)

        class Entry:
            values = {"TryExec": str(exe), "Name": "Tool"}

        self.assertTrue(tryexec_available_for_entry(Entry()))
        self.assertTrue(
            tryexec_available_for_entry({"TryExec": exe.name}, search_path=str(self.root))
        )
        self.assertTrue(tryexec_available_for_entry({"Name": "Tool"}))
        with self.assertRaises(TypeError):
            tryexec_available_for_entry(object())


if __name__ == "__main__":
    unittest.main()
