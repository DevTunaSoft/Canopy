"""Offline tests for the preview/desktop-helper privilege boundary.

No process is spawned, no credential is changed and no real Mint/Qt runtime
is involved. Host portability: these tests run on Windows and POSIX.
"""

import unittest
from unittest.mock import patch

from canopy_features.security import privilege_boundary as pb


class PrivilegeBoundaryTests(unittest.TestCase):
    def test_clean_action_allowed_when_unprivileged(self):
        decision = pb.evaluate(["nemo", "--new-window"], euid=1000)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, pb.ALLOWED)
        self.assertTrue(decision)  # Decision is truthy when allowed.
        self.assertIsNone(pb.authorize(["nemo"], euid=1000))

    def test_inherited_root_denied(self):
        decision = pb.evaluate(["nemo"], euid=0)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, pb.DENIED_INHERITED_ROOT)
        with self.assertRaises(pb.PrivilegeDenied) as context:
            pb.authorize(["nemo"], euid=0)
        self.assertEqual(context.exception.reason, pb.DENIED_INHERITED_ROOT)

    def test_inherited_root_denied_even_with_sudo_free_action(self):
        # Root context is refused on its own; no argv can make it acceptable.
        for argv in (["nemo"], ["firefox", "--private-window"]):
            with self.subTest(argv=argv):
                self.assertEqual(
                    pb.evaluate(argv, euid=0).reason, pb.DENIED_INHERITED_ROOT
                )

    def test_sudo_injection_prepended_denied(self):
        decision = pb.evaluate(["sudo", "nemo"], euid=1000)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, pb.DENIED_ELEVATION)
        with self.assertRaisesRegex(pb.PrivilegeDenied, pb.DENIED_ELEVATION):
            pb.authorize(["sudo", "nemo"], euid=1000)

    def test_sudo_injection_at_any_position_denied(self):
        for argv in (
            ["nemo", "sudo"],
            ["nemo", "--handler", "sudo"],
            ["sh", "-c", "sudo mount /dev/sda1 /mnt"],
            ["env", "sudo", "nemo"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(
                    pb.evaluate(argv, euid=1000).reason, pb.DENIED_ELEVATION
                )

    def test_elevation_wrapper_variants_denied(self):
        for token in (
            "sudo", "SUDO", "/usr/bin/sudo", "./sudo", ".\\sudo",
            "sudo.exe", "'sudo'", "pkexec", "doas", "su", "runuser",
            "gksudo", "kdesudo", "runas",
        ):
            with self.subTest(token=token):
                self.assertEqual(
                    pb.evaluate([token, "nemo"], euid=1000).reason,
                    pb.DENIED_ELEVATION,
                )

    def test_injected_sudo_inside_shell_word_denied(self):
        for argv in (
            ["sh", "-c", "echo ok;sudo reboot"],
            ["bash", "-c", "true && pkexec nemo"],
            ["cmd", "/c", "runas /user:admin nemo"],
        ):
            with self.subTest(argv=argv):
                self.assertFalse(pb.evaluate(argv, euid=1000).allowed)

    def test_system_level_commands_denied(self):
        for argv in (
            ["systemctl", "restart", "cinnamon"],
            ["apt", "upgrade", "-y"],
            ["/usr/sbin/useradd", "intruder"],
            ["sh", "-c", "mount -o remount,rw /"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(
                    pb.evaluate(argv, euid=1000).reason, pb.DENIED_SYSTEM_COMMAND
                )

    def test_empty_and_malformed_actions_denied(self):
        for argv, reason in (
            ([], pb.DENIED_EMPTY_ACTION),
            ("sudo nemo", pb.DENIED_INVALID_ACTION),
            (None, pb.DENIED_INVALID_ACTION),
            ({"argv": ["sudo"]}, pb.DENIED_INVALID_ACTION),
            (["nemo", 7], pb.DENIED_INVALID_ACTION),
            (["nemo", None], pb.DENIED_INVALID_ACTION),
        ):
            with self.subTest(argv=argv):
                self.assertEqual(pb.evaluate(argv, euid=1000).reason, reason)

    def test_oversized_action_denied_without_scanning_all_of_it(self):
        long_argument = "a" * (pb.MAX_ARGUMENT_LENGTH + 1)
        self.assertEqual(
            pb.evaluate(["nemo", long_argument], euid=1000).reason,
            pb.DENIED_OVERSIZED,
        )
        many_arguments = ["nemo"] * (pb.MAX_ARGUMENTS + 1)
        self.assertEqual(
            pb.evaluate(many_arguments, euid=1000).reason, pb.DENIED_OVERSIZED
        )

    def test_similar_but_harmless_arguments_allowed(self):
        # Negative control: exact basename match, no substring false positives.
        argv = [
            "nemo", "--title=sudoers guide",
            "/home/user/sudo-notes.txt", "--set-wallpaper",
        ]
        decision = pb.evaluate(argv, euid=1000)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, pb.ALLOWED)

    def test_current_euid_detection_is_used_by_default(self):
        with patch.object(pb, "current_euid", return_value=0):
            self.assertEqual(pb.evaluate(["nemo"]).reason, pb.DENIED_INHERITED_ROOT)
        with patch.object(pb, "current_euid", return_value=1000):
            self.assertTrue(pb.evaluate(["nemo"]).allowed)

    def test_windows_host_without_geteuid_still_denies_sudo(self):
        # On Windows current_euid() is None; argument denial must still work.
        with patch.object(pb, "current_euid", return_value=None):
            self.assertTrue(pb.evaluate(["nemo"]).allowed)
            self.assertEqual(
                pb.evaluate(["sudo", "nemo"]).reason, pb.DENIED_ELEVATION
            )

    def test_current_euid_returns_none_when_geteuid_absent(self):
        with patch.object(pb.os, "geteuid", None, create=True):
            self.assertIsNone(pb.current_euid())
        with patch.object(pb.os, "geteuid", return_value=0, create=True):
            self.assertEqual(pb.current_euid(), 0)

    def test_rejection_reason_never_contains_action_text(self):
        secret_action = ["sudo", "--token", "SECRET_VALUE_DO_NOT_LOG"]
        with self.assertRaises(pb.PrivilegeDenied) as context:
            pb.authorize(secret_action, euid=1000)
        self.assertNotIn("SECRET_VALUE_DO_NOT_LOG", str(context.exception))
        self.assertEqual(context.exception.reason, pb.DENIED_ELEVATION)


if __name__ == "__main__":
    unittest.main()
