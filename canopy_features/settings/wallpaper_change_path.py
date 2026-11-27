"""Pure source contract for wallpaper path changes at the selection boundary.

This module validates a caller-supplied request to change the Classic wallpaper
path. It is a metadata decision only: every endpoint must be one of the two
exact-hash approved wallpaper choices, and the caller must present the exact
approved manifest digest. It reads no file, opens no socket, starts no process,
and changes no asset, default, QML, C++ or workflow. It never claims visual
acceptance or owner approval.
"""
from __future__ import annotations

import collections.abc
import re
import unicodedata
from dataclasses import dataclass
from typing import Mapping

__all__ = [
    "APPROVED_ASSET_PREFIX",
    "DEFAULT_WALLPAPER_PATH",
    "DEFAULT_WALLPAPER_SHA256",
    "MANIFEST_RELATIVE",
    "MANIFEST_SHA256",
    "MANIFEST_WALLPAPER_PATH",
    "MANIFEST_WALLPAPER_SHA256",
    "SOURCE_APPROVED_DEFAULT",
    "SOURCE_MANIFEST_WALLPAPER",
    "WALLPAPER_ROLE",
    "WallpaperChangeDecision",
    "WallpaperChangeError",
    "WallpaperEndpoint",
    "validate_wallpaper_change",
]

APPROVED_ASSET_PREFIX = "prototype/classic/assets/approved"
MANIFEST_RELATIVE = APPROVED_ASSET_PREFIX + "/manifest.json"
DEFAULT_WALLPAPER_PATH = (
    APPROVED_ASSET_PREFIX
    + "/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png"
)
DEFAULT_WALLPAPER_SHA256 = (
    "8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381"
)
MANIFEST_WALLPAPER_PATH = (
    APPROVED_ASSET_PREFIX + "/wallpaper/canopy-wave-preview.png"
)
MANIFEST_WALLPAPER_SHA256 = (
    "1efa6e83deee160ce9cf225db010025f4f162975f4dfc23e6da3f3ca0973528a"
)
MANIFEST_SHA256 = (
    "5aa040ddbfeddbd38dcbd1808710676982efbc4146987c42e93eaa57ad0d4737"
)

WALLPAPER_ROLE = "wallpaper"
SOURCE_APPROVED_DEFAULT = "approved-default"
SOURCE_MANIFEST_WALLPAPER = "manifest-wallpaper-role"


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_UNSAFE_CATEGORIES = frozenset({"Cs", "Co", "Cn", "Zl", "Zp", "Cc", "Cf"})
_REQUEST_KEYS = frozenset({"current", "proposed", "manifest_sha256"})
_ENDPOINT_KEYS = frozenset({"path", "sha256", "role", "source"})
_APPROVED_ENDPOINTS = frozenset({
    (DEFAULT_WALLPAPER_PATH, DEFAULT_WALLPAPER_SHA256, WALLPAPER_ROLE,
     SOURCE_APPROVED_DEFAULT),
    (MANIFEST_WALLPAPER_PATH, MANIFEST_WALLPAPER_SHA256, WALLPAPER_ROLE,
     SOURCE_MANIFEST_WALLPAPER),
})
_APPROVED_PATHS = frozenset(item[0] for item in _APPROVED_ENDPOINTS)
_DIGEST_BY_PATH = {item[0]: item[1] for item in _APPROVED_ENDPOINTS}
_SOURCE_BY_PATH = {item[0]: item[3] for item in _APPROVED_ENDPOINTS}


class WallpaperChangeError(ValueError):
    """A change request that is not provably an approved wallpaper change."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(code + ": " + detail)


@dataclass(frozen=True)
class WallpaperEndpoint:
    """One validated endpoint of a wallpaper change."""

    path: str
    sha256: str
    role: str
    source: str


@dataclass(frozen=True)
class WallpaperChangeDecision:
    """Immutable result for a validated change request."""

    current: WallpaperEndpoint
    proposed: WallpaperEndpoint
    manifest_sha256: str
    direction: str


def _text(value, label: str, limit: int, code: str) -> str:
    if not isinstance(value, str):
        raise WallpaperChangeError(code, label + " must be a string")
    if not value or len(value) > limit:
        raise WallpaperChangeError(code, label + " has an invalid length")
    for char in value:
        if unicodedata.category(char) in _UNSAFE_CATEGORIES or not char.isprintable():
            raise WallpaperChangeError(code, label + " has an unsafe character")
    return value


def _digest(value, label: str, code: str) -> str:
    text = _text(value, label, 64, code)
    if _SHA256_RE.fullmatch(text) is None:
        raise WallpaperChangeError(code, label + " must be 64 lowercase hex digits")
    return text


def _mapping(value, code: str) -> Mapping:
    if not isinstance(value, collections.abc.Mapping):
        raise WallpaperChangeError(code, "value must be a mapping")
    return value


def _keys(value, expected: frozenset, code: str) -> Mapping:
    raw = _mapping(value, code)
    try:
        keys = frozenset(raw.keys())
    except Exception as exc:
        raise WallpaperChangeError(code, "keys are unreadable") from exc
    if keys != expected:
        raise WallpaperChangeError(code, "unexpected fields")
    return raw


def _get(data: Mapping, key: str, code: str):
    try:
        return data[key]
    except (KeyError, TypeError, IndexError) as exc:
        raise WallpaperChangeError(code, "value is unreadable") from exc


def _endpoint(raw) -> WallpaperEndpoint:
    data = _keys(raw, _ENDPOINT_KEYS, "ENDPOINT_KEYS")
    path = _text(_get(data, "path", "ENDPOINT_KEYS"), "path", 240, "PATH")
    digest = _digest(_get(data, "sha256", "ENDPOINT_KEYS"), "sha256", "BAD_HASH")
    role = _text(_get(data, "role", "ENDPOINT_KEYS"), "role", 64, "ROLE")
    source = _text(_get(data, "source", "ENDPOINT_KEYS"), "source", 64, "SOURCE")
    if path not in _APPROVED_PATHS:
        raise WallpaperChangeError("UNKNOWN_PATH", "path is not an approved wallpaper")
    if role != WALLPAPER_ROLE:
        raise WallpaperChangeError("ROLE", "role is not wallpaper")
    if digest != _DIGEST_BY_PATH[path]:
        raise WallpaperChangeError("HASH_MISMATCH",
                                   "hash does not belong to the path")
    if source != _SOURCE_BY_PATH[path]:
        raise WallpaperChangeError("SOURCE", "source does not match the path")
    return WallpaperEndpoint(path=path, sha256=digest, role=role, source=source)


def validate_wallpaper_change(change: Mapping) -> WallpaperChangeDecision:
    """Validate one caller-supplied wallpaper change request.

    The request must carry exactly ``current``, ``proposed`` and
    ``manifest_sha256``. Each endpoint must carry exactly ``path``,
    ``sha256``, ``role`` and ``source`` and must bind to one of the two
    approved wallpaper records. The current and proposed endpoints must
    differ. No file is read and nothing is applied.
    """
    data = _keys(change, _REQUEST_KEYS, "REQUEST_KEYS")
    manifest_digest = _digest(_get(data, "manifest_sha256", "REQUEST_KEYS"),
                              "manifest_sha256", "MANIFEST_DIGEST")
    if manifest_digest != MANIFEST_SHA256:
        raise WallpaperChangeError("MANIFEST_DIGEST", "manifest digest is not pinned")
    current = _endpoint(_get(data, "current", "REQUEST_KEYS"))
    proposed = _endpoint(_get(data, "proposed", "REQUEST_KEYS"))
    if current == proposed:
        raise WallpaperChangeError("NO_OP", "current and proposed are identical")
    return WallpaperChangeDecision(
        current=current,
        proposed=proposed,
        manifest_sha256=manifest_digest,
        direction=current.source + "->" + proposed.source,
    )
