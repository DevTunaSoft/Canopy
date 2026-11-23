"""Regression tests for repeated ``.exe`` suffixes in the privilege boundary.

``_basename`` strips one trailing ``.exe`` so Windows spellings such as
``sudo.exe`` match the denylist.  A doubled spelling (``sudo.exe.exe``) left
``sudo.exe`` behind, which is not a denylisted name: the gate returned ALLOWED
even though re-applying the same normalizer produced ``sudo`` and a denial.
Basename normalization must be a fixed point so a decorated spelling cannot
widen the decision.  Pure Python, host portable; no process is spawned.
"""

import unittest

from canopy_features.security import privilege_boundary as pb


# Elevation wrappers with a repeated Windows executable suffix.
ELEVATION_TOKENS = (
    "sudo.exe.exe",
    "SUDO.EXE.EXE",
    "/usr/bin/sudo.exe.exe",
    ".\\sudo.exe.exe",
    "'sudo.exe.exe'",
    "runas.exe.exe",
    "pkexec.exe.exe",
)

# Denylisted system commands with the same decoration.
SYSTEM_TOKENS = (
    "apt.exe.exe",
    "adduser.exe.exe",
    "systemctl.exe.exe",
)

# Already handled before this fix: controls that must keep their decision.
CONTROL_DENIED = (
    "sudo", "sudo.exe", "/usr/bin/sudo", "mkfs.ext4.exe.exe", "adduser.exe",
)
CONTROL_ALLOWED = ("nemo", "firefox.exe", "--new-window")


class PrivilegeRepeatedExeSuffixTests(unittest.TestCase):
    def test_basename_normalization_is_a_fixed_point(self):
        for token in ELEVATION_TOKENS + SYSTEM_TOKENS:
            with self.subTest(token=token):
                once = pb._basename(token)
                self.assertEqual(pb._basename(once), once)

    def test_elevation_wrappers_with_repeated_exe_denied(self):
        for token in ELEVATION_TOKENS:
            with self.subTest(token=token):
                decision = pb.evaluate([token, "nemo"], euid=1000)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, pb.DENIED_ELEVATION)

    def test_system_commands_with_repeated_exe_denied(self):
        for token in SYSTEM_TOKENS:
            with self.subTest(token=token):
                decision = pb.evaluate([token, "intruder"], euid=1000)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, pb.DENIED_SYSTEM_COMMAND)

    def test_authorize_refuses_repeated_exe_with_stable_reason(self):
        for token in ("sudo.exe.exe", "apt.exe.exe"):
            with self.subTest(token=token):
                with self.assertRaises(pb.PrivilegeDenied) as context:
                    pb.authorize([token, "nemo"], euid=1000)
                self.assertIn(
                    context.exception.reason,
                    (pb.DENIED_ELEVATION, pb.DENIED_SYSTEM_COMMAND),
                )
                self.assertEqual(str(context.exception), context.exception.reason)

    def test_repeated_exe_inside_shell_word_denied(self):
        for argv in (
            ["sh", "-c", "echo ok;sudo.exe.exe nemo"],
            ["env", "apt.exe.exe", "update"],
        ):
            with self.subTest(argv=argv):
                self.assertNotEqual(pb.evaluate(argv, euid=1000).reason, pb.ALLOWED)

    def test_existing_denials_unchanged(self):
        for token in CONTROL_DENIED:
            with self.subTest(token=token):
                self.assertNotEqual(pb.evaluate([token], euid=1000).reason, pb.ALLOWED)

    def test_valid_actions_still_allowed(self):
        for argv in ([token] for token in CONTROL_ALLOWED):
            with self.subTest(argv=argv):
                decision = pb.evaluate(argv, euid=1000)
                self.assertTrue(decision.allowed)
                self.assertEqual(decision.reason, pb.ALLOWED)


if __name__ == "__main__":
    unittest.main()
