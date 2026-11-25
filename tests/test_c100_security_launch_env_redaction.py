"""Offline tests for launch-environment and failure-report redaction.

No real desktop, Qt binary, Mint guest, network or background service is used.
"""
import json
import re
import unittest

from canopy_core.host_events import FORBIDDEN_FIELDS
from canopy_features.security.launch_env_redaction import (
    MAX_ITEMS,
    MAX_TEXT_BYTES,
    REDACTED,
    SENSITIVE_TOKENS,
    TRUNCATED,
    is_sensitive_name,
    redact_environment,
    redact_report,
    redact_text,
)


class LaunchEnvRedactionTests(unittest.TestCase):
    def assert_no_secrets(self, serialized, secrets):
        for secret in secrets:
            with self.subTest(secret=secret):
                self.assertNotIn(secret, serialized)

    def test_api_keys_and_credentials_are_redacted_in_environment(self):
        env = {
            "OPENAI_API_KEY": "sk-live-openai-abcdef",
            "GITHUB_TOKEN": "ghp_github_abcdef",
            "AWS_SECRET_ACCESS_KEY": "aws-secret-access-value",
            "GOOGLE_API_KEY": "ya29.google_key_value",
            "CLIENT_SECRET": "client-secret-value",
            "DATABASE_PASSWORD": "database-pass-value",
            "SESSION_TOKEN": "session-token-value",
            "APIKEY": "flat-apikey-value",
        }
        result = redact_environment(env)
        for name, secret in env.items():
            self.assertEqual(result[name], REDACTED)
            self.assertIn(name, result)
        self.assert_no_secrets(json.dumps(result), env.values())

    def test_credential_like_names_reuse_existing_forbidden_vocabulary(self):
        names = (
            "PASSWORD", "SECRET", "TOKEN", "CREDENTIAL", "COOKIE",
            "AUTHORIZATION", "PRIVATE_KEY", "ACCESS_KEY", "AUTH_TOKEN",
            "__proto__", "constructor", "prototype", "XAUTHORITY",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(is_sensitive_name(name))
                self.assertEqual(redact_environment({name: "leak-me"})[name],
                                 REDACTED)
        for field in FORBIDDEN_FIELDS:
            for token in re.split(r"[^a-z0-9]+", field.lower()):
                if token:
                    self.assertIn(token, SENSITIVE_TOKENS)

    def test_benign_linux_and_windows_environment_keys_survive(self):
        env = {
            "XDG_SESSION_TYPE": "x11",
            "XDG_CURRENT_DESKTOP": "X-Cinnamon",
            "DISPLAY": ":0",
            "WAYLAND_DISPLAY": "wayland-0",
            "QT_QUICK_BACKEND": "software",
            "LANG": "C.UTF-8",
            "HOME": "/home/tester",
            "SYSTEMROOT": "C:\\Windows",
            "USERPROFILE": "C:\\Users\\tester",
            "APPDATA": "C:\\Users\\tester\\AppData\\Roaming",
            "Path": "C:\\bin",
        }
        self.assertEqual(redact_environment(env), env)

    def test_benign_field_still_scrubs_an_embedded_secret(self):
        result = redact_environment({"CANOPY_NOTE": "launch failed: api_key=embedded-secret"})
        self.assertNotIn("embedded-secret", result["CANOPY_NOTE"])
        self.assertIn(REDACTED, result["CANOPY_NOTE"])

    def test_freeform_text_scrubs_assignments_bearer_and_url_passwords(self):
        text = "\n".join((
            "OPENAI_API_KEY=sk-live-freeform",
            "Authorization: Bearer bearer-token-value",
            "error: token: xyz789 from launcher",
            "password='hunter2'",
            "dsn=postgres://user:dbpass-value@host/db",
        ))
        result = redact_text(text)
        self.assert_no_secrets(result, (
            "sk-live-freeform", "bearer-token-value", "xyz789", "hunter2",
            "dbpass-value",
        ))
        self.assertIn(REDACTED, result)

    def test_structured_failure_report_is_redacted_recursively(self):
        report = {
            "status": "FAIL",
            "exit_code": 3,
            "env": {"GITHUB_TOKEN": "ghp-nested-secret", "DISPLAY": ":0"},
            "detail": {
                "message": "launch failed with api_key=sk-nested-secret",
                "hint": "Authorization: Basic basic-nested-secret",
            },
            "markers": ["CANOPY_APP_LAUNCH_FAILED", "token: marker-secret"],
        }
        result = redact_report(report)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["exit_code"], "3")
        self.assertEqual(result["env"]["GITHUB_TOKEN"], REDACTED)
        self.assertEqual(result["env"]["DISPLAY"], ":0")
        self.assert_no_secrets(json.dumps(result), (
            "ghp-nested-secret", "sk-nested-secret", "basic-nested-secret",
            "marker-secret",
        ))

    def test_bytes_and_scalar_values_are_scrubbed(self):
        self.assertNotIn("bytes-secret", redact_text(b"api_key=bytes-secret"))
        self.assertEqual(redact_text(12345), "12345")
        self.assertEqual(redact_text(None), "")
        self.assertEqual(redact_text(True), "true")

    def test_output_is_bounded(self):
        self.assertLessEqual(len(redact_text("x" * 5000).encode("utf-8")),
                             MAX_TEXT_BYTES + len(TRUNCATED))
        big_list = redact_report(list(range(MAX_ITEMS + 20)))
        self.assertEqual(len(big_list), MAX_ITEMS + 1)
        self.assertEqual(big_list[-1], TRUNCATED)
        nested = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "deep-secret"}}}}}}}
        self.assertNotIn("deep-secret", json.dumps(redact_report(nested)))

    def test_input_is_not_mutated(self):
        env = {"GITHUB_TOKEN": "ghp-original"}
        original = dict(env)
        redact_environment(env)
        self.assertEqual(env, original)

    def test_invalid_environment_is_rejected(self):
        with self.assertRaises(TypeError):
            redact_environment(["TOKEN=abc"])
        with self.assertRaises(TypeError):
            redact_environment({1: "abc"})


if __name__ == "__main__":
    unittest.main()
