"""Plan a reversible uninstall without touching unrelated paths.

Offline, side-effect-free planning from an installer ownership manifest. The
planner verifies every owned file by SHA-256 (same trust model as
``tools/register_classic_preview.py``) and fails closed: if any owned file is
missing, changed, a symlink, or reached through an unsafe path, it proposes
no deletion at all. Directories are proposed for removal only when they would
be empty once the verified owned files are gone.

The manifest is trusted input::

    {"schema": 1, "files": {"relative/path": "<64 hex sha256>", ...}}

Paths use forward slashes and stay relative to the install root. This module
never deletes, never mounts, and never escalates privilege; it only computes
a plan for a separate executor to review and carry out. The install root and
manifest path must be real paths: a symlink in any existing path component is
unsafe and fails closed, not just a symlink at the final component.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

SCHEMA = 1
MAX_MANIFEST_BYTES = 1 << 20  # Keep manifest parsing bounded (1 MiB).
_CHUNK = 64 * 1024  # Stream file digests; never read a whole file into RAM.
_HEX = frozenset("0123456789abcdef")


class UninstallIntegrityError(ValueError):
    """Raised for a malformed or unsafe ownership manifest."""


@dataclass(frozen=True)
class UninstallPlan:
    """Result of planning. ``remove_*`` are populated only when ``safe``.

    Paths are relative, POSIX-style strings under the install root. An
    executor must refuse to act unless ``safe`` is True; when it is False,
    ``blockers`` explains why and ``remove_files`` is empty.
    """

    safe: bool
    remove_files: tuple[str, ...]
    remove_dirs: tuple[str, ...]
    preserved: tuple[str, ...]
    blockers: tuple[str, ...]


def _digest_hex(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_parts(rel):
    """Validate an owned path and return its components as a tuple."""
    if not isinstance(rel, str) or not rel or "\x00" in rel or "\\" in rel:
        raise UninstallIntegrityError("invalid owned path: " + repr(rel))
    if rel.startswith("/"):
        raise UninstallIntegrityError("absolute owned path refused: " + rel)
    parts = tuple(rel.split("/"))
    for part in parts:
        if part in ("", ".", ".."):
            raise UninstallIntegrityError("unsafe component in owned path: " + rel)
        if len(part) >= 2 and part[1] == ":" and part[0].isalpha():
            raise UninstallIntegrityError("drive-qualified owned path refused: " + rel)
    return parts


def normalize_manifest(data):
    """Validate a parsed manifest and return a normalized copy."""
    if not isinstance(data, dict):
        raise UninstallIntegrityError("manifest must be a JSON object")
    schema = data.get("schema")
    if type(schema) is not int or schema != SCHEMA:
        raise UninstallIntegrityError("unsupported manifest schema")
    files = data.get("files")
    if not isinstance(files, dict):
        raise UninstallIntegrityError("manifest files must be an object")
    normalized = {}
    for rel, digest in files.items():
        _safe_parts(rel)
        if (not isinstance(digest, str) or len(digest) != 64
                or any(char not in _HEX for char in digest)):
            raise UninstallIntegrityError("invalid digest for " + str(rel))
        normalized[rel] = digest
    return {"schema": SCHEMA, "files": normalized}


def _require_real_path_components(path, message):
    """Raise ``UninstallIntegrityError`` if any existing component is a link.

    A leaf-only ``is_symlink()`` check is defeated by an aliased parent: the
    install root (or manifest) resolves outside the declared tree while the
    plan still records the declared path. Walk every component with ``lstat``
    (never ``resolve``) so ordinary multi-component Windows temp paths behave
    as before. ``..`` is refused rather than collapsed lexically, which could
    conceal the alias. The walk stops at the first missing component; no link
    can exist beneath a component that does not exist.
    """
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise UninstallIntegrityError(message) from exc
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise UninstallIntegrityError(message)
    if os.pardir in Path(raw).parts:
        raise UninstallIntegrityError(message)
    try:
        parts = Path(os.path.abspath(raw)).parts
    except (OSError, ValueError) as exc:
        raise UninstallIntegrityError(message) from exc
    if not parts:
        raise UninstallIntegrityError(message)
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        except OSError as exc:
            raise UninstallIntegrityError(message) from exc
        if stat.S_ISLNK(mode):
            raise UninstallIntegrityError(message)


def read_manifest(path):
    """Read and validate an ownership manifest from disk."""
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise UninstallIntegrityError("manifest must be a regular file")
    _require_real_path_components(
        source, "manifest path contains a symlinked or unsafe ancestor")
    if source.stat().st_size > MAX_MANIFEST_BYTES:
        raise UninstallIntegrityError("manifest too large")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise UninstallIntegrityError("manifest is not valid JSON") from exc
    return normalize_manifest(data)


def _symlinked_ancestor(root, parts):
    current = root
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _owned_directories(owned):
    """Return owned directory paths, deepest first, as POSIX strings."""
    dirs = set()
    for rel in owned:
        parts = _safe_parts(rel)
        for depth in range(1, len(parts)):
            dirs.add("/".join(parts[:depth]))
    return sorted(dirs, key=lambda value: (-value.count("/") - 1, value))


def plan_uninstall(root, manifest):
    """Compute an uninstall plan for ``root`` using a validated manifest.

    ``manifest`` is a dict (see :func:`normalize_manifest`). No filesystem
    entry is modified. Fails closed on any integrity problem.
    """
    manifest = normalize_manifest(manifest)
    root = Path(root)
    owned = manifest["files"]
    blockers = []
    verified = []

    if root.is_symlink():
        blockers.append("install root is a symlink")
        return UninstallPlan(False, (), (), (), tuple(blockers))
    try:
        _require_real_path_components(
            root, "install root contains a symlinked or unsafe ancestor")
    except UninstallIntegrityError as exc:
        blockers.append(str(exc))
        return UninstallPlan(False, (), (), (), tuple(blockers))

    for rel in sorted(owned):
        parts = _safe_parts(rel)
        candidate = root.joinpath(*parts)
        if _symlinked_ancestor(root, parts):
            blockers.append("symlinked parent directory for " + rel)
            continue
        if candidate.is_symlink():
            blockers.append("owned path is a symlink: " + rel)
            continue
        if not candidate.exists():
            blockers.append("MISSING owned file: " + rel)
            continue
        if not candidate.is_file():
            blockers.append("owned path is not a regular file: " + rel)
            continue
        try:
            actual = _sha256_file(candidate)
        except OSError as exc:
            blockers.append("unreadable owned file: " + rel + " (" + str(exc) + ")")
            continue
        if actual != owned[rel]:
            blockers.append("OWNERSHIP MISMATCH: " + rel)
            continue
        verified.append(rel)

    if blockers:
        return UninstallPlan(False, (), (), (), tuple(blockers))

    preserved = []
    removable = set()
    for directory in _owned_directories(owned):
        path = root.joinpath(*directory.split("/"))
        if path.is_symlink() or not path.is_dir():
            continue
        can_remove = True
        try:
            entries = list(path.iterdir())
        except OSError:
            continue
        for entry in entries:
            rel_entry = directory + "/" + entry.name
            if entry.is_symlink():
                preserved.append("unrelated symlink preserved: " + rel_entry)
                can_remove = False
            elif entry.is_file():
                if rel_entry in owned and rel_entry in verified:
                    continue
                preserved.append("unrelated file preserved: " + rel_entry)
                can_remove = False
            elif entry.is_dir():
                if rel_entry in removable:
                    continue
                preserved.append("directory kept: " + rel_entry)
                can_remove = False
            else:
                preserved.append("non-regular entry preserved: " + rel_entry)
                can_remove = False
        if can_remove:
            removable.add(directory)

    remove_dirs = tuple(
        directory for directory in _owned_directories(owned)
        if directory in removable
    )
    return UninstallPlan(
        True,
        tuple(verified),
        remove_dirs,
        tuple(dict.fromkeys(preserved)),
        (),
    )


def plan_uninstall_file(root, manifest_path):
    """Convenience wrapper: read a manifest from disk, then plan."""
    return plan_uninstall(root, read_manifest(manifest_path))
