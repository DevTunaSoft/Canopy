"""Targeted tests for the PE-100 wallpaper change path source contract.

Pure source-contract tests only: no Qt, no runtime wallpaper change, no
approved asset, manifest, QML, C++ or workflow edit, and no visual approval.
"""
from __future__ import annotations

import ast
import collections.abc
import hashlib
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from canopy_features.settings.wallpaper_change_path import (
    DEFAULT_WALLPAPER_PATH,
    DEFAULT_WALLPAPER_SHA256,
    MANIFEST_RELATIVE,
    MANIFEST_SHA256,
    MANIFEST_WALLPAPER_PATH,
    MANIFEST_WALLPAPER_SHA256,
    SOURCE_MANIFEST_WALLPAPER,
    WallpaperChangeError,
    validate_wallpaper_change,
)


def endpoint(path: object = DEFAULT_WALLPAPER_PATH,
             sha256: object = DEFAULT_WALLPAPER_SHA256,
             role: object = "wallpaper",
             source: object = "approved-default"):
    return {"path": path, "sha256": sha256, "role": role, "source": source}


def wave_endpoint():
    return endpoint(MANIFEST_WALLPAPER_PATH, MANIFEST_WALLPAPER_SHA256,
                    source="manifest-wallpaper-role")


def change(current=None, proposed=None, manifest_sha256: object = MANIFEST_SHA256):
    return {
        "current": current if current is not None else endpoint(),
        "proposed": proposed if proposed is not None else wave_endpoint(),
        "manifest_sha256": manifest_sha256,
    }


class UnreadableMapping(collections.abc.Mapping):
    """Mapping that advertises keys but refuses every value read."""

    def __init__(self, keys):
        self._keys = frozenset(keys)

    def __getitem__(self, key):
        raise KeyError(key)

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)


class WallpaperChangePathTests(unittest.TestCase):
    def test_default_to_manifest_wallpaper_is_an_approved_change(self):
        decision = validate_wallpaper_change(change())
        self.assertEqual(decision.current.path, DEFAULT_WALLPAPER_PATH)
        self.assertEqual(decision.proposed.sha256, MANIFEST_WALLPAPER_SHA256)
        self.assertEqual(decision.manifest_sha256, MANIFEST_SHA256)
        self.assertEqual(decision.direction,
                         "approved-default->manifest-wallpaper-role")

    def assert_refused(self, request, code):
        with self.assertRaises(WallpaperChangeError) as caught:
            validate_wallpaper_change(request)
        self.assertEqual(caught.exception.code, code)

    def test_manifest_wallpaper_to_default_is_an_approved_change(self):
        decision = validate_wallpaper_change(
            change(current=wave_endpoint(), proposed=endpoint()))
        self.assertEqual(decision.direction,
                         "manifest-wallpaper-role->approved-default")
        self.assertEqual(decision.current.sha256, MANIFEST_WALLPAPER_SHA256)
        self.assertEqual(decision.proposed.sha256, DEFAULT_WALLPAPER_SHA256)

    def test_identical_endpoints_are_not_a_change(self):
        self.assert_refused(change(proposed=endpoint()), "NO_OP")

    def test_unknown_path_is_rejected(self):
        other_copy = endpoint(
            path="prototype/classic/assets/wallpapers/"
                 "Canopy_Classic_Master_Wallpaper_1920x1080.png")
        self.assert_refused(change(current=other_copy), "UNKNOWN_PATH")

    def test_icon_hash_cannot_be_presented_as_a_wallpaper(self):
        icon_hash = ("28283672dec0621172f3cf793dc6f00174fdce944d986ff1"
                     "44a1d2d1a881469a")
        self.assert_refused(change(proposed=endpoint(sha256=icon_hash)),
                            "HASH_MISMATCH")

    def test_hash_must_belong_to_the_claimed_path(self):
        self.assert_refused(change(
            proposed=endpoint(sha256=MANIFEST_WALLPAPER_SHA256)),
            "HASH_MISMATCH")

    def test_wrong_role_is_rejected(self):
        self.assert_refused(change(proposed=endpoint(role="icons")), "ROLE")

    def test_wrong_source_for_path_is_rejected(self):
        self.assert_refused(change(
            current=endpoint(source=SOURCE_MANIFEST_WALLPAPER)), "SOURCE")

    def test_non_lowercase_hash_is_rejected(self):
        self.assert_refused(change(
            proposed=endpoint(sha256=MANIFEST_WALLPAPER_SHA256.upper())),
            "BAD_HASH")

    def test_manifest_digest_drift_is_rejected(self):
        self.assert_refused(change(manifest_sha256="0" * 64),
                            "MANIFEST_DIGEST")

    def test_extra_request_field_is_rejected(self):
        request = change()
        request["approved"] = True
        self.assert_refused(request, "REQUEST_KEYS")

    def test_extra_endpoint_field_is_rejected(self):
        proposed = wave_endpoint()
        proposed["note"] = "trusted"
        self.assert_refused(change(proposed=proposed), "ENDPOINT_KEYS")

    def test_non_mapping_request_is_rejected(self):
        self.assert_refused([change()], "REQUEST_KEYS")

    def test_non_mapping_endpoint_is_rejected(self):
        self.assert_refused(change(proposed=tuple(wave_endpoint().items())),
                            "ENDPOINT_KEYS")

    def test_wrong_endpoint_field_types_are_rejected(self):
        self.assert_refused(change(proposed=endpoint(path=17)), "PATH")
        self.assert_refused(change(proposed=endpoint(role=b"wallpaper")), "ROLE")
        self.assert_refused(change(proposed=endpoint(source=None)), "SOURCE")
        self.assert_refused(change(proposed=endpoint(sha256=42)), "BAD_HASH")

    def test_wrong_manifest_field_type_is_rejected(self):
        self.assert_refused(change(manifest_sha256=42), "MANIFEST_DIGEST")

    def test_control_character_in_path_is_rejected(self):
        hostile = DEFAULT_WALLPAPER_PATH + "\x1c"
        self.assert_refused(change(proposed=endpoint(path=hostile)), "PATH")

    def test_private_use_character_in_source_is_rejected(self):
        hostile = SOURCE_MANIFEST_WALLPAPER + "\ue000"
        hostile_endpoint = endpoint(
            path=MANIFEST_WALLPAPER_PATH,
            sha256=MANIFEST_WALLPAPER_SHA256,
            source=hostile)
        self.assert_refused(change(proposed=hostile_endpoint), "SOURCE")

    def test_oversized_path_is_rejected(self):
        self.assert_refused(change(proposed=endpoint(path="a" * 241)), "PATH")

    def test_unreadable_request_is_rejected_with_domain_error(self):
        self.assert_refused(
            UnreadableMapping(("current", "proposed", "manifest_sha256")),
            "REQUEST_KEYS")

    def test_unreadable_endpoint_is_rejected_with_domain_error(self):
        self.assert_refused(
            change(current=UnreadableMapping(
                ("path", "sha256", "role", "source"))),
            "ENDPOINT_KEYS")

    def test_pinned_hashes_paths_and_manifest_digest_are_exact(self):
        self.assertEqual(
            DEFAULT_WALLPAPER_PATH,
            "prototype/classic/assets/approved/wallpaper/"
            "Canopy_Classic_Master_Wallpaper_1920x1080.png")
        self.assertEqual(
            DEFAULT_WALLPAPER_SHA256,
            "8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381")
        self.assertEqual(
            MANIFEST_WALLPAPER_PATH,
            "prototype/classic/assets/approved/wallpaper/canopy-wave-preview.png")
        self.assertEqual(
            MANIFEST_WALLPAPER_SHA256,
            "1efa6e83deee160ce9cf225db010025f4f162975f4dfc23e6da3f3ca0973528a")
        self.assertEqual(
            MANIFEST_SHA256,
            "5aa040ddbfeddbd38dcbd1808710676982efbc4146987c42e93eaa57ad0d4737")

    def test_pinned_hashes_match_committed_approved_bytes(self):
        root = Path(__file__).resolve().parents[1]
        for relative, expected in (
            (MANIFEST_RELATIVE, MANIFEST_SHA256),
            (DEFAULT_WALLPAPER_PATH, DEFAULT_WALLPAPER_SHA256),
            (MANIFEST_WALLPAPER_PATH, MANIFEST_WALLPAPER_SHA256),
        ):
            with self.subTest(relative=relative):
                self.assertEqual(
                    hashlib.sha256((root / relative).read_bytes()).hexdigest(),
                    expected)

    def test_decision_is_immutable(self):
        decision = validate_wallpaper_change(change())
        with self.assertRaises(FrozenInstanceError):
            setattr(decision, "direction", "tampered")

    def test_module_has_no_io_imports_or_write_calls(self):
        source = (Path(__file__).resolve().parents[1]
                  / "canopy_features/settings/wallpaper_change_path.py").read_text(
                      encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        forbidden_calls = {"open", "write", "write_bytes", "write_text", "mkdir",
                           "unlink", "rmtree", "remove", "replace", "chmod",
                           "symlink_to", "Popen", "run", "call", "socket",
                           "connect", "sleep"}
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    calls.add(func.id)
                elif isinstance(func, ast.Attribute):
                    calls.add(func.attr)
        self.assertLessEqual(
            imports, {"__future__", "collections", "re", "unicodedata",
                      "dataclasses", "typing"})
        self.assertEqual(calls & forbidden_calls, set())
        self.assertNotIn("wallpaper_selection", source)
        self.assertNotIn("check_wallpaper", source)


if __name__ == "__main__":
    unittest.main()
