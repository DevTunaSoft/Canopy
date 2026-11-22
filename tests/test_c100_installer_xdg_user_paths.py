"""Offline unit tests for user-level XDG target-path validation.

Exercises symlinks (real where available, plus a deterministic simulated
component) and path traversal. No root, no writes outside a temp directory and
no desktop-session changes are needed.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canopy_features.installer import xdg_user_paths as xdg


class XdgUserPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()

    def test_user_base_defaults_are_per_user(self):
        self.assertEqual(
            xdg.user_base("XDG_DATA_HOME", home=self.home, env={}),
            self.home / ".local" / "share",
        )

    def test_all_xdg_user_defaults(self):
        expected = {
            "XDG_DATA_HOME": ".local/share",
            "XDG_CONFIG_HOME": ".config",
            "XDG_CACHE_HOME": ".cache",
            "XDG_STATE_HOME": ".local/state",
        }
        self.assertEqual(set(xdg.XDG_USER_VARS), set(expected))
        for name, suffix in expected.items():
            with self.subTest(name=name):
                self.assertEqual(
                    xdg.user_base(name, home=self.home, env={}),
                    self.home.joinpath(*suffix.split("/")),
                )

    def test_absolute_environment_override(self):
        custom = self.home / "custom data"
        result = xdg.user_base(
            "XDG_DATA_HOME", home=self.home,
            env={"XDG_DATA_HOME": str(custom)},
        )
        self.assertEqual(result, custom)

    def test_relative_environment_value_rejected(self):
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "absolute"):
            xdg.user_base("XDG_DATA_HOME", home=self.home,
                          env={"XDG_DATA_HOME": "relative"})

    def test_unsupported_variable_rejected(self):
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "unsupported"):
            xdg.user_base("XDG_SYSTEM_DIRS", home=self.home, env={})

    def test_validate_target_returns_normalized_absolute_path(self):
        base = self.home / "base"
        result = xdg.validate_target(base, "canopy/app.desktop")
        self.assertEqual(result, base / "canopy" / "app.desktop")
        self.assertTrue(result.is_absolute())

    def test_path_traversal_rejected(self):
        base = self.home / "base"
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "traversal"):
            xdg.validate_target(base, "../outside")

    def test_nested_path_traversal_rejected(self):
        base = self.home / "base"
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "traversal"):
            xdg.validate_target(base, "a/../../outside")

    def test_absolute_target_rejected(self):
        base = self.home / "base"
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "relative"):
            xdg.validate_target(base, str(self.root / "evil"))

    def test_non_absolute_base_rejected(self):
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "absolute"):
            xdg.validate_target("relative-base", "file")

    def test_oversized_path_rejected(self):
        base = self.home / "base"
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "too long"):
            xdg.validate_target(base, "a" * (xdg.MAX_PATH_CHARS + 1))

    def test_symlinked_base_component_rejected(self):
        real = self.home / "real"
        real.mkdir()
        alias = self.home / "alias"
        try:
            alias.symlink_to(real, target_is_directory=True)
        except OSError as exc:
            self.skipTest("symlink creation not permitted: " + str(exc))
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "symlink"):
            xdg.validate_target(alias, "app")

    def test_symlinked_target_directory_component_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        base = self.home / "base"
        base.mkdir()
        alias = base / "alias"
        try:
            alias.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest("symlink creation not permitted: " + str(exc))
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "symlink"):
            xdg.validate_target(base, "alias/app")

    def test_symlinked_target_file_rejected(self):
        outside = self.root / "outside.txt"
        outside.write_text("private", encoding="utf-8")
        base = self.home / "base"
        base.mkdir()
        alias = base / "linkfile"
        try:
            alias.symlink_to(outside)
        except OSError as exc:
            self.skipTest("symlink creation not permitted: " + str(exc))
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "symlink"):
            xdg.validate_target(base, "linkfile")

    def test_symlink_detection_is_component_aware(self):
        # Deterministic check of the detection logic without relying on OS
        # symlink privilege; forces one component to report as a link.
        base = self.home / "plain"
        base.mkdir()
        real_is_symlink = Path.is_symlink

        def fake_is_symlink(self):
            return self.name == "alias" or real_is_symlink(self)

        with patch.object(Path, "is_symlink", fake_is_symlink):
            with self.assertRaisesRegex(xdg.UnsafeUserPathError, "symlink"):
                xdg.validate_target(base, "alias/app")

    def test_validate_user_target_happy_path(self):
        result = xdg.validate_user_target(
            "XDG_CONFIG_HOME", "canopy/settings.ini",
            home=self.home, env={},
        )
        self.assertEqual(
            result, self.home / ".config" / "canopy" / "settings.ini"
        )

    def test_root_refused(self):
        # create=True so the patch works on hosts without os.geteuid (Windows).
        with patch.object(xdg.os, "geteuid", return_value=0, create=True):
            with self.assertRaisesRegex(xdg.UnsafeUserPathError, "root"):
                xdg.validate_user_target(
                    "XDG_DATA_HOME", "x", home=self.home, env={}
                )

    def test_base_outside_home_refused_as_global(self):
        global_dir = self.root / "global"
        with self.assertRaisesRegex(xdg.UnsafeUserPathError, "outside"):
            xdg.validate_user_target(
                "XDG_DATA_HOME", "x", home=self.home,
                env={"XDG_DATA_HOME": str(global_dir)},
            )

    def test_ensure_user_level_accepts_home_subpath(self):
        self.assertEqual(
            xdg.ensure_user_level(self.home / "a" / "b", self.home),
            self.home / "a" / "b",
        )

    def test_validation_creates_nothing(self):
        fresh = self.home / "not-created"
        self.assertFalse(fresh.exists())
        xdg.validate_target(fresh, "still/absent")
        self.assertFalse(fresh.exists())


if __name__ == "__main__":
    unittest.main()
