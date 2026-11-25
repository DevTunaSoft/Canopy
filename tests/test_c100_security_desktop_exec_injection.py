"""Offline security checks for the exec-field boundary validator.

No process starts, no shell is used, and no real Mint or compiled Qt runtime
is claimed here.
"""
from pathlib import Path
import unittest

from canopy_features.security.desktop_exec_injection import (
    MAX_FIELD_CHARS, MAX_TOKENS, MAX_TOKEN_CHARS,
    UnsafeExecError, is_safe_exec, validate_exec,
)


class ExecFieldValidationTests(unittest.TestCase):
    def assert_rejected(self, field, reason):
        with self.subTest(field=field, reason=reason):
            with self.assertRaises(UnsafeExecError) as ctx:
                validate_exec(field)
            self.assertEqual(ctx.exception.reason, reason)
            if type(field) is str and field:
                self.assertNotIn(field, str(ctx.exception))
            self.assertFalse(is_safe_exec(field))

    def test_plain_exec_returns_immutable_argv(self):
        argv = validate_exec("firefox --new-window https://example.com")
        self.assertIsInstance(argv, tuple)
        self.assertEqual(argv,
                         ("firefox", "--new-window", "https://example.com"))
        self.assertTrue(is_safe_exec("/usr/bin/nemo /home/user/Documents"))

    def test_no_existence_check_is_claimed(self):
        argv = validate_exec("not-installed-app --flag")
        self.assertEqual(argv, ("not-installed-app", "--flag"))

    def test_quotes_are_rejected(self):
        for field in ("firefox 'https://example.com'",
                      'firefox "https://example.com"',
                      "sh -c 'echo hi'"):
            self.assert_rejected(field, "quote")

    def test_redirects_are_rejected(self):
        for field in ("firefox > /tmp/out", "firefox < /tmp/in",
                      "firefox >> /tmp/out", "firefox 2>&1"):
            self.assert_rejected(field, "redirect")

    def test_pipes_are_rejected(self):
        for field in ("firefox | tee /tmp/out", "firefox |cat",
                      "firefox || true"):
            self.assert_rejected(field, "pipe")

    def test_substitutions_are_rejected(self):
        for field in ("firefox $(id)", "firefox ${HOME}",
                      "firefox $HOME", "firefox `id`"):
            self.assert_rejected(field, "substitution")

    def test_field_codes_are_rejected(self):
        for field in ("firefox %f", "firefox %U", "firefox --profile %u",
                      "firefox %%"):
            self.assert_rejected(field, "field code expansion")

    def test_shell_interpreter_and_wrapper_calls_are_rejected(self):
        for field in ("sh -c id", "bash -lc id", "/bin/sh -c id",
                      "/usr/bin/env sh -c id", "python3 -c pass",
                      "sudo nemo"):
            self.assert_rejected(field, "shell or interpreter call")

    def test_chaining_glob_and_escape_are_rejected(self):
        cases = (
            ("firefox && true", "command chaining"),
            ("firefox; true", "command chaining"),
            ("firefox &", "command chaining"),
            ("firefox *", "glob expansion"),
            ("firefox a\\b", "escape sequence"),
        )
        for field, reason in cases:
            self.assert_rejected(field, reason)

    def test_reason_is_deterministic_when_many_shell_marks_appear(self):
        self.assert_rejected("sh -c 'echo $HOME | tee %f'", "quote")

    def test_control_and_non_ascii_input_is_rejected(self):
        for field in ("firefox\nrm", "firefire\tx", "firefox --name Café"):
            self.assert_rejected(field, "control or non-ASCII character")

    def test_wrong_types_empty_and_whitespace_are_rejected(self):
        for value in (None, b"firefox", 3, True, ["firefox"]):
            self.assert_rejected(value, "field must be a string")
        self.assert_rejected("", "empty or oversized field")
        self.assert_rejected("   ", "invalid token count")

    def test_bounds_are_enforced(self):
        self.assert_rejected("firefox " + "a" * (MAX_FIELD_CHARS + 1),
                             "empty or oversized field")
        self.assert_rejected("firefox " + " ".join(["x"] * MAX_TOKENS),
                             "invalid token count")
        self.assert_rejected("firefox " + "a" * (MAX_TOKEN_CHARS + 1),
                             "unsupported argument token")

    def test_module_stays_pure_offline_and_bounded(self):
        code = (Path(__file__).resolve().parents[1] /
                "canopy_features/security/desktop_exec_injection.py"
                ).read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "os.popen", "QProcess",
                          "shlex", "eval(", "Thread(", "socket",
                          "time.sleep", "importlib"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
