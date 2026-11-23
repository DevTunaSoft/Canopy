"""Regression tests for real Linux/Debian system-command names in the privilege boundary.

The deny gate lists ``mkfs`` and ``useradd`` but the executables that actually
format a filesystem or create an account on Debian/Ubuntu/Mint are
``mkfs.ext4`` and ``adduser``.  Those names used to fail open: ``evaluate``
returned ALLOWED and ``authorize`` raised nothing.  Pure-Python, host portable;
no process is spawned and no credential is changed.
"""

import unittest

from canopy_features.security import privilege_boundary as pb


# Filesystem builders on Debian/Ubuntu/Mint: mkfs itself is already denied,
# but the dispatch utilities that actually do the work have a dot suffix.
MKFS_COMMANDS = (
    "mkfs.ext4", "mkfs.ext3", "mkfs.ext2", "mkfs.vfat", "mkfs.fat",
    "mkfs.xfs", "mkfs.btrfs", "mkfs.ntfs", "mkfs.f2fs", "mkfs.minix",
    "mkfs.jfs", "mkfs.reiserfs",
)

# Debian account-management utilities (useradd/usermod/userdel are already
# listed; the friendly wrappers and group tools were missing).
ACCOUNT_COMMANDS = (
    "adduser", "addgroup", "deluser", "delgroup",
    "groupadd", "groupmod", "groupdel", "newusers", "chpasswd",
)


class PrivilegeSystemCommandNamesTests(unittest.TestCase):
    def test_mkfs_dispatch_utilities_denied(self):
        for command in MKFS_COMMANDS:
            with self.subTest(command=command):
                decision = pb.evaluate([command, "/dev/sda1"], euid=1000)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, pb.DENIED_SYSTEM_COMMAND)

    def test_account_management_utilities_denied(self):
        for command in ACCOUNT_COMMANDS:
            with self.subTest(command=command):
                decision = pb.evaluate([command, "intruder"], euid=1000)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, pb.DENIED_SYSTEM_COMMAND)

    def test_denial_applies_to_paths_case_and_exe_suffix(self):
        # _basename strips directories/quotes/.exe and lowercases before the
        # deny check; the suffix variants must be covered at that same layer.
        for argv in (
            ["/usr/sbin/mkfs.ext4", "/dev/sda1"],
            [".\\mkfs.vfat", "E:"],
            ["MKFS.EXT4", "/dev/sda1"],
            ["mkfs.ext4.exe", "/dev/sda1"],
            ["/usr/sbin/adduser", "intruder"],
            ["ADDGROUP", "wheel"],
            ["adduser.exe", "intruder"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(
                    pb.evaluate(argv, euid=1000).reason, pb.DENIED_SYSTEM_COMMAND
                )

    def test_dispatch_names_inside_injected_shell_word_denied(self):
        for argv in (
            ["sh", "-c", "mkfs.ext4 /dev/sda1 && sync"],
            ["bash", "-c", "echo ok; adduser intruder"],
            ["cmd", "/c", "mkfs.vfat E:"],
        ):
            with self.subTest(argv=argv):
                self.assertFalse(pb.evaluate(argv, euid=1000).allowed)

    def test_authorize_raises_for_newly_denied_names(self):
        # authorize() is the enforcement entry point, not just evaluate().
        for argv in (
            ["mkfs.ext4", "/dev/sda1"],
            ["mkfs.btrfs", "-f", "/dev/sdb1"],
            ["adduser", "intruder"],
            ["delgroup", "staff"],
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(pb.PrivilegeDenied) as context:
                    pb.authorize(argv, euid=1000)
                self.assertEqual(context.exception.reason, pb.DENIED_SYSTEM_COMMAND)
                self.assertNotIn("intruder", str(context.exception))

    def test_similar_but_harmless_arguments_still_allowed(self):
        # Negative control: whole-name matching, no substring false positives.
        # "--title=mkfs.ext4" is one word starting with "--title=", and file
        # names with a hyphen instead of a dot are unrelated to the binaries.
        argv = [
            "nemo", "--title=mkfs.ext4 guide", "--note=adduser setup",
            "/home/user/mkfs-notes.txt", "/home/user/adduser-guide.pdf",
            "format-notes.txt", "--set-wallpaper",
        ]
        decision = pb.evaluate(argv, euid=1000)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, pb.ALLOWED)

    def test_existing_baseline_denials_unchanged(self):
        # Guard against narrowing the pre-existing deny set while fixing it.
        for argv in (
            ["mkfs", "/dev/sda1"],
            ["useradd", "intruder"],
            ["systemctl", "restart", "cinnamon"],
            ["sudo", "nemo"],
        ):
            with self.subTest(argv=argv):
                self.assertFalse(pb.evaluate(argv, euid=1000).allowed)


if __name__ == "__main__":
    unittest.main()
