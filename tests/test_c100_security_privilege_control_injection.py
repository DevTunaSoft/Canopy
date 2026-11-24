"""Regression tests: injected control bytes must not bypass the privilege gate.

Distinct from the double-``.exe`` normalization fix (PR #344): this covers
control characters that were never split into words at all, so an elevation or
system command smuggled behind NUL/C0/C1/DEL was silently allowed.

Run: python -m unittest tests.test_c100_security_privilege_control_injection -v
"""
import unittest

from canopy_features.security import privilege_boundary as priv


EUID = 1000
# Whitespace controls were already handled by \s; these were not.
UNSPLIT_CONTROLS = tuple(chr(code) for code in (
    0x00, 0x01, 0x02, 0x03, 0x07, 0x08, 0x0e, 0x0f,
    0x10, 0x1b, 0x1f, 0x7f, 0x85, 0x9f,
))


class ControlInjectionTests(unittest.TestCase):
    def test_elevation_after_control_is_denied(self):
        for ch in UNSPLIT_CONTROLS:
            with self.subTest(code=ord(ch)):
                decision = priv.evaluate(["sudo" + ch + " --version"], euid=EUID)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, priv.DENIED_ELEVATION)

    def test_system_command_after_control_is_denied(self):
        for ch in UNSPLIT_CONTROLS:
            with self.subTest(code=ord(ch)):
                decision = priv.evaluate(["reboot" + ch + " now"], euid=EUID)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, priv.DENIED_SYSTEM_COMMAND)

    def test_elevation_before_control_is_denied(self):
        for ch in UNSPLIT_CONTROLS:
            with self.subTest(code=ord(ch)):
                decision = priv.evaluate([ch + "sudo"], euid=EUID)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, priv.DENIED_ELEVATION)

    def test_nul_embedded_in_longer_argument_is_denied(self):
        decision = priv.evaluate(["--title=Notes\x00sudo mount /"], euid=EUID)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, priv.DENIED_ELEVATION)

    def test_windows_elevation_wrapper_with_control_is_denied(self):
        decision = priv.evaluate(["runas.exe\x00cmd"], euid=EUID)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, priv.DENIED_ELEVATION)

    def test_double_exe_behavior_unchanged(self):
        decision = priv.evaluate(["sudo.exe.exe"], euid=EUID)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, priv.DENIED_ELEVATION)


class ControlRegressionTests(unittest.TestCase):
    """Controls proving the fix preserves the documented contract."""

    def test_plain_elevation_still_denied(self):
        self.assertEqual(
            priv.evaluate(["sudo", "--version"], euid=EUID).reason,
            priv.DENIED_ELEVATION)

    def test_plain_system_command_still_denied(self):
        self.assertEqual(priv.evaluate(["reboot"], euid=EUID).reason,
                         priv.DENIED_SYSTEM_COMMAND)

    def test_benign_action_still_allowed(self):
        self.assertTrue(priv.evaluate(["eog", "--fullscreen"], euid=EUID))

    def test_whitespace_splitting_still_works(self):
        for ch in (" ", "\t", "\n", "\r", "\v", "\f", ";", "&", "|", "`"):
            with self.subTest(code=ord(ch)):
                decision = priv.evaluate(["sudo" + ch + "--version"], euid=EUID)
                self.assertEqual(decision.reason, priv.DENIED_ELEVATION)

    def test_inherited_root_still_denied(self):
        self.assertEqual(priv.evaluate(["eog"], euid=0).reason,
                         priv.DENIED_INHERITED_ROOT)

    def test_empty_and_oversized_still_denied(self):
        self.assertEqual(priv.evaluate([], euid=EUID).reason,
                         priv.DENIED_EMPTY_ACTION)
        self.assertEqual(
            priv.evaluate(["eog"] * (priv.MAX_ARGUMENTS + 1), euid=EUID).reason,
            priv.DENIED_OVERSIZED)

    def test_wrong_type_still_denied(self):
        self.assertEqual(priv.evaluate(["eog", 7], euid=EUID).reason,
                         priv.DENIED_INVALID_ACTION)

    def test_decision_reason_never_echoes_argument(self):
        decision = priv.evaluate(["sudo\x00 --version"], euid=EUID)
        self.assertNotIn("sudo", str(decision))
        self.assertNotIn("sudo", decision.reason)


if __name__ == "__main__":
    unittest.main()
