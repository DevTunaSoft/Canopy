"""Regression tests: hostile wrong-type path values fail closed in XDG helpers.

Every caller-supplied *path-shaped* argument of this module documents
:class:`UnsafeXdgPath` as its error type.  A bounded hostile value (an int, a
list, a dict, bytes or a broken ``__fspath__``) must produce that domain error
instead of leaking a built-in ``TypeError``/``AttributeError`` from ``pathlib``
or from a non-mapping ``env``.
"""
import os
from pathlib import Path
import tempfile
import unittest

from canopy_features.installer import xdg_user_paths as xp


class _BrokenFspath:
    def __init__(self, raised=False):
        self.raised = raised

    def __fspath__(self):
        if self.raised:
            raise TypeError("no path here")
        return b"/home/user"  # os.fspath must yield str, not bytes


class XdgHostilePathValueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.empty_env = {}

    def test_base_dir_env_path_value_wrong_type_uses_domain_error(self):
        # ``Path(chosen)`` leaked TypeError for each of these on the base tip.
        bad_values = (5, 3.5, True, False, ["/tmp"], {"p": "/tmp"}, b"/tmp",
                      _BrokenFspath(), _BrokenFspath(raised=True))
        for value in bad_values:
            with self.subTest(value=type(value).__name__):
                with self.assertRaisesRegex(xp.UnsafeXdgPath, "XDG_DATA_HOME"):
                    xp.base_dir("data", home=self.home,
                                env={"XDG_DATA_HOME": value})

    def test_base_dir_env_mapping_wrong_type_uses_domain_error(self):
        # ``environ.get(variable)`` leaked AttributeError on the base tip.
        for env in (5, 3.5, True, ["/tmp"], ("XDG_DATA_HOME",), b"env",
                    object()):
            with self.subTest(env=type(env).__name__):
                with self.assertRaisesRegex(xp.UnsafeXdgPath, "env"):
                    xp.base_dir("data", home=self.home, env=env)

    def test_home_wrong_type_uses_domain_error_on_every_entry_point(self):
        bad_homes = (5, 3.5, True, ["/tmp"], {"home": "/tmp"}, b"/tmp",
                     _BrokenFspath(), _BrokenFspath(raised=True))
        target = self.home / "ok"
        calls = (
            lambda h: xp.base_dir("data", home=h, env=self.empty_env),
            lambda h: xp.validate(str(target), home=h),
            lambda h: xp.target("data", "app", home=h, env=self.empty_env),
        )
        for index, call in enumerate(calls):
            for home in bad_homes:
                with self.subTest(entry=index, home=type(home).__name__):
                    with self.assertRaisesRegex(xp.UnsafeXdgPath, "home"):
                        call(home)

    def test_target_relative_wrong_type_uses_domain_error(self):
        bad_relatives = (5, 3.5, True, ["app"], {"a": 1}, b"app",
                         _BrokenFspath(), _BrokenFspath(raised=True))
        for relative in bad_relatives:
            with self.subTest(relative=type(relative).__name__):
                with self.assertRaisesRegex(xp.UnsafeXdgPath, "relative subpath"):
                    xp.target("data", relative, home=self.home,
                              env=self.empty_env)

    def test_valid_inputs_still_accepted(self):
        env = {"XDG_DATA_HOME": str(self.home / "custom")}
        self.assertEqual(xp.base_dir("data", home=self.home, env=env),
                         self.home / "custom")
        self.assertEqual(
            xp.target("config", "canopy/app", home=self.home,
                      env=self.empty_env),
            self.home / ".config" / "canopy" / "app",
        )
        candidate = self.home / ".cache" / "canopy"
        self.assertEqual(xp.validate(candidate, home=self.home), candidate)


if __name__ == "__main__":
    unittest.main()
