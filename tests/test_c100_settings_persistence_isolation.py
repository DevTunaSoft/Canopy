"""Bounded RED->GREEN isolation and rollback tests for Classic settings state.

These are host-side source-contract tests only. They create bounded temporary
directories, never start a service, never touch a system location and never
claim Qt, artwork, theme or Linux Mint acceptance.
"""

import importlib.util
import json
import os
import posixpath
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from canopy_features.accessibility import reduced_motion_contract as motion
import canopy_features.settings.persisted_preferences as source
from canopy_features.settings import (
    PersistedPreferences,
    PersistedPreferencesError,
)


class _BoundedTempMixin:
    """Give each test one bounded, self-cleaning temporary root."""

    def _root(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def _link(self, target, link):
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except (OSError, NotImplementedError, ValueError) as exc:
            self.skipTest("symlinks unavailable on this host: %s" % exc)

    def _leftovers(self, directory):
        return sorted(name for name in os.listdir(directory)
                      if name.startswith(".canopy-prefs-"))


class PerUserIsolationTests(_BoundedTempMixin, unittest.TestCase):
    def test_state_path_for_user_is_distinct_and_rooted(self):
        root = self._root()
        alice = source.state_path_for_user(root, "alice")
        bob = source.state_path_for_user(root, "bob")
        self.assertNotEqual(alice, bob)
        self.assertEqual(alice.name, bob.name)
        for path in (alice, bob):
            self.assertEqual(path.parent.parent.parent, root)

    def test_for_user_stores_do_not_share_state(self):
        root = self._root()
        alice = PersistedPreferences.for_user(root, "alice")
        bob = PersistedPreferences.for_user(root, "bob")
        self.assertNotEqual(alice.path, bob.path)
        self.assertTrue(alice.set("reduced_motion", motion.FULL))
        self.assertEqual(alice.view("reduced_motion").value, motion.FULL)
        self.assertEqual(bob.view("reduced_motion").value, motion.UNSET)
        self.assertFalse(bob.path.exists())
        self.assertEqual(
            PersistedPreferences.for_user(root, "bob").view("reduced_motion").value,
            motion.UNSET,
        )
        self.assertEqual(
            PersistedPreferences.for_user(root, "alice").view("reduced_motion").value,
            motion.FULL,
        )

    def test_user_component_rejects_escape_separators_and_wrong_types(self):
        root = self._root()
        for user in ("../bob", "a/b", "a\\b", "", ".", "..", "ALICE",
                     "bob\x00x", "a" * 65, None, 7, ["alice"]):
            with self.subTest(user=user):
                with self.assertRaises(PersistedPreferencesError):
                    source.state_path_for_user(root, user)

    def test_symlinked_user_alias_is_rejected(self):
        root = self._root()
        alice = source.state_path_for_user(root, "alice")
        alice.parent.mkdir(parents=True, exist_ok=True)
        alice.write_text(json.dumps({
            "version": 1, "values": {"reduced_motion": motion.FULL},
        }))
        alias = root / "users" / "bob"
        self._link(alice.parent, alias)
        with self.assertRaises(PersistedPreferencesError):
            source.state_path_for_user(root, "bob")
        self.assertEqual(
            PersistedPreferences.for_user(root, "alice").view("reduced_motion").value,
            motion.FULL,
        )

    def test_for_user_requires_an_existing_directory_root(self):
        root = self._root()
        with self.assertRaises(PersistedPreferencesError):
            PersistedPreferences.for_user(root / "missing", "alice")


class BoundaryRejectionTests(_BoundedTempMixin, unittest.TestCase):
    def test_symlinked_state_file_is_rejected_without_cross_user_read(self):
        root = self._root()
        alice = source.state_path_for_user(root, "alice")
        alice.parent.mkdir(parents=True, exist_ok=True)
        alice.write_text(json.dumps({
            "version": 1, "values": {"reduced_motion": motion.FULL},
        }))
        bob = source.state_path_for_user(root, "bob")
        bob.parent.mkdir(parents=True, exist_ok=True)
        self._link(alice, bob)
        with self.assertRaises(PersistedPreferencesError):
            PersistedPreferences(bob, root=root)

    def test_symlinked_ancestor_escape_is_rejected(self):
        root = self._root()
        outside = self._root()
        outside_state = outside / "users" / "alice" / "preferences.json"
        outside_state.parent.mkdir(parents=True, exist_ok=True)
        outside_state.write_text(json.dumps({
            "version": 1, "values": {"reduced_motion": motion.FULL},
        }))
        self._link(outside / "users", root / "users")
        candidate = root / "users" / "alice" / "preferences.json"
        with self.assertRaises(PersistedPreferencesError):
            PersistedPreferences(candidate, root=root)

    def test_escape_by_dotdot_or_absolute_outside_root_is_rejected(self):
        root = self._root()
        outside = self._root() / "preferences.json"
        for candidate in (outside, root / "users" / ".." / "leak.json"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(PersistedPreferencesError):
                    PersistedPreferences(candidate, root=root)

    def test_privileged_absolute_path_is_rejected(self):
        if os.name == "nt":
            privileged = Path(os.environ.get("SystemRoot", "C:\\Windows")) / \
                "System32" / "canopy-preferences.json"
        else:
            privileged = Path("/etc/canopy/preferences.json")
        with self.assertRaises(PersistedPreferencesError):
            PersistedPreferences(privileged)

    def test_unknown_unavailable_and_oversized_keys_do_not_cross_profiles(self):
        root = self._root()
        alice = source.state_path_for_user(root, "alice")
        alice.parent.mkdir(parents=True, exist_ok=True)
        alice.write_text(json.dumps({
            "version": 1, "values": {"reduced_motion": motion.FULL},
        }))
        bob = source.state_path_for_user(root, "bob")
        bob.parent.mkdir(parents=True, exist_ok=True)
        bob.write_text(json.dumps({
            "version": 1,
            "values": {
                "reduced_motion": motion.FULL,
                "power": "suspend",
                "root_override": "on",
            },
        }))
        bob_store = PersistedPreferences.for_user(root, "bob")
        self.assertEqual(bob_store.view("reduced_motion").value, motion.UNSET)
        bob.write_text(json.dumps({
            "version": 1, "values": {"a" * 65: "reduce"},
        }))
        self.assertEqual(
            PersistedPreferences.for_user(root, "bob").view("reduced_motion").value,
            motion.UNSET,
        )
        self.assertEqual(
            PersistedPreferences.for_user(root, "alice").view("reduced_motion").value,
            motion.FULL,
        )

    def test_lone_surrogate_json_key_is_discarded_fail_closed(self):
        # PR #602 review: key.encode("utf-8", "strict") raised a raw
        # UnicodeEncodeError for a lone surrogate, escaping the documented
        # discard-to-empty path. json.dumps escapes the surrogate, so the file
        # itself is plain ASCII; json.loads restores it before validation.
        root = self._root()
        path = root / "state" / "preferences.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        for key in ("\ud800", "\udfff" + "x" * 8, "reduced_motion\udc00"):
            with self.subTest(key=key):
                path.write_text(json.dumps({
                    "version": 1,
                    "values": {key: motion.FULL},
                }))
                store = PersistedPreferences(path)
                self.assertEqual(store.view("reduced_motion").value, motion.UNSET)
                self.assertTrue(store.set("reduced_motion", motion.REDUCE))
                self.assertEqual(
                    PersistedPreferences(path).view("reduced_motion").value,
                    motion.REDUCE,
                )
                path.unlink()

    def test_lone_surrogate_user_component_is_rejected(self):
        root = self._root()
        with self.assertRaises(PersistedPreferencesError):
            source.state_path_for_user(root, "al\ud800ice")


class AtomicRollbackTests(_BoundedTempMixin, unittest.TestCase):
    def test_replace_failure_rolls_back_memory_and_existing_disk_state(self):
        root = self._root()
        path = root / "state" / "preferences.json"
        store = PersistedPreferences(path)
        self.assertTrue(store.set("reduced_motion", motion.FULL))
        before = path.read_bytes()
        with mock.patch("os.replace", side_effect=OSError("replace denied")):
            with self.assertRaises(PersistedPreferencesError):
                store.set("reduced_motion", motion.REDUCE)
        self.assertEqual(store.view("reduced_motion").value, motion.FULL)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self._leftovers(path.parent), [])

    def test_replace_failure_on_first_write_leaves_no_state(self):
        path = self._root() / "state" / "preferences.json"
        store = PersistedPreferences(path)
        with mock.patch("os.replace", side_effect=OSError("replace denied")):
            with self.assertRaises(PersistedPreferencesError):
                store.set("reduced_motion", motion.FULL)
        self.assertFalse(path.exists())
        self.assertEqual(store.view("reduced_motion").value, motion.UNSET)
        self.assertEqual(self._leftovers(path.parent), [])

    def test_directory_creation_failure_is_domain_error_without_write(self):
        path = self._root() / "state" / "preferences.json"
        store = PersistedPreferences(path)
        with mock.patch("pathlib.Path.mkdir", side_effect=OSError("denied")):
            with self.assertRaises(PersistedPreferencesError):
                store.set("reduced_motion", motion.FULL)
        self.assertEqual(store.view("reduced_motion").value, motion.UNSET)
        self.assertFalse(path.exists())

    def test_rolled_back_write_does_not_touch_the_other_profile(self):
        root = self._root()
        alice = PersistedPreferences.for_user(root, "alice")
        bob = PersistedPreferences.for_user(root, "bob")
        alice.set("reduced_motion", motion.FULL)
        with mock.patch("os.replace", side_effect=OSError("replace denied")):
            with self.assertRaises(PersistedPreferencesError):
                alice.set("reduced_motion", motion.REDUCE)
        self.assertEqual(alice.view("reduced_motion").value, motion.FULL)
        self.assertEqual(bob.view("reduced_motion").value, motion.UNSET)
        self.assertFalse(bob.path.exists())


class NoPrivilegedWriteTests(_BoundedTempMixin, unittest.TestCase):
    def test_rejected_inputs_perform_no_filesystem_writes(self):
        root = self._root()
        store = PersistedPreferences(root / "state" / "preferences.json")
        with mock.patch("pathlib.Path.mkdir") as mkdir, \
                mock.patch("os.replace") as replace, \
                mock.patch("os.chmod") as chmod, \
                mock.patch("tempfile.NamedTemporaryFile") as temporary:
            self.assertFalse(store.set("power", "suspend"))
            for key, value in (("secret_admin_override", "on"),
                               ("reduced_motion", "fast")):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(PersistedPreferencesError):
                        store.set(key, value)
            self.assertFalse(store.set("theme", "dark"))
            for call in (mkdir, replace, chmod, temporary):
                self.assertFalse(call.called)

    def test_import_and_escape_attempt_perform_no_writes(self):
        spec = importlib.util.spec_from_file_location(
            "_settings_isolation_probe", source.__file__)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        root = self._root()
        outside = self._root() / "preferences.json"
        with mock.patch("pathlib.Path.mkdir") as mkdir, \
                mock.patch("os.replace") as replace, \
                mock.patch("os.chmod") as chmod, \
                mock.patch("tempfile.NamedTemporaryFile") as temporary:
            spec.loader.exec_module(module)
            with self.assertRaises(PersistedPreferencesError):
                PersistedPreferences(outside, root=root)
            with self.assertRaises(PersistedPreferencesError):
                PersistedPreferences(
                    Path(os.environ.get("SystemRoot", "C:\\Windows")) /
                    "System32" / "preferences.json"
                    if os.name == "nt" else Path("/etc/preferences.json"))
            for call in (mkdir, replace, chmod, temporary):
                self.assertFalse(call.called)

    def test_successful_write_stays_user_only(self):
        if os.name == "nt":
            self.skipTest("POSIX mode bits are not authoritative on Windows")
        root = self._root()
        store = PersistedPreferences.for_user(root, "alice")
        self.assertTrue(store.set("reduced_motion", motion.FULL))
        self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(store.path.parent.stat().st_mode), 0o700)



class WindowsPrivilegedSeparatorTests(_BoundedTempMixin, unittest.TestCase):
    """PR #618 QA: separator spelling must not open the privileged gate.

    ``_is_privileged_path`` branches on ``os.name``. A POSIX interpreter
    receiving a Windows-style path kept the privileged prefixes unmatched,
    so the same system location was refused on one host branch and accepted
    on the other. Patching only ``os.name`` exercises that branch decision on
    any host; ``os.path`` stays the native module so no fixture depends on a
    host-specific pathlib rendering.
    """

    _PRIVILEGED = (
        "C:/WINDOWS/System32/canopy-preferences.json",
        "C:\\WINDOWS\\System32\\canopy-preferences.json",
        "C:/WINDOWS\\System32/canopy-preferences.json",
        "c:/windows/system32/canopy-preferences.json",
        "C:/Program Files/App/canopy-preferences.json",
        "C:/ProgramData/App/canopy-preferences.json",
    )

    _ORDINARY = (
        "C:/Users/alice/.config/preferences.json",
        "C:\\Users\\alice\\AppData\\Roaming\\preferences.json",
        "C:/projects/canopy/state/preferences.json",
        "/home/alice/.config/preferences.json",
    )

    def _host_branch(self, name):
        return mock.patch.object(source.os, "name", name)

    def test_windows_system_prefix_matches_either_separator(self):
        for text in self._PRIVILEGED:
            for name in ("posix", "nt"):
                with self.subTest(path=text, host=name):
                    with self._host_branch(name):
                        self.assertTrue(source._is_privileged_path(text))

    def test_windows_prefix_ignores_the_active_os_path_module(self):
        # Foundation CI runs on Linux: os.path is posixpath even when a test
        # exercises the nt branch. A drive-qualified system path must still
        # be recognized; the branch must not depend on splitdrive's module.
        for text in self._PRIVILEGED:
            for name in ("nt", "posix"):
                with self.subTest(path=text, host=name):
                    with mock.patch.object(source.os, "path", posixpath), \
                            self._host_branch(name):
                        self.assertTrue(source._is_privileged_path(text))

    def test_ordinary_user_paths_are_not_privileged_with_either_separator(self):
        for text in self._ORDINARY:
            for name in ("posix", "nt"):
                with self.subTest(path=text, host=name):
                    with self._host_branch(name):
                        self.assertFalse(source._is_privileged_path(text))

    def test_windows_privileged_path_is_refused_without_any_write(self):
        for text in ("C:/WINDOWS/System32/canopy-preferences.json",
                     "C:\\WINDOWS\\System32\\canopy-preferences.json",
                     "C:/WINDOWS\\System32/canopy-preferences.json"):
            with self.subTest(path=text):
                with self._host_branch("posix"):
                    with mock.patch("pathlib.Path.mkdir") as mkdir, \
                            mock.patch("os.replace") as replace, \
                            mock.patch("os.chmod") as chmod, \
                            mock.patch("tempfile.NamedTemporaryFile") as tmp:
                        with self.assertRaises(PersistedPreferencesError) as ctx:
                            PersistedPreferences(text)
                        self.assertIn("privileged", str(ctx.exception))
                        for call in (mkdir, replace, chmod, tmp):
                            self.assertFalse(call.called)

    def test_escape_and_symlink_attempts_with_mixed_separators_still_refuse(self):
        root = self._root()
        outside = self._root()
        alias = root / "alias"
        self._link(outside, alias)
        attempts = (
            str(root) + "/alias/../users/alice/preferences.json",
            str(alias / "users" / "alice" / "preferences.json"),
        )
        for text in attempts:
            with self.subTest(path=text):
                with self._host_branch("posix"):
                    with mock.patch("pathlib.Path.mkdir") as mkdir, \
                            mock.patch("os.replace") as replace, \
                            mock.patch("os.chmod") as chmod, \
                            mock.patch("tempfile.NamedTemporaryFile") as tmp:
                        with self.assertRaises(PersistedPreferencesError):
                            PersistedPreferences(text, root=root)
                        for call in (mkdir, replace, chmod, tmp):
                            self.assertFalse(call.called)


if __name__ == "__main__":
    unittest.main()
