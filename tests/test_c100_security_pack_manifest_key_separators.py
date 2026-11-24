"""Regression tests: executable-looking pack metadata keys with alternate separators.

The data-only metadata boundary rejects field names such as ``exec``, ``path``
or ``load`` before reading their values.  A hostile manifest can hide the same
token behind a hyphen, a dot, or camelCase (``exec-path``, ``exec.path``,
``execPath``); those spellings are token boundaries too and must fail closed.

No Qt, no pack install, no network and no code execution: every value below is
inert data that is only projected or rejected.
"""

import unittest

from canopy_features.security.pack_manifest_metadata import to_safe_metadata
from tools.check_shell_pack import PackValidationError


def valid_manifest():
    """Schema-shaped, untrusted metadata mapping with legitimate keys only."""
    return {
        "manifest_version": 1,
        "id": "com.community.calm.desktop",
        "name": "Calm Desktop",
        "description": "An original Canopy presentation pack",
        "shell_api": 1,
        "kind": "presentation",
        "ui_engine": "qt-qml",
        "entrypoint": "ui/Main.qml",
        "capabilities": ["dock", "app-launcher"],
        "switch_strategy": "same-session",
        "permissions": [],
    }


class AlternateSeparatorKeyTests(unittest.TestCase):
    def setUp(self):
        self.manifest = valid_manifest()

    def assert_key_rejected(self, key):
        manifest = dict(self.manifest)
        manifest[key] = "benign text"
        with self.assertRaisesRegex(
                PackValidationError, "executable-looking metadata field"):
            to_safe_metadata(manifest)

    def assert_key_allowed(self, key):
        manifest = dict(self.manifest)
        manifest[key] = "benign text"
        result = to_safe_metadata(manifest)
        self.assertEqual(result.pack_id, "com.community.calm.desktop")

    # --- hyphenated executable-looking keys ----------------------------------

    def test_hyphen_token_boundaries_rejected(self):
        for key in ("exec-path", "load-file", "cmd-line",
                    "run-script", "on-load"):
            with self.subTest(key=key):
                self.assert_key_rejected(key)

    # --- dotted executable-looking keys --------------------------------------

    def test_dot_token_boundaries_rejected(self):
        for key in ("exec.path", "load.file", "cmd.line",
                    "run.script", "on.load"):
            with self.subTest(key=key):
                self.assert_key_rejected(key)

    # --- camelCase executable-looking keys -----------------------------------

    def test_camel_token_boundaries_rejected(self):
        for key in ("execPath", "loadFile", "cmdLine",
                    "runScript", "onLoad"):
            with self.subTest(key=key):
                self.assert_key_rejected(key)

    # --- case-insensitive -----------------------------------------------------

    def test_uppercase_hyphen_token_rejected(self):
        self.assert_key_rejected("EXEC-PATH")

    # --- nested spellings -----------------------------------------------------

    def test_nested_hyphen_key_rejected(self):
        self.manifest["extra"] = {"exec-path": "benign"}
        with self.assertRaisesRegex(
                PackValidationError, "executable-looking metadata field"):
            to_safe_metadata(self.manifest)

    def test_nested_list_hyphen_key_rejected(self):
        self.manifest["extra"] = [{"on-load": "benign"}]
        with self.assertRaisesRegex(
                PackValidationError, "executable-looking metadata field"):
            to_safe_metadata(self.manifest)

    # --- no false positives on legitimate keys -------------------------------

    def test_legitimate_alternate_separator_keys_still_allowed(self):
        for key in ("shell_api", "shellApi", "entrypoint", "author-name",
                    "release.tag", "displayName", "theme-id"):
            with self.subTest(key=key):
                self.assert_key_allowed(key)

    def test_baseline_manifest_still_projects(self):
        result = to_safe_metadata(self.manifest)
        self.assertEqual(result.name, "Calm Desktop")
        self.assertEqual(result.capabilities, frozenset({"dock", "app-launcher"}))


if __name__ == "__main__":
    unittest.main()
