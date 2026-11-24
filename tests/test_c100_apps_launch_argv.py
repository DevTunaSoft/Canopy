"""Offline unit tests for shell-free application launch argv.

No process is spawned. These tests cover token construction only and do not
claim a Qt, GIO, Linux Mint or Windows desktop launch was performed.
"""
from pathlib import Path
import unittest

from canopy_features.apps.launch_argv import (
    MAX_ARGUMENTS,
    MAX_ARGV_BYTES,
    MAX_TOKEN_BYTES,
    SHELL_METACHARACTERS,
    LaunchArgvError,
    build_launch_argv,
    gio_launch_argv,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "canopy_features" / "apps" / "launch_argv.py"


class LaunchArgvTests(unittest.TestCase):
    def test_plain_argv_is_immutable_ordered_and_shell_free(self):
        argv = build_launch_argv("firefox", ["--new-window", "https://example.org"])
        self.assertEqual(argv, ("firefox", "--new-window", "https://example.org"))
        self.assertIsInstance(argv, tuple)
        for token in argv:
            self.assertIsInstance(token, str)
            self.assertFalse(any(ch in SHELL_METACHARACTERS for ch in token))

    def test_no_arguments_returns_a_single_token(self):
        self.assertEqual(build_launch_argv("nemo"), ("nemo",))
        self.assertEqual(build_launch_argv("nemo", ()), ("nemo",))
        self.assertEqual(build_launch_argv("nemo", []), ("nemo",))

    def test_empty_and_non_string_commands_are_rejected(self):
        for command in ("", "   ", "\t", None, b"firefox", 7, [], ("a",)):
            with self.subTest(command=repr(command)):
                with self.assertRaises(LaunchArgvError):
                    build_launch_argv(command)

    def test_every_shell_metacharacter_is_rejected_in_command(self):
        for char in sorted(SHELL_METACHARACTERS):
            with self.subTest(char=repr(char)):
                with self.assertRaises(LaunchArgvError):
                    build_launch_argv("app" + char + "x")

    def test_every_shell_metacharacter_is_rejected_in_arguments(self):
        for char in sorted(SHELL_METACHARACTERS):
            with self.subTest(char=repr(char)):
                with self.assertRaises(LaunchArgvError):
                    build_launch_argv("app", ["a" + char + "b"])

    def test_shell_command_string_is_not_treated_as_an_executable(self):
        for command in ("firefox; rm -rf /", "sh -c 'id'", "app && other",
                        "$(whoami)", "app | tee out", "app > out"):
            with self.subTest(command=command):
                with self.assertRaises(LaunchArgvError):
                    build_launch_argv(command)

    def test_host_allowlist_is_fail_closed(self):
        allowed = ("firefox", "nemo")
        self.assertEqual(build_launch_argv("nemo", allowed_executables=allowed),
                         ("nemo",))
        for command in ("sh", "Firefox", "/usr/bin/firefox"):
            with self.subTest(command=command):
                with self.assertRaisesRegex(LaunchArgvError, "not approved"):
                    build_launch_argv(command, allowed_executables=allowed)
        for bad_allowlist in ("firefox", b"firefox", {"a": 1}, 5):
            with self.subTest(bad_allowlist=repr(bad_allowlist)):
                with self.assertRaises(LaunchArgvError):
                    build_launch_argv("firefox", allowed_executables=bad_allowlist)

    def test_argument_container_and_entry_mistakes_are_rejected(self):
        for arguments in ("--flag", b"--flag", {"a": "b"}, None, 5,
                          ["--ok", 1], [""], [None], [["nested"]]):
            with self.subTest(arguments=repr(arguments)):
                with self.assertRaises(LaunchArgvError):
                    build_launch_argv("app", arguments)

    def test_argument_count_is_bounded(self):
        build_launch_argv("app", ["a"] * MAX_ARGUMENTS)
        with self.assertRaisesRegex(LaunchArgvError, "too many"):
            build_launch_argv("app", ["a"] * (MAX_ARGUMENTS + 1))

    def test_token_and_total_byte_bounds_are_enforced(self):
        with self.assertRaisesRegex(LaunchArgvError, "byte bound"):
            build_launch_argv("a" * (MAX_TOKEN_BYTES + 1))
        with self.assertRaisesRegex(LaunchArgvError, "byte bound"):
            build_launch_argv("app", ["a" * (MAX_TOKEN_BYTES + 1)])
        with self.assertRaisesRegex(LaunchArgvError, "total byte bound"):
            build_launch_argv("app", ["a" * MAX_TOKEN_BYTES] * 5)
        self.assertLess(MAX_ARGV_BYTES, MAX_TOKEN_BYTES * 5)

    def test_valid_unicode_is_kept_and_lone_surrogate_is_rejected(self):
        self.assertEqual(build_launch_argv("Café", ["naïve"]), ("Café", "naïve"))
        with self.assertRaisesRegex(LaunchArgvError, "not valid Unicode"):
            build_launch_argv("\ud800")

    def test_caller_mutation_does_not_change_returned_argv(self):
        arguments = ["--a"]
        argv = build_launch_argv("app", arguments)
        arguments.append("--b")
        self.assertEqual(argv, ("app", "--a"))

    def test_gio_argv_reuses_gio_cli_without_a_shell(self):
        self.assertEqual(gio_launch_argv("firefox.desktop"),
                         ("gio", "launch", "--", "firefox.desktop"))
        self.assertEqual(
            gio_launch_argv("org.mozilla.firefox.desktop", ["--new-window"]),
            ("gio", "launch", "--", "org.mozilla.firefox.desktop", "--new-window"))

    def test_gio_argv_validates_desktop_id_allowlist_and_metacharacters(self):
        for app_id in ("", "firefox", "../firefox.desktop", "fire desktop",
                       "app;id.desktop", "$(id).desktop", "app\n.desktop"):
            with self.subTest(app_id=repr(app_id)):
                with self.assertRaises(LaunchArgvError):
                    gio_launch_argv(app_id)
        with self.assertRaisesRegex(LaunchArgvError, "not approved"):
            gio_launch_argv("firefox.desktop",
                            allowed_app_ids=("org.mozilla.firefox.desktop",))
        self.assertEqual(
            gio_launch_argv("firefox.desktop",
                            allowed_app_ids=("firefox.desktop",)),
            ("gio", "launch", "--", "firefox.desktop"))
        with self.assertRaises(LaunchArgvError):
            gio_launch_argv("firefox.desktop", ["a; b"])
        with self.assertRaisesRegex(LaunchArgvError, "total byte bound"):
            gio_launch_argv("firefox.desktop", ["a" * MAX_TOKEN_BYTES] * 5)

    def test_module_is_pure_offline_and_platform_neutral(self):
        code = MODULE.read_text(encoding="utf-8")
        for forbidden in ("subprocess", "os.system", "Popen", "shell=True",
                          "QProcess", "socket", "QTimer", "Thread(",
                          "time.sleep", "importlib", "ctypes", "winreg",
                          "os.name", "sys.platform", "platform.system"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
