"""Regression coverage: malformed host allowlists fail closed with LaunchArgvError.

A caller-supplied allowlist is a validation boundary for build_launch_argv and
gio_launch_argv. Unhashable entries previously escaped as a built-in TypeError
from set(allowed) instead of the documented LaunchArgvError.
"""
import unittest

from canopy_features.apps.launch_argv import (
    LaunchArgvError,
    build_launch_argv,
    gio_launch_argv,
)


class HostAllowlistWrongTypeTests(unittest.TestCase):
    def test_build_launch_argv_unhashable_allowlist_entries(self):
        for allowed in ([[]], [{}], [set()], ["gio", []], [frozenset({1})]):
            with self.subTest(allowed=repr(allowed)):
                with self.assertRaises(LaunchArgvError):
                    build_launch_argv("gio", allowed_executables=allowed)

    def test_build_launch_argv_unhashable_allowlist_generator(self):
        allowed = (entry for entry in ([], "gio"))
        with self.assertRaises(LaunchArgvError):
            build_launch_argv("gio", allowed_executables=allowed)

    def test_gio_launch_argv_unhashable_allowlist_entries(self):
        app_id = "org.example.App.desktop"
        for allowed in ([[]], [{}], [app_id, {}]):
            with self.subTest(allowed=repr(allowed)):
                with self.assertRaises(LaunchArgvError):
                    gio_launch_argv(app_id, allowed_app_ids=allowed)

    def test_valid_string_allowlist_still_approved(self):
        self.assertEqual(
            build_launch_argv("gio", allowed_executables=("gio", "nemo")),
            ("gio",),
        )
        self.assertEqual(
            gio_launch_argv("org.example.App.desktop",
                            allowed_app_ids=["org.example.App.desktop"]),
            ("gio", "launch", "--", "org.example.App.desktop"),
        )

    def test_bad_allowlist_container_still_refused(self):
        for bad in (7, "gio", b"gio", {"gio": True}):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(LaunchArgvError):
                    build_launch_argv("gio", allowed_executables=bad)

    def test_unapproved_value_still_refused(self):
        with self.assertRaisesRegex(LaunchArgvError, "not approved"):
            build_launch_argv("gio", allowed_executables=("nemo",))
        with self.assertRaisesRegex(LaunchArgvError, "not approved"):
            gio_launch_argv("org.example.App.desktop",
                            allowed_app_ids=("org.other.App.desktop",))


if __name__ == "__main__":
    unittest.main()
