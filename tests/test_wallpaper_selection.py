"""Fail-closed tests for approved Classic wallpaper selection (PE-066).

Source and byte-level checks only. No Qt launch, no Mint guest, no visual
approval claim, and no edit to any approved asset or default.
"""
from __future__ import annotations

import ast
import collections.abc
import copy
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from canopy_features.settings.wallpaper_selection import (
    APPROVED_ASSET_PREFIX,
    DEFAULT_WALLPAPER_PATH,
    DEFAULT_WALLPAPER_SHA256,
    ICONS_ROLE,
    WALLPAPER_ROLE,
    WallpaperChoice,
    WallpaperSelectionError,
    approved_wallpaper_choices,
    load_approved_manifest,
    parse_approved_manifest,
    validate_wallpaper_selection,
)
from tools.check_wallpaper import APPROVED_SHA256

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_RELATIVE = Path("prototype/classic/assets/approved/manifest.json")
MANIFEST_BYTES = (ROOT / MANIFEST_RELATIVE).read_bytes()
MANIFEST_WALLPAPER_PATH = (
    "prototype/classic/assets/approved/wallpaper/canopy-wave-preview.png"
)
MANIFEST_WALLPAPER_SHA256 = (
    "1efa6e83deee160ce9cf225db010025f4f162975f4dfc23e6da3f3ca0973528a"
)


def selection(path=DEFAULT_WALLPAPER_PATH, sha256=DEFAULT_WALLPAPER_SHA256):
    return {"path": path, "sha256": sha256}


def parse_real_manifest():
    return parse_approved_manifest(MANIFEST_BYTES)


def fixture_root():
    """Temporary repo root carrying only the approved manifest."""
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    manifest = root / MANIFEST_RELATIVE
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_bytes(MANIFEST_BYTES)
    return temp, root


@contextmanager
def cleanup(temp):
    try:
        yield
    finally:
        temp.cleanup()


class UnreadableMapping(collections.abc.Mapping):
    """A mapping whose advertised keys cannot be read."""

    def __iter__(self):
        return iter(("path", "sha256"))

    def __len__(self):
        return 2

    def __getitem__(self, key):
        raise KeyError(key)


class ApprovedWallpaperSelectionTests(unittest.TestCase):
    def test_approved_pins_are_unchanged(self):
        self.assertEqual(DEFAULT_WALLPAPER_SHA256, APPROVED_SHA256)
        self.assertEqual(
            DEFAULT_WALLPAPER_PATH,
            "prototype/classic/assets/approved/wallpaper/"
            "Canopy_Classic_Master_Wallpaper_1920x1080.png",
        )
        live = json.loads(MANIFEST_BYTES.decode("utf-8"))
        self.assertEqual(live["wallpaper"]["path"], "wallpaper/canopy-wave-preview.png")
        self.assertEqual(live["wallpaper"]["sha256"], MANIFEST_WALLPAPER_SHA256)
        self.assertEqual(len(live["icons"]), 8)
        for relative in (DEFAULT_WALLPAPER_PATH, MANIFEST_WALLPAPER_PATH):
            asset = ROOT / relative
            self.assertTrue(asset.is_file(), asset)
            self.assertFalse(asset.is_symlink(), asset)

    def test_exact_choices_come_from_default_and_manifest_role(self):
        choices = approved_wallpaper_choices(parse_real_manifest())
        self.assertIsInstance(choices, tuple)
        self.assertEqual(len(choices), 2)
        self.assertTrue(all(isinstance(choice, WallpaperChoice) for choice in choices))
        self.assertEqual(choices[0].path, DEFAULT_WALLPAPER_PATH)
        self.assertEqual(choices[0].sha256, DEFAULT_WALLPAPER_SHA256)
        self.assertEqual(choices[0].source, "approved-default")
        self.assertEqual(choices[1].path, MANIFEST_WALLPAPER_PATH)
        self.assertEqual(choices[1].sha256, MANIFEST_WALLPAPER_SHA256)
        self.assertEqual(choices[1].source, "manifest-wallpaper-role")
        self.assertTrue(all(choice.role == WALLPAPER_ROLE for choice in choices))
        self.assertEqual(len({choice.path for choice in choices}), 2)
        self.assertEqual(len({choice.sha256 for choice in choices}), 2)

    def test_pinned_default_is_accepted(self):
        result = validate_wallpaper_selection(selection(), parse_real_manifest())
        self.assertEqual(result.path, DEFAULT_WALLPAPER_PATH)
        self.assertEqual(result.sha256, DEFAULT_WALLPAPER_SHA256)
        self.assertEqual(result.role, WALLPAPER_ROLE)
        self.assertEqual(result.source, "approved-default")

    def test_manifest_wallpaper_role_is_accepted(self):
        result = validate_wallpaper_selection(
            selection(MANIFEST_WALLPAPER_PATH, MANIFEST_WALLPAPER_SHA256),
            parse_real_manifest(),
        )
        self.assertEqual(result.path, MANIFEST_WALLPAPER_PATH)
        self.assertEqual(result.source, "manifest-wallpaper-role")

    def test_icon_role_with_exact_hash_is_rejected(self):
        manifest = parse_real_manifest()
        icon = json.loads(MANIFEST_BYTES.decode("utf-8"))["icons"][0]
        hostile = selection(APPROVED_ASSET_PREFIX + "/" + icon["path"], icon["sha256"])
        with self.assertRaises(WallpaperSelectionError) as caught:
            validate_wallpaper_selection(hostile, manifest)
        self.assertIn(ICONS_ROLE, str(caught.exception))
        self.assertIn("role", str(caught.exception))

    def test_cross_field_hash_swap_is_rejected(self):
        hostile = selection(DEFAULT_WALLPAPER_PATH, MANIFEST_WALLPAPER_SHA256)
        with self.assertRaises(WallpaperSelectionError):
            validate_wallpaper_selection(hostile, parse_real_manifest())

    def test_unknown_or_missing_selection_fields_are_rejected(self):
        manifest = parse_real_manifest()
        hostile = [
            {},
            {"path": DEFAULT_WALLPAPER_PATH},
            {"sha256": DEFAULT_WALLPAPER_SHA256},
            {**selection(), "role": WALLPAPER_ROLE},
            {**selection(), "approved": True},
            [],
            (),
            b"bytes",
            "text",
            None,
            7,
            UnreadableMapping(),
        ]
        for value in hostile:
            with self.subTest(value=repr(value)[:60]):
                with self.assertRaises(WallpaperSelectionError):
                    validate_wallpaper_selection(value, manifest)

    def test_hostile_path_spellings_are_rejected(self):
        manifest = parse_real_manifest()
        hostile = [
            "../" + DEFAULT_WALLPAPER_PATH,
            "/etc/passwd.png",
            "C:/Windows/System32/wallpaper.png",
            APPROVED_ASSET_PREFIX.replace("/", "\\") + "\\wallpaper\\ok.png",
            DEFAULT_WALLPAPER_PATH + "\x00.png",
            DEFAULT_WALLPAPER_PATH + "\x1c.png",
            DEFAULT_WALLPAPER_PATH + "\ud800.png",
            DEFAULT_WALLPAPER_PATH + ".jpg",
            "a" * 241 + ".png",
            "",
        ]
        for value in hostile:
            with self.subTest(value=repr(value)[:60]):
                with self.assertRaises(WallpaperSelectionError):
                    validate_wallpaper_selection(selection(value), manifest)

    def test_hash_format_and_type_are_rejected(self):
        manifest = parse_real_manifest()
        hostile = [
            DEFAULT_WALLPAPER_SHA256.upper(),
            DEFAULT_WALLPAPER_SHA256[:-1],
            "z" * 64,
            DEFAULT_WALLPAPER_SHA256.encode("ascii"),
            None,
            42,
            ["0" * 64],
        ]
        for value in hostile:
            with self.subTest(value=repr(value)[:60]):
                with self.assertRaises(WallpaperSelectionError):
                    validate_wallpaper_selection(
                        selection(DEFAULT_WALLPAPER_PATH, value), manifest)

    def test_duplicate_manifest_keys_are_rejected(self):
        text = MANIFEST_BYTES.decode("utf-8").rstrip()
        self.assertTrue(text.endswith("}"))
        duplicate = (
            text[:-1]
            + ', "wallpaper": {"path": "wallpaper/duplicate.png", '
            + '"sha256": "'
            + "0" * 64
            + '"}}'
        ).encode("utf-8")
        with self.assertRaises(WallpaperSelectionError):
            parse_approved_manifest(duplicate)

    def test_plain_value_error_from_huge_number_is_translated(self):
        raw = b'{"schema_version": ' + b"9" * 5000 + b"}"
        with self.assertRaises(WallpaperSelectionError):
            parse_approved_manifest(raw)

    def test_manifest_role_collision_is_rejected(self):
        data = json.loads(MANIFEST_BYTES.decode("utf-8"))
        icon = data["icons"][0]
        data["wallpaper"]["path"] = icon["path"]
        data["wallpaper"]["sha256"] = icon["sha256"]
        with self.assertRaises(WallpaperSelectionError):
            parse_approved_manifest(json.dumps(data).encode("utf-8"))

    def test_manifest_wrong_role_shape_is_rejected(self):
        data = json.loads(MANIFEST_BYTES.decode("utf-8"))
        data["icons"] = {"path": "icons/Browser_Option_3.png"}
        with self.assertRaises(WallpaperSelectionError):
            parse_approved_manifest(json.dumps(data).encode("utf-8"))
        data = json.loads(MANIFEST_BYTES.decode("utf-8"))
        del data["wallpaper"]["sha256"]
        with self.assertRaises(WallpaperSelectionError):
            parse_approved_manifest(json.dumps(data).encode("utf-8"))

    def test_repository_manifest_loads_without_writes(self):
        temp, root = fixture_root()
        with cleanup(temp):
            manifest = load_approved_manifest(root)
            self.assertTrue(validate_wallpaper_selection(
                selection(), manifest).path == DEFAULT_WALLPAPER_PATH)
            self.assertEqual((root / MANIFEST_RELATIVE).read_bytes(), MANIFEST_BYTES)

    def test_ondisk_bytes_must_match_claimed_hash(self):
        temp, root = fixture_root()
        with cleanup(temp):
            asset = root / DEFAULT_WALLPAPER_PATH
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(b"substitute")
            with self.assertRaises(WallpaperSelectionError) as caught:
                validate_wallpaper_selection(
                    selection(), parse_real_manifest(), root=root)
            self.assertIn("SHA-256", str(caught.exception))
            raw = (ROOT / DEFAULT_WALLPAPER_PATH).read_bytes()
            asset.write_bytes(raw)
            result = validate_wallpaper_selection(selection(), parse_real_manifest(),
                                                  root=root)
            self.assertEqual(result.path, DEFAULT_WALLPAPER_PATH)
            self.assertEqual(result.sha256, DEFAULT_WALLPAPER_SHA256)

    def test_missing_asset_is_rejected(self):
        temp, root = fixture_root()
        with cleanup(temp):
            with self.assertRaises(WallpaperSelectionError) as caught:
                validate_wallpaper_selection(
                    selection(), parse_real_manifest(), root=root)
            self.assertIn("missing", str(caught.exception))

    def test_symlinked_asset_is_rejected(self):
        temp, root = fixture_root()
        with cleanup(temp):
            outside = Path(temp.name) / "outside.png"
            outside.write_bytes(b"outside")
            asset = root / DEFAULT_WALLPAPER_PATH
            asset.parent.mkdir(parents=True, exist_ok=True)
            try:
                asset.symlink_to(outside)
            except OSError as exc:
                self.skipTest("symlink unavailable on this host: " + str(exc))
            with self.assertRaises(WallpaperSelectionError) as caught:
                validate_wallpaper_selection(
                    selection(), parse_real_manifest(), root=root)
            self.assertIn("symlink", str(caught.exception))

    def test_symlinked_ancestor_is_rejected(self):
        temp, root = fixture_root()
        with cleanup(temp):
            outside = Path(temp.name) / "outside"
            (outside / "wallpaper").mkdir(parents=True, exist_ok=True)
            asset = outside / "wallpaper" / Path(DEFAULT_WALLPAPER_PATH).name
            asset.write_bytes(b"outside")
            link = root / APPROVED_ASSET_PREFIX / "wallpaper"
            link.parent.mkdir(parents=True, exist_ok=True)
            try:
                link.symlink_to(outside / "wallpaper", target_is_directory=True)
            except OSError as exc:
                self.skipTest("symlink unavailable on this host: " + str(exc))
            with self.assertRaises(WallpaperSelectionError) as caught:
                validate_wallpaper_selection(
                    selection(), parse_real_manifest(), root=root)
            self.assertIn("symlink", str(caught.exception))

    def test_validation_does_not_mutate_inputs(self):
        manifest = parse_real_manifest()
        before_manifest = copy.deepcopy(manifest)
        chosen = selection()
        before_choice = copy.deepcopy(chosen)
        validate_wallpaper_selection(chosen, manifest)
        self.assertEqual(manifest, before_manifest)
        self.assertEqual(chosen, before_choice)

    def test_module_never_writes_or_deletes_files(self):
        source = (ROOT / "canopy_features/settings/wallpaper_selection.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {
            "write_bytes", "write_text", "mkdir", "unlink", "rmdir", "replace",
            "chmod", "remove", "rmtree", "symlink_to", "truncate",
        }
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = None
                if isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    name = node.func.id
                if name in forbidden:
                    found.append(name)
                if name == "open":
                    for argument in node.args:
                        if isinstance(argument, ast.Constant) and isinstance(
                                argument.value, str):
                            if any(mark in argument.value for mark in ("w", "a", "x", "+")):
                                found.append("open(write)")
        self.assertEqual(found, [], found)


if __name__ == "__main__":
    unittest.main()
