"""Build reproducible evidence manifests from existing screenshot captures.

Read-only: this module never captures, launches Qt, or changes the desktop.
It reuses tools.mint_classic_qt_smoke for PNG integrity and safe hashing.
A green unit test is not proof of a real Mint capture or a working desktop.
"""
import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
import re

from tools import mint_classic_qt_smoke as qt

SCHEMA_VERSION = 1
KIND = "canopy-screenshot-evidence-manifest"
MAX_CAPTURES = 64
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ManifestError(ValueError):
    """Capture set cannot be proven from files that actually exist."""


def _path_arg(value, label):
    """Return a string path or fail closed with the manifest domain error.

    Caller-supplied path values reach ``Path``/``os.fspath`` directly; a wrong
    type must not leak a raw ``TypeError`` (or be coerced into a capture-safe
    claim) at any public entry point.
    """
    message = label + " path must be a string or path-like object"
    if not isinstance(value, (str, os.PathLike)):
        raise ManifestError(message)
    try:
        path = os.fspath(value)
    except (TypeError, ValueError, OSError) as exc:
        raise ManifestError(message) from exc
    if not isinstance(path, str):
        raise ManifestError(message)
    return path


def _capture_iterable(captures):
    """Require a finite, non-string iterable of caller-supplied path values."""
    if isinstance(captures, (str, bytes, bytearray, Mapping)) or not isinstance(
            captures, Iterable):
        raise ManifestError("captures must be an iterable of path values")
    return captures


def serialize(manifest):
    """Return canonical bytes: stable order, no locale or platform endings.

    A manifest that cannot be represented as canonical JSON (non-finite
    floats, unsupported value or key types, cyclic data) is refused with
    ``ManifestError``. Raw ``json`` conversion errors must not escape this
    boundary: ``write_manifest`` and the CLI only handle ``ManifestError``.
    """
    if type(manifest) is not dict:
        raise ManifestError("manifest must be an object")
    try:
        text = json.dumps(
            manifest, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ManifestError("manifest is not serializable") from exc
    return (text + "\n").encode("ascii")


def _expected_map(expected_sha256):
    if expected_sha256 is None:
        return {}
    if type(expected_sha256) is not dict:
        raise ManifestError("expected_sha256 must be a mapping")
    for name, digest in expected_sha256.items():
        if (type(name) is not str or not name
                or type(digest) is not str or not SHA256.fullmatch(digest)):
            raise ManifestError("invalid expected SHA-256 entry")
    return expected_sha256


def build_manifest(captures, *, binary=None, expected_sha256=None):
    """Return a deterministic manifest for existing PNG capture files.

    ``captures`` is an iterable of absolute paths to real, non-symlink PNGs.
    ``binary`` optionally records the SHA-256 of the compiled binary that
    produced them. ``expected_sha256`` maps capture file names to known
    digests; any mismatch fails closed.
    """
    expected = _expected_map(expected_sha256)
    paths = []
    for item in _capture_iterable(captures):
        capture_arg = _path_arg(item, "screenshot capture")
        try:
            paths.append(qt.safe_resource(capture_arg, "screenshot capture"))
        except (OSError, qt.MintSmokeError) as exc:
            raise ManifestError("screenshot capture missing or unsafe") from exc
    if not paths or len(paths) > MAX_CAPTURES:
        raise ManifestError(
            "capture count must be between 1 and " + str(MAX_CAPTURES)
        )
    names = [path.name for path in paths]
    if len(set(names)) != len(names):
        raise ManifestError("duplicate screenshot capture name")

    entries = []
    for path in sorted(paths, key=lambda item: item.name):
        try:
            width, height = qt.png_size(path)  # CRC, zlib, bounds, variation
            digest = qt.file_sha256(path)      # O_NOFOLLOW + regular-file guard
            size = path.stat().st_size
        except (OSError, qt.MintSmokeError) as exc:
            raise ManifestError(
                "corrupt or unreadable PNG capture: " + path.name
            ) from exc
        entries.append({
            "path": path.name,
            "sha256": digest,
            "size_bytes": size,
            "width": width,
            "height": height,
        })

    actual = {entry["path"]: entry["sha256"] for entry in entries}
    if set(expected) - set(actual):
        raise ManifestError("expected SHA-256 for an unknown capture")
    for name, digest in expected.items():
        if actual[name] != digest:
            raise ManifestError("SHA-256 mismatch for capture: " + name)

    binary_sha256 = None
    if binary is not None:
        binary_arg = _path_arg(binary, "binary")
        try:
            source = qt.safe_resource(binary_arg, "capture binary")
            binary_sha256 = qt.file_sha256(source)
        except (OSError, qt.MintSmokeError) as exc:
            raise ManifestError("capture binary missing or unsafe") from exc

    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "binary_sha256": binary_sha256,
        "capture_count": len(entries),
        "entries": entries,
    }
    payload["manifest_sha256"] = hashlib.sha256(serialize(payload)).hexdigest()
    return payload


def write_manifest(path, manifest):
    """Write canonical manifest bytes to a new file; never overwrite."""
    data = serialize(manifest)
    target = Path(_path_arg(path, "manifest target"))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
    return target
