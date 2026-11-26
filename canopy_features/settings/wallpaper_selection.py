"""Fail-closed wallpaper selection validation for Canopy Classic settings.

This module decides whether a caller-supplied wallpaper selection is admissible.
It answers a metadata question only: the selection must name one of the two
approved wallpaper assets -- the pinned alpine default or the manifest's
``wallpaper`` role entry -- by its exact lowercase SHA-256. An approved icon
hash is never valid for the wallpaper role, even when the bytes are genuine.

It is a pure host-side contract. It creates no daemon, opens no socket, writes
no file and changes no asset or default. When a repository root is supplied it
also re-hashes the bytes on disk and refuses symlinks and escapes, but it never
modifies what it reads. It does not compile Qt, render a frame or claim visual
acceptance.
"""
from __future__ import annotations

import collections.abc
import hashlib
import hmac
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

__all__ = [
    "APPROVED_ASSET_PREFIX",
    "MANIFEST_RELATIVE",
    "DEFAULT_WALLPAPER_PATH",
    "DEFAULT_WALLPAPER_SHA256",
    "ICONS_ROLE",
    "WALLPAPER_ROLE",
    "SCHEMA_VERSION",
    "ApprovedManifest",
    "ManifestEntry",
    "WallpaperChoice",
    "WallpaperSelectionError",
    "parse_approved_manifest",
    "load_approved_manifest",
    "approved_wallpaper_choices",
    "validate_wallpaper_selection",
]


APPROVED_ASSET_PREFIX = "prototype/classic/assets/approved"
MANIFEST_RELATIVE = APPROVED_ASSET_PREFIX + "/manifest.json"
DEFAULT_WALLPAPER_PATH = (
    APPROVED_ASSET_PREFIX + "/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png"
)
# Same exact pin as tools.check_wallpaper.APPROVED_SHA256; the gate test asserts
# the two constants never drift. The default itself is never rewritten here.
DEFAULT_WALLPAPER_SHA256 = (
    "8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381"
)

ICONS_ROLE = "icons"
WALLPAPER_ROLE = "wallpaper"
SOURCE_DEFAULT = "approved-default"
SOURCE_MANIFEST = "manifest-wallpaper-role"

SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 64 * 1024
MAX_ASSET_BYTES = 16 * 1024 * 1024
MAX_PATH_CHARS = 240
MAX_NAME_CHARS = 64

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_DRIVE_RE = re.compile(r"[A-Za-z]:")
_UNSAFE_CATEGORIES = frozenset({"Cs", "Co", "Cn", "Zl", "Zp", "Cc", "Cf"})
_SELECTION_KEYS = frozenset({"path", "sha256"})
_ENTRY_KEYS = frozenset({"name", "path", "sha256"})
_ROLE_DIRECTORIES = frozenset({ICONS_ROLE, WALLPAPER_ROLE})


class WallpaperSelectionError(ValueError):
    """Invalid selection, manifest, role or on-disk asset."""


@dataclass(frozen=True)
class ManifestEntry:
    """One exact-hash asset registered under a manifest role."""

    name: str
    path: str
    sha256: str
    role: str


@dataclass(frozen=True)
class ApprovedManifest:
    """Normalized, role-indexed v1 approved manifest."""

    icons: tuple[ManifestEntry, ...]
    wallpaper: ManifestEntry
    roles_by_path: dict[str, str]
    roles_by_sha256: dict[str, str]


@dataclass(frozen=True)
class WallpaperChoice:
    """The validated, approved wallpaper the caller may use."""

    path: str
    sha256: str
    role: str
    source: str


def _text(value, label: str, limit: int) -> str:
    """Require a bounded printable string; never raise a built-in error."""
    if not isinstance(value, str):
        raise WallpaperSelectionError(label + " must be a string")
    if not value or len(value) > limit:
        raise WallpaperSelectionError(label + " has an invalid length")
    # Categories are checked before any whitespace folding: C0 separators
    # such as U+001C are whitespace to str.split() but are unsafe here.
    for char in value:
        if unicodedata.category(char) in _UNSAFE_CATEGORIES or not char.isprintable():
            raise WallpaperSelectionError(label + " contains a control character")
    return value


def _sha256(value, label: str = "sha256") -> str:
    text = _text(value, label, 64)
    if _SHA256_RE.fullmatch(text) is None:
        raise WallpaperSelectionError(label + " must be 64 lowercase hex digits")
    return text


def _manifest_path(value) -> str:
    """Validate a role entry path relative to the approved asset root."""
    text = _text(value, "manifest path", MAX_PATH_CHARS)
    if "\\" in text or "\x00" in text:
        raise WallpaperSelectionError("manifest path has a forbidden separator")
    if text.startswith("/") or _DRIVE_RE.match(text[:2]) is not None:
        raise WallpaperSelectionError("manifest path must be relative")
    parts = text.split("/")
    if len(parts) != 2 or parts[0] not in _ROLE_DIRECTORIES:
        raise WallpaperSelectionError("manifest path is outside an approved role")
    if any(part in ("", ".", "..") for part in parts):
        raise WallpaperSelectionError("manifest path has a traversal component")
    if not parts[1].endswith(".png"):
        raise WallpaperSelectionError("manifest asset must be a PNG")
    return text


def _selection_path(value) -> str:
    """Validate a caller's repo-relative wallpaper selection path."""
    text = _text(value, "selection path", MAX_PATH_CHARS)
    if "\\" in text or "\x00" in text:
        raise WallpaperSelectionError("selection path has a forbidden separator")
    if text.startswith("/") or _DRIVE_RE.match(text[:2]) is not None:
        raise WallpaperSelectionError("selection path must be relative")
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise WallpaperSelectionError("selection path has a traversal component")
    if parts[:4] != APPROVED_ASSET_PREFIX.split("/"):
        raise WallpaperSelectionError("selection path is outside the approved tree")
    if len(parts) != 6 or parts[4] not in _ROLE_DIRECTORIES:
        raise WallpaperSelectionError("selection path is not an approved asset")
    if not parts[5].endswith(".png"):
        raise WallpaperSelectionError("selection asset must be a PNG")
    return text


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WallpaperSelectionError("duplicate manifest key: " + str(key)[:40])
        result[key] = value
    return result


def _entry(raw, role: str) -> ManifestEntry:
    if not isinstance(raw, collections.abc.Mapping):
        raise WallpaperSelectionError(role + " entry must be an object")
    try:
        keys = set(raw.keys())
    except Exception as exc:
        raise WallpaperSelectionError(role + " entry has invalid keys") from exc
    if keys != _ENTRY_KEYS:
        raise WallpaperSelectionError(role + " entry has unexpected fields")
    name = _text(raw["name"], "asset name", MAX_NAME_CHARS)
    path = _manifest_path(raw["path"])
    digest = _sha256(raw["sha256"])
    return ManifestEntry(name=name, path=APPROVED_ASSET_PREFIX + "/" + path,
                         sha256=digest, role=role)


def parse_approved_manifest(raw) -> ApprovedManifest:
    """Parse the pinned v1 manifest, rejecting duplicate keys and role clashes."""
    if not isinstance(raw, (bytes, bytearray)):
        raise WallpaperSelectionError("manifest must be bytes")
    if not raw or len(raw) > MAX_MANIFEST_BYTES:
        raise WallpaperSelectionError("manifest size is out of bounds")
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WallpaperSelectionError("manifest is not UTF-8") from exc
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except WallpaperSelectionError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise WallpaperSelectionError("manifest is not valid JSON") from exc
    if not isinstance(data, dict):
        raise WallpaperSelectionError("manifest root must be an object")
    if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise WallpaperSelectionError("unsupported manifest schema_version")
    raw_icons = data.get(ICONS_ROLE)
    if not isinstance(raw_icons, list) or not 1 <= len(raw_icons) <= 64:
        raise WallpaperSelectionError("icons role must be a bounded list")
    icons = tuple(_entry(item, ICONS_ROLE) for item in raw_icons)
    wallpaper = _entry(data.get(WALLPAPER_ROLE), WALLPAPER_ROLE)

    roles_by_path: dict[str, str] = {}
    roles_by_sha256: dict[str, str] = {}
    for item in [*icons, wallpaper]:
        for index, value in ((roles_by_path, item.path),
                             (roles_by_sha256, item.sha256)):
            if value in index:
                raise WallpaperSelectionError("manifest role collision: " + item.role)
            index[value] = item.role
    return ApprovedManifest(icons=icons, wallpaper=wallpaper,
                            roles_by_path=roles_by_path,
                            roles_by_sha256=roles_by_sha256)


def _root_path(root) -> Path:
    if isinstance(root, (bytes, bytearray)):
        raise WallpaperSelectionError("root must be a path")
    try:
        return Path(root)
    except (TypeError, ValueError) as exc:
        raise WallpaperSelectionError("root must be a path") from exc


def _no_symlink_components(root: Path, relative: str) -> Path:
    current = root
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink():
            raise WallpaperSelectionError("symlink in asset path: " + part)
    return current


def load_approved_manifest(root) -> ApprovedManifest:
    """Read the approved manifest from *root* without writing to it."""
    base = _root_path(root)
    path = _no_symlink_components(base, MANIFEST_RELATIVE)
    try:
        if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
            raise WallpaperSelectionError("approved manifest missing or oversized")
        return parse_approved_manifest(path.read_bytes())
    except OSError as exc:
        raise WallpaperSelectionError("approved manifest unreadable") from exc


def approved_wallpaper_choices(manifest: ApprovedManifest) -> tuple[WallpaperChoice, ...]:
    """Return the exact two admissible wallpaper choices; default stays first."""
    if not isinstance(manifest, ApprovedManifest):
        raise WallpaperSelectionError("manifest must be an approved manifest")
    choices = (
        WallpaperChoice(path=DEFAULT_WALLPAPER_PATH,
                        sha256=DEFAULT_WALLPAPER_SHA256,
                        role=WALLPAPER_ROLE, source=SOURCE_DEFAULT),
        WallpaperChoice(path=manifest.wallpaper.path,
                        sha256=manifest.wallpaper.sha256,
                        role=WALLPAPER_ROLE, source=SOURCE_MANIFEST),
    )
    if (len({choice.path for choice in choices}) != 2
            or len({choice.sha256 for choice in choices}) != 2):
        raise WallpaperSelectionError("approved wallpaper choices are not distinct")
    return choices


def _verify_on_disk(root, chosen: WallpaperChoice) -> None:
    base = _root_path(root)
    path = _no_symlink_components(base, chosen.path)
    try:
        if not path.is_file():
            raise WallpaperSelectionError("missing approved asset: " + chosen.path)
        size = path.stat().st_size
        if not 0 < size <= MAX_ASSET_BYTES:
            raise WallpaperSelectionError("approved asset size is out of bounds")
        if not path.resolve().is_relative_to(base.resolve()):
            raise WallpaperSelectionError("approved asset escapes the root")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
        if not hmac.compare_digest(digest.hexdigest(), chosen.sha256):
            raise WallpaperSelectionError("SHA-256 mismatch on disk: " + chosen.path)
    except OSError as exc:
        raise WallpaperSelectionError("approved asset unreadable") from exc


def validate_wallpaper_selection(selection, manifest: ApprovedManifest, *, root=None) -> WallpaperChoice:
    """Return the approved wallpaper for *selection*, or fail closed.

    The caller's role claim is never trusted: the role comes from the pinned
    manifest index. When *root* is given, the on-disk bytes must also match the
    exact approved hash and contain no symlink component.
    """
    if not isinstance(manifest, ApprovedManifest):
        raise WallpaperSelectionError("manifest must be an approved manifest")
    if isinstance(selection, (str, bytes, bytearray)) or not isinstance(
            selection, collections.abc.Mapping):
        raise WallpaperSelectionError("selection must be a mapping")
    try:
        keys = set(selection.keys())
    except Exception as exc:
        raise WallpaperSelectionError("selection has invalid keys") from exc
    if keys != _SELECTION_KEYS:
        raise WallpaperSelectionError("selection fields must be path and sha256")
    try:
        raw_path = selection["path"]
        raw_sha = selection["sha256"]
    except Exception as exc:
        raise WallpaperSelectionError("selection fields are unreadable") from exc
    path = _selection_path(raw_path)
    digest = _sha256(raw_sha)

    chosen = None
    for candidate in approved_wallpaper_choices(manifest):
        if (hmac.compare_digest(candidate.path, path)
                and hmac.compare_digest(candidate.sha256, digest)):
            chosen = candidate
            break
    if chosen is None:
        path_role = manifest.roles_by_path.get(path)
        sha_role = manifest.roles_by_sha256.get(digest)
        if ICONS_ROLE in (path_role, sha_role):
            raise WallpaperSelectionError(
                "manifest role 'icons' cannot be selected as wallpaper")
        raise WallpaperSelectionError(
            "selection is not an exact approved wallpaper-role asset")

    if root is not None:
        _verify_on_disk(root, chosen)
    return chosen
