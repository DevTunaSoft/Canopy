"""Read-only SHA-256 manifests and fail-closed verification.

``build_manifest`` reads declared files once, in bounded chunks, and hashes
their bytes. It never writes, renames, deletes or follows a symlink. A
manifest is a claim about bytes, not proof of a working restore; a reviewed
host must verify it again immediately before any staged write.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from .contract import (
    MAX_DOC_BYTES,
    BackupRecoveryError,
    BackupPlan,
    canonical_bytes,
    contained,
    digest_bytes,
    parse_bounded_document,
    safe_path,
    valid_logical_path,
)

SCHEMA = 1
MAX_FILE_BYTES = 8 * 1024 * 1024
_CHUNK = 64 * 1024

OK = "OK"
MISMATCH = "MISMATCH"
MISSING = "MISSING"
OVERSIZE = "OVERSIZE"
UNSAFE_PATH = "UNSAFE_PATH"
UNREADABLE = "UNREADABLE"
SCHEMA_INVALID = "SCHEMA_INVALID"


@dataclass(frozen=True)
class FileDigest:
    """Bounded result of hashing one declared file."""

    status: str
    size: int
    sha256: str


def hash_file(path: Any, *, max_bytes: int = MAX_FILE_BYTES) -> FileDigest:
    """Hash one regular file without writing or following symlinks.

    ``max_bytes`` must be a positive ``int``; a bool is refused. The whole
    open/read path is translated to the module's domain error vocabulary, so
    POSIX and Windows differ only in status, never in an escaping OSError.
    """
    if type(max_bytes) is not int or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise BackupRecoveryError("file byte bound must be positive")
    candidate = safe_path(path)
    if candidate is None:
        return FileDigest(UNSAFE_PATH, 0, "")
    try:
        mode = os.lstat(str(candidate)).st_mode
    except OSError:
        return FileDigest(MISSING, 0, "")
    import stat as _stat
    if not _stat.S_ISREG(mode):
        return FileDigest(UNSAFE_PATH, 0, "")
    digest = hashlib.sha256()
    size = 0
    try:
        with candidate.open("rb") as handle:
            while True:
                chunk = handle.read(min(_CHUNK, max_bytes + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    return FileDigest(OVERSIZE, 0, "")
                digest.update(chunk)
    except FileNotFoundError:
        return FileDigest(MISSING, 0, "")
    except OSError:
        return FileDigest(UNREADABLE, 0, "")
    return FileDigest(OK, size, digest.hexdigest())


@dataclass(frozen=True)
class ManifestEntry:
    """One logical-name-to-bytes integrity claim."""

    logical_name: str
    relative_path: str
    size: int
    sha256: str

    def to_document(self) -> Dict[str, Any]:
        return {
            "logical_name": self.logical_name,
            "relative_path": self.relative_path,
            "size": self.size,
            "sha256": self.sha256,
        }

    @classmethod
    def from_document(cls, document: Any) -> "ManifestEntry":
        if type(document) is not dict or set(document) != {
                "logical_name", "relative_path", "size", "sha256"}:
            raise BackupRecoveryError("manifest entry schema mismatch")
        if not valid_logical_path(document["logical_name"]):
            raise BackupRecoveryError("invalid manifest logical name")
        if not valid_logical_path(document["relative_path"]):
            raise BackupRecoveryError("invalid manifest relative path")
        size = document["size"]
        sha = document["sha256"]
        if (type(size) is not int or isinstance(size, bool) or not 0 <= size <= MAX_FILE_BYTES):
            raise BackupRecoveryError("invalid manifest size")
        if (type(sha) is not str or len(sha) != 64
                or any(char not in "0123456789abcdef" for char in sha)):
            raise BackupRecoveryError("invalid manifest digest")
        return cls(document["logical_name"], document["relative_path"], size, sha)


@dataclass(frozen=True)
class IntegrityManifest:
    """Canonical, bounded claim about a plan's captured bytes."""

    plan_digest: str
    entries: Tuple[ManifestEntry, ...]

    def to_document(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "plan_digest": self.plan_digest,
            "entries": [entry.to_document() for entry in self.entries],
        }

    def digest(self) -> str:
        return digest_bytes(canonical_bytes(self.to_document()))


def parse_manifest_document(document: Any) -> IntegrityManifest:
    if type(document) is not dict or set(document) != {
            "schema", "plan_digest", "entries"}:
        raise BackupRecoveryError("manifest document schema mismatch")
    if type(document["schema"]) is not int or document["schema"] != SCHEMA:
        raise BackupRecoveryError("unsupported manifest schema")
    plan_digest = document["plan_digest"]
    if (type(plan_digest) is not str or len(plan_digest) != 64
            or any(char not in "0123456789abcdef" for char in plan_digest)):
        raise BackupRecoveryError("invalid manifest plan digest")
    entries = document["entries"]
    if type(entries) is not list or not 1 <= len(entries) <= 64:
        raise BackupRecoveryError("manifest entries out of bound")
    checked = [ManifestEntry.from_document(item) for item in entries]
    names = [entry.logical_name for entry in checked]
    paths = [entry.relative_path for entry in checked]
    if len(set(names)) != len(names) or len(set(paths)) != len(paths):
        raise BackupRecoveryError("duplicate manifest identity or path")
    return IntegrityManifest(plan_digest, tuple(checked))


@dataclass(frozen=True)
class ManifestResult:
    """Outcome of a bounded, read-only manifest build."""

    status: str
    manifest: Optional[IntegrityManifest]
    reasons: Tuple[str, ...]


def build_manifest(root: Any, plan: BackupPlan, *,
                   max_bytes: int = MAX_FILE_BYTES) -> ManifestResult:
    """Hash every plan source under ``root`` without writing anything.

    A source whose path escapes ``root``, is a symlink, is missing or exceeds
    the byte bound fails the whole build. The caller never receives a partial
    manifest that could later be mistaken for a complete backup.
    """
    if not isinstance(plan, BackupPlan):
        raise BackupRecoveryError("plan must be a BackupPlan")
    base = safe_path(root)
    if base is None:
        return ManifestResult(UNSAFE_PATH, None, (UNSAFE_PATH,))
    entries: list = []
    reasons: list = []
    for source in plan.sources:
        candidate = safe_path(base.joinpath(*source.relative_path.split("/")))
        if candidate is None or not contained(candidate, base):
            reasons.append(UNSAFE_PATH)
            continue
        result = hash_file(candidate, max_bytes=max_bytes)
        if result.status != OK:
            reasons.append(result.status)
            continue
        entries.append(ManifestEntry(
            source.logical_name, source.relative_path, result.size, result.sha256))
    if reasons:
        return ManifestResult(reasons[0], None, tuple(dict.fromkeys(reasons)))
    return ManifestResult(OK, IntegrityManifest(plan.digest(), tuple(entries)), ())


@dataclass(frozen=True)
class IntegrityResult:
    """Fail-closed verification result for one manifest and one root."""

    status: str
    mismatches: Tuple[str, ...]
    reasons: Tuple[str, ...]

    @property
    def verified(self) -> bool:
        return self.status == OK and not self.mismatches and not self.reasons


def verify_manifest(manifest: Any, root: Any, *,
                    max_bytes: int = MAX_FILE_BYTES) -> IntegrityResult:
    """Re-hash declared bytes and compare every field, never trusting claims.

    Wrong types, a corrupt durable document, an entry outside ``root`` and a
    changed deployment all produce a non-verified result rather than an
    exception or a partial PASS.
    """
    if isinstance(manifest, (bytes, bytearray)):
        try:
            manifest = parse_manifest_document(parse_bounded_document(manifest))
        except BackupRecoveryError:
            return IntegrityResult(SCHEMA_INVALID, (), (SCHEMA_INVALID,))
    if not isinstance(manifest, IntegrityManifest):
        return IntegrityResult(SCHEMA_INVALID, (), (SCHEMA_INVALID,))
    if type(max_bytes) is not int or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise BackupRecoveryError("file byte bound must be positive")
    base = safe_path(root)
    if base is None:
        return IntegrityResult(UNSAFE_PATH, (), (UNSAFE_PATH,))
    mismatches: list = []
    reasons: list = []
    for entry in manifest.entries:
        candidate = safe_path(base.joinpath(*entry.relative_path.split("/")))
        if candidate is None or not contained(candidate, base):
            reasons.append(UNSAFE_PATH)
            continue
        result = hash_file(candidate, max_bytes=max_bytes)
        if result.status != OK:
            reasons.append(result.status)
            continue
        if result.size != entry.size or result.sha256 != entry.sha256:
            mismatches.append(entry.logical_name)
    if reasons:
        status = reasons[0]
    elif mismatches:
        status = MISMATCH
    else:
        status = OK
    return IntegrityResult(status, tuple(mismatches), tuple(dict.fromkeys(reasons)))
