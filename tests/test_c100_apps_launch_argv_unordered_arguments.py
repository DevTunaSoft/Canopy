"""Regression: unordered argument containers cannot yield a validated argv.

``build_launch_argv`` and ``gio_launch_argv`` promise an ordered, immutable
argv tuple. A ``set``/``frozenset`` (or other set-like view) is a bounded but
wrong-type ``arguments`` container: every element can be a valid plain string,
yet iteration order is arbitrary, so the emitted argv silently changes meaning
between processes. Accepting one is a false launch-validity claim. Fail closed
with LaunchArgvError instead.
"""
import unittest

from canopy_features.apps.launch_argv import (
    LaunchArgvError,
    build_launch_argv,
    gio_launch_argv,
)


class UnorderedArgumentContainerTests(unittest.TestCase):
    def test_build_launch_argv_rejects_set_and_frozenset_arguments(self):
        for arguments in ({"b", "a"}, frozenset({"b", "a"}), {"only"}):
            with self.subTest(arguments=repr(arguments)):
                with self.assertRaisesRegex(LaunchArgvError, "ordered"):
                    build_launch_argv("app", arguments)

    def test_build_launch_argv_rejects_set_like_keys_view(self):
        with self.assertRaisesRegex(LaunchArgvError, "ordered"):
            build_launch_argv("app", {"b": 1, "a": 2}.keys())

    def test_gio_launch_argv_rejects_set_arguments(self):
        with self.assertRaisesRegex(LaunchArgvError, "ordered"):
            gio_launch_argv("org.example.App.desktop", {"--flag", "value"})

    def test_ordered_argument_sequences_still_build_normally(self):
        self.assertEqual(
            build_launch_argv("app", ["--output", "report.txt"]),
            ("app", "--output", "report.txt"),
        )
        self.assertEqual(
            gio_launch_argv("org.example.App.desktop", ("--flag", "value")),
            ("gio", "launch", "--", "org.example.App.desktop", "--flag", "value"),
        )


if __name__ == "__main__":
    unittest.main()
