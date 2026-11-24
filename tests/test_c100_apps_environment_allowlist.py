"""Offline unit tests for the credential-free subprocess environment builder.

No process is launched, no real Linux Mint desktop is contacted and no compiled
Qt code is exercised. All secrets below are synthetic values placed into source
mappings to prove they cannot leak into the returned environment.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from canopy_features.apps.environment_allowlist import (
    CORE_ENV,
    LINUX_GUI_ENV,
    MAX_NAME_BYTES,
    MAX_VALUE_BYTES,
    MAX_VARIABLES,
    WINDOWS_GUI_ENV,
    EnvironmentAllowlistError,
    build_environment,
)


class EnvironmentAllowlistTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/canopy",
            "LANG": "C.UTF-8",
            "DISPLAY": ":0",
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": "/run/user/1000",
            "XAUTHORITY": "/home/canopy/.Xauthority",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
            "SystemRoot": r"C:\Windows",
            "USERPROFILE": r"C:\Users\canopy",
            "APPDATA": r"C:\Users\canopy\AppData\Roaming",
            "GITHUB_TOKEN": "ghp_SYNTHETIC_TOKEN_VALUE",
            "OPENAI_API_KEY": "sk-SYNTHETIC_KEY_VALUE",
            "AWS_SECRET_ACCESS_KEY": "SYNTHETIC_AWS_SECRET",
            "CANOPY_PASSWORD": "SYNTHETIC_PASSWORD",
            "SESSION_TOKEN": "SYNTHETIC_SESSION_TOKEN",
            "FOO": "bar",
        }
        self.snapshot = dict(self.source)

    def assertNoLeak(self, env):
        blob = repr(env)
        for name in ("GITHUB_TOKEN", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY",
                     "CANOPY_PASSWORD", "SESSION_TOKEN", "XAUTHORITY",
                     "DBUS_SESSION_BUS_ADDRESS", "ghp_SYNTHETIC_TOKEN_VALUE",
                     "sk-SYNTHETIC_KEY_VALUE", "SYNTHETIC_AWS_SECRET",
                     "SYNTHETIC_PASSWORD", "SYNTHETIC_SESSION_TOKEN"):
            with self.subTest(name=name):
                self.assertNotIn(name, blob)

    def test_only_allowlisted_names_are_copied(self):
        env = build_environment(["PATH", "LANG"], self.source)
        self.assertEqual(env, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        self.assertNoLeak(env)
        self.assertEqual(self.source, self.snapshot)

    def test_missing_and_duplicate_names_are_handled(self):
        env = build_environment(["PATH", "PATH", "NOT_PRESENT"], self.source)
        self.assertEqual(env, {"PATH": "/usr/bin:/bin"})

    def test_token_and_secret_names_refused_even_when_allowlisted(self):
        names = ("GITHUB_TOKEN", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY",
                 "CANOPY_PASSWORD", "SESSION_TOKEN", "github_token",
                 "MySecret", "API_KEY", "CLIENT_SECRET", "AUTH_TOKEN",
                 "GITHUBTOKEN")
        for name in names:
            with self.subTest(name=name):
                with self.assertRaises(EnvironmentAllowlistError):
                    build_environment(["PATH", name], self.source)

    def test_credential_handles_refused_even_when_allowlisted(self):
        for name in ("XAUTHORITY", "SSH_AUTH_SOCK", "SSH_AGENT_PID",
                     "GPG_AGENT_INFO", "KRB5CCNAME"):
            with self.subTest(name=name):
                with self.assertRaises(EnvironmentAllowlistError):
                    build_environment([name], self.source)

    def test_short_credential_aliases_refused_even_when_allowlisted(self):
        # Regression: DB_PASS / DB_PW / AWS_CRED are credential-shaped names,
        # but the word matcher only knew long forms (PASSWORD, PASSWORD_HASH,
        # CREDENTIAL) and copied their values into the child environment.
        names = ("PASS", "PW", "CRED", "DB_PASS", "MYSQL_PASS", "SSH_PASS",
                 "DB_PW", "AWS_CRED", "my_pass", "SVC_CRED")
        secret = "SYNTHETIC_SECRET_VALUE"
        for name in names:
            with self.subTest(name=name):
                with self.assertRaises(EnvironmentAllowlistError):
                    build_environment([name], {name: secret})
        env = build_environment(["PATH"], {**self.source, "DB_PASS": secret})
        self.assertNotIn(secret, repr(env))

    def test_error_messages_never_include_secret_values(self):
        with self.assertRaises(EnvironmentAllowlistError) as ctx:
            build_environment(["GITHUB_TOKEN"], self.source)
        self.assertNotIn("ghp_SYNTHETIC_TOKEN_VALUE", str(ctx.exception))
        self.assertNotIn("sk-SYNTHETIC_KEY_VALUE", repr(ctx.exception))

    def test_allowlist_shape_and_size_are_bounded(self):
        with self.assertRaises(EnvironmentAllowlistError):
            build_environment(["PATH"] * (MAX_VARIABLES + 1), self.source)
        for bad in ("PATH", b"PATH", None, 42):
            with self.subTest(bad=bad):
                with self.assertRaises(EnvironmentAllowlistError):
                    build_environment(bad, self.source)

    def test_non_mapping_source_containers_fail_closed(self):
        # A sequence has both __getitem__ and __contains__, so the old
        # hasattr-only check let it reach source[name] and leak a raw
        # built-in TypeError instead of the module's domain error.
        for bad_source in (["PATH"], ("PATH",), b"PATH", "PATH"):
            with self.subTest(bad_source=bad_source):
                with self.assertRaises(EnvironmentAllowlistError):
                    build_environment(["PATH"], bad_source)

    def test_name_format_and_length_validated(self):
        for name in ("", "1BAD", "A=B", "A B", "A\nB", "A" * (MAX_NAME_BYTES + 1)):
            with self.subTest(name=name):
                with self.assertRaises(EnvironmentAllowlistError):
                    build_environment([name], self.source)

    def test_value_type_nul_surrogate_and_size_validated(self):
        bad_values = {
            "BAD_NUL": "a\x00b",
            "BAD_LONG": "x" * (MAX_VALUE_BYTES + 1),
            "BAD_SURROGATE": "\ud800",
            "BAD_TYPE": 123,
        }
        for name, value in bad_values.items():
            with self.subTest(name=name):
                with self.assertRaises(EnvironmentAllowlistError):
                    build_environment([name], {name: value})

    def test_result_is_fresh_and_source_is_untouched(self):
        env = build_environment(["PATH"], self.source)
        env["PATH"] = "mutated"
        self.assertEqual(self.source, self.snapshot)
        self.assertEqual(self.source["PATH"], "/usr/bin:/bin")

    def test_core_baseline_is_minimal_and_token_free(self):
        env = build_environment(CORE_ENV, self.source)
        self.assertEqual(env, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        self.assertNoLeak(env)

    def test_linux_gui_baseline_keeps_gui_vars_but_drops_credential_handles(self):
        env = build_environment(LINUX_GUI_ENV, self.source)
        for name in ("PATH", "HOME", "DISPLAY", "WAYLAND_DISPLAY",
                     "XDG_RUNTIME_DIR", "LANG"):
            with self.subTest(name=name):
                self.assertIn(name, env)
        self.assertNotIn("XAUTHORITY", env)
        self.assertNotIn("DBUS_SESSION_BUS_ADDRESS", env)
        self.assertNoLeak(env)
        self.assertTrue(set(env).issubset(set(LINUX_GUI_ENV)))

    def test_windows_baseline_keeps_system_vars_but_drops_secrets(self):
        env = build_environment(WINDOWS_GUI_ENV, self.source)
        for name in ("PATH", "SystemRoot", "USERPROFILE", "APPDATA"):
            with self.subTest(name=name):
                self.assertIn(name, env)
        self.assertNoLeak(env)
        self.assertTrue(set(env).issubset(set(WINDOWS_GUI_ENV)))

    def test_real_host_environ_is_read_without_mutation(self):
        before = dict(os.environ)
        env = build_environment(CORE_ENV)
        self.assertEqual(dict(os.environ), before)
        self.assertTrue(set(env).issubset(set(CORE_ENV)))
        for name, value in env.items():
            self.assertEqual(value, before[name])


if __name__ == "__main__":
    unittest.main()
