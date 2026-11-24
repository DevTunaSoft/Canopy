"""Offline tests for the symlink component defense.

No Qt compilation, no Linux Mint guest and no privileged action is claimed.
Race tests inject controlled state changes; they never spawn a real attacker.
"""
import errno
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest import mock

from canopy_features.security import symlink_component_defense as defense


class SymlinkComponentDefenseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.real = self.base / "real"
        (self.real / "child" / "leaf" / "deep").mkdir(parents=True)
        self.clean = self.real / "child" / "leaf"

    def make_link(self, name, target, *, directory=True):
        path = self.base / name
        try:
            path.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError, ValueError) as exc:
            self.skipTest("symlink creation unavailable: %s" % exc)
        return path

    def test_clean_nested_directory_is_accepted(self):
        result = defense.reject_symlink_components(self.clean)
        self.assertEqual(str(result), os.path.abspath(str(self.clean)))

    def test_verified_directory_yields_usable_handle(self):
        with defense.verified_directory(self.clean) as (fd, path):
            self.assertEqual(str(path), os.path.abspath(str(self.clean)))
            if defense._POSIX_FD:
                self.assertIsInstance(fd, int)
                self.assertTrue(stat.S_ISDIR(os.fstat(fd).st_mode))
            else:
                self.assertIsNone(fd)

    def test_final_component_symlink_is_rejected(self):
        alias = self.make_link("leaf-alias", self.clean)
        self.assertTrue(alias.is_symlink())
        with self.assertRaises(defense.UnsafePathError):
            defense.reject_symlink_components(alias)

    def test_nested_component_symlink_is_rejected(self):
        alias = self.make_link("child-alias", self.real / "child")
        guarded = alias / "leaf"
        self.assertTrue(guarded.is_dir())
        with self.assertRaises(defense.UnsafePathError):
            defense.reject_symlink_components(guarded)

    def test_two_nested_links_in_one_path_are_rejected(self):
        (self.base / "d1").mkdir()
        first = self.make_link("d1/a", self.real)
        second = self.make_link("d1/a/b", self.real / "child")
        guarded = second / "leaf"
        self.assertTrue(guarded.is_dir())
        self.assertEqual(
            defense.find_symlink_component(guarded), "a"
        )
        with self.assertRaises(defense.UnsafePathError):
            defense.reject_symlink_components(guarded)

    def test_detector_reports_first_link_and_ignores_clean_path(self):
        alias = self.make_link("nested", self.real / "child")
        self.assertEqual(
            defense.find_symlink_component(alias / "leaf"), "nested"
        )
        self.assertIsNone(defense.find_symlink_component(self.clean))

    def test_relative_path_is_normalised_then_checked(self):
        alias = self.make_link("rel", self.clean)
        cwd = os.getcwd()
        os.chdir(self.base)
        self.addCleanup(os.chdir, cwd)
        with self.assertRaises(defense.UnsafePathError):
            defense.reject_symlink_components("rel")

    def test_traversal_missing_and_empty_paths_fail_closed(self):
        trav = os.path.join(str(self.base), "x", "..", "real")
        with self.assertRaisesRegex(defense.UnsafePathError, r"\.\."):
            defense.reject_symlink_components(trav)
        with self.assertRaises(defense.UnsafePathError):
            defense.reject_symlink_components(self.base / "missing")
        with self.assertRaises(defense.UnsafePathError):
            defense.reject_symlink_components("")
        with self.assertRaises(defense.UnsafePathError):
            defense.reject_symlink_components("bad\x00path")

    def test_fd_walk_simulation_uses_nofollow_and_rejects_flagged_component(self):
        nofollow, directory, rdonly = 1, 2, 4
        symlinks = set()
        open_fds = {}
        seen = []

        def fake_open(path, flags, dir_fd=None):
            seen.append((os.fspath(path), flags))
            if dir_fd is None:
                current = "/"
            else:
                name = os.fspath(path)
                if name in symlinks:
                    raise OSError(errno.ELOOP, "simulated symlink swap")
                current = open_fds[id(dir_fd)].rstrip("/") + "/" + name
            handle = types.SimpleNamespace(path=current)
            open_fds[id(handle)] = current
            return handle

        def fake_close(fd):
            open_fds.pop(id(fd), None)

        overrides = (
            ("O_NOFOLLOW", nofollow),
            ("O_DIRECTORY", directory),
            ("O_RDONLY", rdonly),
        )
        patches = [
            mock.patch.object(defense.os, name, value, create=True)
            for name, value in overrides
        ]
        patches += [
            mock.patch.object(defense.os, "open", fake_open),
            mock.patch.object(defense.os, "close", fake_close),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

        parts = ("/", "home", "user", "dir")
        handle = defense._open_verified_fd(parts)
        self.assertEqual(handle.path, "/home/user/dir")
        self.assertEqual(len(seen), len(parts))
        for _, flags in seen:
            self.assertTrue(flags & nofollow)
            self.assertTrue(flags & directory)
        fake_close(handle)
        symlinks.add("user")  # race: verified directory is now a symlink
        with self.assertRaises(defense.UnsafePathError):
            defense._open_verified_fd(parts)
        self.assertEqual(open_fds, {})

    @unittest.skipUnless(defense._POSIX_FD, "needs POSIX dir_fd/O_NOFOLLOW")
    def test_every_component_open_uses_nofollow_and_directory(self):
        real_open = os.open
        seen = []

        def spy(path, flags, *args, **kwargs):
            seen.append(flags)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(defense.os, "open", spy):
            defense.reject_symlink_components(self.clean)
        self.assertTrue(seen)
        for flags in seen:
            self.assertTrue(flags & os.O_NOFOLLOW)
            self.assertTrue(flags & os.O_DIRECTORY)

    @unittest.skipUnless(defense._POSIX_FD, "needs POSIX dir_fd/O_NOFOLLOW")
    def test_race_swap_to_symlink_at_open_is_rejected(self):
        real_open = os.open

        def racing_open(path, flags, *args, **kwargs):
            if os.fspath(path) == "child":
                raise OSError(errno.ELOOP, "component swapped to symlink")
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(defense.os, "open", racing_open):
            with self.assertRaises(defense.UnsafePathError):
                defense.reject_symlink_components(self.clean)

    def test_race_component_type_change_seen_by_portable_detector(self):
        real_lstat = os.lstat

        def flipping_lstat(path, *args, **kwargs):
            if os.fspath(path).endswith("child"):
                return types.SimpleNamespace(st_mode=stat.S_IFLNK | 0o777)
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(defense.os, "lstat", flipping_lstat):
            self.assertEqual(defense.find_symlink_component(self.clean), "child")
            if not defense._POSIX_FD:
                with self.assertRaises(defense.UnsafePathError):
                    defense.reject_symlink_components(self.clean)

    def test_race_component_vanishing_midwalk_fails_closed(self):
        primitive = "open" if defense._POSIX_FD else "lstat"
        original = getattr(os, primitive)
        state = {"calls": 0}

        def flaky(path, *args, **kwargs):
            state["calls"] += 1
            if state["calls"] == 2:
                raise FileNotFoundError("component swapped during walk")
            return original(path, *args, **kwargs)

        with mock.patch.object(defense.os, primitive, flaky):
            with self.assertRaises(defense.UnsafePathError):
                defense.reject_symlink_components(self.clean)
        self.assertGreaterEqual(state["calls"], 2)

    def test_guard_creates_or_modifies_no_files(self):
        alias = self.make_link("probe", self.clean)
        before = sorted(str(p) for p in self.base.rglob("*"))
        with self.assertRaises(defense.UnsafePathError):
            defense.reject_symlink_components(alias)
        self.assertEqual(before, sorted(str(p) for p in self.base.rglob("*")))


if __name__ == "__main__":
    unittest.main()
