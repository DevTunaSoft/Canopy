"""Offline tests for user-level XDG target path validation."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canopy_features.installer import xdg_user_paths as xp
from tools import register_classic_preview as _menu


class XdgUserPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.home = base / "home"
        self.home.mkdir()
        # A different tree in the same temp root: outside user home, e.g. a
        # global location or another user's files.
        self.elsewhere = base / "elsewhere"
        self.elsewhere.mkdir()
        self.empty_env = {}

    def _link(self, link, source, **kwargs):
        try:
            link.symlink_to(source, **kwargs)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symlinks unavailable on this host: %s" % exc)
        return link

    def test_default_bases_follow_xdg_spec(self):
        cases = {
            "data": self.home / ".local" / "share",
            "config": self.home / ".config",
            "cache": self.home / ".cache",
            "state": self.home / ".local" / "state",
        }
        for kind, expected in cases.items():
            with self.subTest(kind=kind):
                self.assertEqual(
                    xp.base_dir(kind, home=self.home, env=self.empty_env), expected
                )

    def test_absolute_env_base_override(self):
        chosen = self.home / "custom-data"
        self.assertEqual(
            xp.base_dir("data", home=self.home,
                        env={"XDG_DATA_HOME": str(chosen)}),
            chosen,
        )

    def test_relative_env_base_rejected(self):
        with self.assertRaisesRegex(xp.UnsafeXdgPath, "absolute"):
            xp.base_dir("config", home=self.home,
                        env={"XDG_CONFIG_HOME": "relative"})

    def test_unknown_base_kind_rejected(self):
        with self.assertRaises(xp.UnsafeXdgPath):
            xp.base_dir("bogus", home=self.home, env=self.empty_env)

    def test_real_environment_data_base_reuses_existing_installer(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.home / "real")},
                        clear=False):
            self.assertEqual(xp.base_dir("data"), Path(_menu.data_home()))

    def test_target_built_under_base(self):
        self.assertEqual(
            xp.target("data", "canopy/app", home=self.home, env=self.empty_env),
            self.home / ".local" / "share" / "canopy" / "app",
        )

    def test_absolute_subpath_rejected(self):
        with self.assertRaisesRegex(xp.UnsafeXdgPath, "subpath"):
            xp.target("data", self.elsewhere / "x", home=self.home,
                      env=self.empty_env)

    def test_traversal_in_subpath_rejected(self):
        with self.assertRaises(xp.UnsafeXdgPath):
            xp.target("data", "../escape", home=self.home, env=self.empty_env)
        with self.assertRaises(xp.UnsafeXdgPath):
            xp.target("data", "canopy/../../escape", home=self.home,
                      env=self.empty_env)

    def test_traversal_escaping_home_rejected(self):
        escape = Path(self.home, ".local", "share", "..", "..", "..", "..",
                      "escape")
        with self.assertRaisesRegex(xp.UnsafeXdgPath, "escapes"):
            xp.validate(escape, home=self.home)

    def test_internal_dot_and_dotdot_normalized(self):
        candidate = Path(self.home, ".local", "share", "..", "..", "cache")
        self.assertEqual(
            xp.validate(candidate, home=self.home),
            Path(os.path.normpath(str(self.home / "cache"))),
        )

    def test_path_outside_home_rejected_as_global(self):
        with self.assertRaisesRegex(xp.UnsafeXdgPath, "escapes"):
            xp.validate(self.elsewhere / "system" / "file", home=self.home)

    def test_env_base_outside_home_rejected(self):
        env = {"XDG_DATA_HOME": str(self.elsewhere / "data")}
        with self.assertRaisesRegex(xp.UnsafeXdgPath, "escapes"):
            xp.target("data", "canopy", home=self.home, env=env)

    def test_relative_target_rejected(self):
        with self.assertRaisesRegex(xp.UnsafeXdgPath, "absolute"):
            xp.validate(Path("relative/path"), home=self.home)

    def test_null_byte_target_rejected(self):
        with self.assertRaises(xp.UnsafeXdgPath):
            xp.validate(str(self.home) + "/bad\x00name", home=self.home)

    def test_symlinked_directory_component_rejected(self):
        outside = self.elsewhere / "target-dir"
        outside.mkdir()
        link = self._link(self.home / "linked", outside, target_is_directory=True)
        with self.assertRaisesRegex(xp.UnsafeXdgPath, "symlink"):
            xp.validate(link / "app", home=self.home)
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_leaf_rejected(self):
        outside = self.elsewhere / "note.txt"
        outside.write_text("private", encoding="utf-8")
        link = self._link(self.home / "note.txt", outside)
        with self.assertRaisesRegex(xp.UnsafeXdgPath, "symlink"):
            xp.validate(link, home=self.home)

    def test_symlinked_xdg_base_rejected(self):
        outside = self.elsewhere / "data"
        outside.mkdir()
        link = self._link(self.home / "linked-data", outside,
                          target_is_directory=True)
        env = {"XDG_DATA_HOME": str(link)}
        with self.assertRaisesRegex(xp.UnsafeXdgPath, "symlink"):
            xp.target("data", "canopy", home=self.home, env=env)
        self.assertEqual(list(outside.iterdir()), [])

    def test_root_refused(self):
        with patch.object(os, "geteuid", return_value=0, create=True):
            with self.assertRaisesRegex(xp.UnsafeXdgPath, "root"):
                xp.validate(self.home / "x", home=self.home)

    def test_validation_has_no_side_effects(self):
        candidate = self.home / ".local" / "share" / "canopy" / "app"
        result = xp.validate(candidate, home=self.home)
        self.assertEqual(result,
                         Path(os.path.normpath(str(candidate))))
        self.assertFalse((self.home / ".local").exists())
        self.assertFalse(candidate.exists())

    def test_existing_plain_file_inside_home_accepted(self):
        directory = self.home / ".config" / "canopy"
        directory.mkdir(parents=True)
        file_path = directory / "settings.ini"
        file_path.write_text("x", encoding="utf-8")
        self.assertEqual(xp.validate(file_path, home=self.home), file_path)


if __name__ == "__main__":
    unittest.main()
