"""Offline planner for reversible, exact-byte-owned Canopy uninstalls.

This module reads a bounded JSON ownership manifest, verifies every recorded
file on disk, and returns a reviewable plan. It never deletes, creates,
chmods, executes or downloads anything. It starts no service, polls nothing,
uses no privilege and keeps memory bounded by streaming digests in fixed
chunks.

It reuses the schema-1 SHA-256 ownership marker already produced by
``tools/register_classic_preview.py``: that tool's ``HASH`` validator and
``RegistrationError`` type, plus its "exact bytes or refuse" rule.

Manifest format::

    {"schema": 1, "owner": "org.canopy.classic",
     "files": {"applications/org.canopy.ClassicPreview.desktop": "<sha256>"}}

Only regular files at safe relative paths can be planned for removal.
Directories, symlinks, paths that escape the root, modified files and
unreadable files block the whole plan. Missing files are skipped, not fatal.
A later executor must remove only ``plan.removals`` and nothing else; the
plan's expected digests are what make reinstall verification reversible.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from tools.register_classic_preview import HASH, RegistrationError


SCHEMA = 1
MAX_MANIFEST_BYTES = 64 * 1024
MAX_FILES = 4096
MAX_PATH_LENGTH = 512
CHUNK = 64 * 1024

REMOVE = "remove"
MISSING = "missing"
MISMATCH = "ownership_mismatch"
UNSAFE = "unsafe"
NOT_REGULAR = "not_regular"
UNREADABLE = "unreadable"
BLOCKING = (MISMATCH, UNSAFE, NOT_REGULAR, UNREADABLE)

_WINDOWS_DEVICE = re.compile(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$")


@dataclass(frozen=True)
class UninstallAction:
    """One recorded file and the decision reached from its on-disk state."""

    path: str
    decision: str
    expected_sha256: str
    actual_sha256: Optional[str] = None
    reason: str = ""


@dataclass(frozen=True)
class UninstallPlan:
    """Reviewable result. No field grants permission to delete anything."""

    root: str
    actions: Tuple[UninstallAction, ...]

    @property
    def removals(self) -> Tuple[str, ...]:
        return tuple(a.path for a in self.actions if a.decision == REMOVE)

    @property
    def blockers(self) -> Tuple[UninstallAction, ...]:
        return tuple(a for a in self.actions if a.decision in BLOCKING)

    @property
    def executable(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict:
        return {
            "root": self.root,
            "executable": self.executable,
            "removals": list(self.removals),
            "actions": [
                {
                    "path": a.path,
                    "decision": a.decision,
                    "expected_sha256": a.expected_sha256,
                    "actual_sha256": a.actual_sha256,
                    "reason": a.reason,
                }
                for a in self.actions
            ],
        }


def _relative_parts(value: str) -> Tuple[str, ...]:
    """Accept only plain relative forward-slash paths inside the root."""
    if not isinstance(value, str) or not value or len(value) > MAX_PATH_LENGTH:
        raise RegistrationError("invalid relative path in ownership manifest")
    if value.startswith("/") or "\\" in value or ":" in value or "\x00" in value:
        raise RegistrationError("absolute or non-portable path in ownership manifest")
    parts = tuple(value.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise RegistrationError("traversal path in ownership manifest")
    for part in parts:
        if any(ord(char) < 0x20 for char in part):
            raise RegistrationError("control character in ownership manifest path")
        if part.endswith((".", " ")) or _WINDOWS_DEVICE.fullmatch(part):
            raise RegistrationError("reserved path component in ownership manifest")
    return parts


def _load_manifest(path: Path, expected_owner: Optional[str]) -> Tuple[Optional[str], Dict[str, str]]:
    if path.is_symlink() or not path.is_file():
        raise RegistrationError("ownership manifest must be an existing real file")
    try:
        # Read one extra byte so a file that grows after the stat check is
        # still rejected without ever loading an unbounded payload.
        with path.open("rb") as handle:
            raw = handle.read(MAX_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise RegistrationError("cannot read ownership manifest") from exc
    if len(raw) > MAX_MANIFEST_BYTES:
        raise RegistrationError("ownership manifest is too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise RegistrationError("ownership manifest is not valid JSON") from exc
    if not isinstance(data, dict) or set(data) - {"schema", "owner", "files"}:
        raise RegistrationError("invalid ownership manifest fields")
    if type(data.get("schema")) is not int or data["schema"] != SCHEMA:
        raise RegistrationError("unsupported ownership manifest schema")
    files = data.get("files")
    if not isinstance(files, dict) or len(files) > MAX_FILES:
        raise RegistrationError("invalid file set in ownership manifest")
    owner = data.get("owner")
    if owner is not None and (
        not isinstance(owner, str) or not owner or len(owner) > 128
    ):
        raise RegistrationError("invalid owner in ownership manifest")
    if expected_owner is not None and owner != expected_owner:
        raise RegistrationError("ownership mismatch: manifest owner differs")
    for relative, digest in files.items():
        _relative_parts(relative)
        if not isinstance(digest, str) or not HASH.fullmatch(digest):
            raise RegistrationError("invalid digest in ownership manifest")
    return owner, files


def _digest_regular(target: Path, info: os.stat_result) -> Tuple[Optional[str], str]:
    """Hash a regular file with O_NOFOLLOW where available, in fixed chunks."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(target, flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            return None, "opened path is not a regular file"
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino) \
                and opened.st_ino and info.st_ino:
            return None, "file changed during verification"
        digest = hashlib.sha256()
        while True:
            chunk = os.read(fd, CHUNK)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest(), ""
    finally:
        os.close(fd)


def _inspect(root: Path, parts: Tuple[str, ...], expected: str) -> UninstallAction:
    current = root
    for part in parts[:-1]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return UninstallAction("/".join(parts), MISSING, expected,
                                   reason="parent directory is missing")
        except OSError as exc:
            return UninstallAction("/".join(parts), UNREADABLE, expected,
                                   reason="cannot inspect path: " + str(exc.strerror))
        if stat.S_ISLNK(info.st_mode):
            return UninstallAction("/".join(parts), UNSAFE, expected,
                                   reason="symlink in path")
        if not stat.S_ISDIR(info.st_mode):
            return UninstallAction("/".join(parts), UNSAFE, expected,
                                   reason="path component is not a directory")

    target = current / parts[-1]
    relative = "/".join(parts)
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        return UninstallAction(relative, MISSING, expected, reason="file is missing")
    except OSError as exc:
        return UninstallAction(relative, UNREADABLE, expected,
                               reason="cannot inspect file: " + str(exc.strerror))
    if stat.S_ISLNK(info.st_mode):
        return UninstallAction(relative, UNSAFE, expected, reason="symlink is not owned")
    if not stat.S_ISREG(info.st_mode):
        return UninstallAction(relative, NOT_REGULAR, expected,
                               reason="recorded path is not a regular file")
    try:
        resolved = target.resolve()
        root_resolved = root.resolve()
    except OSError as exc:
        return UninstallAction(relative, UNREADABLE, expected,
                               reason="cannot resolve path: " + str(exc.strerror))
    if not resolved.is_relative_to(root_resolved):
        return UninstallAction(relative, UNSAFE, expected,
                               reason="path escapes the install root")
    try:
        actual, error = _digest_regular(target, info)
    except OSError as exc:
        return UninstallAction(relative, UNREADABLE, expected,
                               reason="cannot read file: " + str(exc.strerror))
    if error:
        return UninstallAction(relative, UNREADABLE, expected, reason=error)
    if actual != expected:
        return UninstallAction(relative, MISMATCH, expected, actual_sha256=actual,
                               reason="file bytes differ from ownership record")
    return UninstallAction(relative, REMOVE, expected, actual_sha256=actual)


def plan_uninstall(root: os.PathLike, manifest: os.PathLike,
                   expected_owner: Optional[str] = None) -> UninstallPlan:
    """Build a fail-closed plan. Reads state only; performs no removal."""
    root_path = Path(root)
    if root_path.is_symlink() or not root_path.is_dir():
        raise RegistrationError("install root must be an existing real directory")
    _, files = _load_manifest(Path(manifest), expected_owner)
    actions = tuple(sorted(
        (_inspect(root_path, _relative_parts(relative), digest)
         for relative, digest in files.items()),
        key=lambda action: action.path,
    ))
    return UninstallPlan(str(root_path), actions)
