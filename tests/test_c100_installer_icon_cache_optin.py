"""Offline tests for description-only, unprivileged icon-cache opt-in."""
from dataclasses import FrozenInstanceError
import inspect
from pathlib import PurePosixPath
import shlex
import unittest

from canopy_features.installer import icon_cache_optin as ic


HOME = "/home/alice"
THEME = HOME + "/.local/share/icons/Hicolor"


def lookup(found):
    """Injectable PATH stand-in; never runs a tool."""
    return lambda name: found


class IconCacheOptinTests(unittest.TestCase):
    def describe(self, dirs=(THEME,), found=ic.CACHE_TOOL, **kwargs):
        return ic.describe_refresh(HOME, dirs, tool_lookup=lookup(found), **kwargs)

    def assert_no_privilege(self, text):
        self.assertIsNone(ic.PRIVILEGED_TOKEN.search(text), text)

    def test_available_description_is_bounded_and_user_scoped(self):
        result = self.describe(found="/opt/with space/" + ic.CACHE_TOOL)
        self.assertTrue(result.available)
        self.assertEqual(result.reason, "TOOL_AVAILABLE")
        self.assertEqual(result.directories, (THEME,))
        self.assertEqual(
            result.commands,
            ("/opt/with space/" + ic.CACHE_TOOL + " " + shlex.quote(THEME),),
        )
        for command in result.commands:
            self.assert_no_privilege(command)
            self.assertNotIn("sudo", command)
            self.assertNotIn("pkexec", command)
        self.assertIn("optional", result.text.lower())
        self.assertIn("does not run", result.text)
        self.assertIn("user-owned", result.text)

    def test_missing_cache_tool_yields_no_command(self):
        result = self.describe(found=None)
        self.assertFalse(result.available)
        self.assertEqual(result.reason, "TOOL_MISSING")
        self.assertEqual(result.commands, ())
        self.assertEqual(result.directories, (THEME,))
        self.assertIn("was not found", result.text)
        self.assertIn("does not install packages", result.text)
        for line in result.text.splitlines():
            self.assert_no_privilege(line)

    def test_forced_root_action_is_refused(self):
        with self.assertRaises(ic.PrivilegedRefreshRefused) as caught:
            self.describe(assume_root=True)
        self.assertIn("root", str(caught.exception).lower())
        with self.assertRaises(ic.IconCacheDescriptionError):
            self.describe(assume_root="yes")
        # Refusal creates no description and therefore no privileged command.
        self.assert_no_privilege(str(caught.exception))

    def test_system_icon_directory_refused(self):
        with self.assertRaises(ic.IconCacheDescriptionError):
            self.describe(dirs=("/usr/share/icons/Hicolor",))
        with self.assertRaises(ic.IconCacheDescriptionError):
            self.describe(dirs=("/home/alice2/icons",))

    def test_parent_traversal_refused(self):
        for bad in (
            HOME + "/.local/icons/../../etc",
            HOME + "/../bob/icons",
            "relative/icons",
        ):
            with self.subTest(bad=bad), self.assertRaises(ic.IconCacheDescriptionError):
                self.describe(dirs=(bad,))

    def test_privileged_tool_lookup_refused(self):
        for candidate in ("/usr/bin/sudo", "/usr/bin/pkexec", "doas", "runuser"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ic.PrivilegedRefreshRefused):
                    self.describe(found=candidate)

    def test_bounds_and_duplicates(self):
        many = tuple(HOME + "/icons/" + str(i) for i in range(ic.MAX_THEME_DIRS + 1))
        with self.assertRaises(ic.IconCacheDescriptionError):
            self.describe(dirs=many)
        with self.assertRaises(ic.IconCacheDescriptionError):
            self.describe(dirs=("",))
        with self.assertRaises(ic.IconCacheDescriptionError):
            self.describe(dirs=("x" * (ic.MAX_PATH_CHARS + 1),))
        with self.assertRaises(ic.IconCacheDescriptionError):
            self.describe(dirs=(THEME + "\nrm -rf /",))
        with self.assertRaises(ic.IconCacheDescriptionError):
            self.describe(dirs=(42,))
        with self.assertRaises(ic.IconCacheDescriptionError):
            self.describe(dirs=THEME)
        result = self.describe(dirs=(THEME, THEME, HOME + "/icons/Adwaita"))
        self.assertEqual(len(result.commands), 2)
        self.assertEqual(result.directories[0], THEME)

    def test_home_validation(self):
        for bad in ("relative/home", "/", "/usr/local/home", "/home/a/../b", "/home/a\n"):
            with self.subTest(bad=bad), self.assertRaises(ic.IconCacheDescriptionError):
                ic.describe_refresh(bad, (THEME,), tool_lookup=lookup(ic.CACHE_TOOL))
        result = ic.describe_refresh(
            PurePosixPath(HOME), (PurePosixPath(THEME),),
            tool_lookup=lookup(ic.CACHE_TOOL),
        )
        self.assertTrue(result.available)

    def test_frozen_result_and_dict_snapshot(self):
        result = self.describe()
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            result.commands += ("extra",)
        first = result.as_dict()
        first["commands"].append("tampered")
        self.assertEqual(result.as_dict()["commands"], list(result.commands))
        self.assertEqual(result.as_dict()["text"], result.text)

    def test_module_has_no_process_execution_path(self):
        # shutil.which only searches PATH; it is the injectable default.
        source = inspect.getsource(ic)
        for forbidden in ("subprocess", "os.system", "Popen", "os.exec"):
            self.assertNotIn(forbidden, source)

    def test_non_callable_tool_lookup_fails_closed(self):
        """A hostile wrong-type lookup must raise the domain error, not TypeError.

        ``tool_lookup`` is a public, injectable argument of ``describe_refresh``.
        Calling a non-callable value leaked a raw ``TypeError`` from the public
        entry point instead of the module's documented fail-closed domain error.
        """
        for bad in (None, 42, 3.5, True, "which", b"which", [1], {"a": 1}, object()):
            with self.subTest(bad=bad):
                with self.assertRaises(ic.IconCacheDescriptionError) as caught:
                    ic.describe_refresh(HOME, (THEME,), tool_lookup=bad)
                self.assertIn("lookup", str(caught.exception).lower())

    def test_default_lookup_is_offline_on_this_windows_host(self):
        # Real PATH probing only; no tool execution and no Linux Mint claim.
        result = ic.describe_refresh(HOME, (THEME,))
        self.assertIsInstance(result, ic.RefreshDescription)
        for command in result.commands:
            self.assert_no_privilege(command)
        self.assertIn("Optional icon cache refresh", result.text)


if __name__ == "__main__":
    unittest.main()
