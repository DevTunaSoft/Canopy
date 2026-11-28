"""Bounded value types and read-only planning for backup/recovery.

Everything in this module is pure: it validates caller-supplied descriptions,
projects them into canonical documents, and computes digests. It performs no
filesystem writes, starts no process, and imports no system/Qt state. The
immutable-host boundary lives in :mod:`canopy_features.backup_recovery.restore`
and is a *decision*, never an application.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

SCHEMA = 1
TOOL_NAME = "lacos_backup_recovery"
TOOL_VERSION = "1.0.0"

# The only host surfaces this contract is ever allowed to describe. Anything
# outside this set is a core/deployment path and is refused by restore.py.
BACKUP_SCOPE = ("owner_data", "versioned_state")

MAX_SOURCES = 64
MAX_LABEL_BYTES = 64
MAX_PATH_BYTES = 256
MAX_DOC_BYTES = 1024 * 1024
MAX_REASONS = 32

LABEL = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
DEPLOYMENT = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_RELATIVE = re.compile(r"(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+\Z")

PLANNING = "PLANNING"
SEALED = "SEALED"
ROLLBACK = "ROLLBACK"
FAILED = "FAILED"

ALLOW_STAGED = "ALLOW_STAGED"
REFUSE = "REFUSE"
BLOCKED = "BLOCKED"
NOT_RUN = "NOT_RUN"
OK = "OK"

DEPLOYMENT_CHANGED = "DEPLOYMENT_CHANGED"
GUEST_NOT_RUN = "GUEST_NOT_RUN"
INTEGRITY_FAILED = "INTEGRITY_FAILED"
OWNER_DATA_CONFLICT = "OWNER_DATA_CONFLICT"
PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"
ROLLBACK_IN_FLIGHT = "ROLLBACK_IN_FLIGHT"
TARGET_NOT_CONTAINED = "TARGET_NOT_CONTAINED"


class BackupRecoveryError(ValueError):
    """A description, bound, path, or transition is invalid; fail closed."""


class _DuplicateKey(ValueError):
    """Internal sentinel for a JSON object that repeats a key."""


def _pairs(pairs):
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey("duplicate JSON key")
        result[key] = value
    return result


def canonical_bytes(document: Any) -> bytes:
    """Deterministic, bounded, canonical UTF-8 JSON for digests and journals."""
    try:
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise BackupRecoveryError("document is not JSON serializable") from exc
    if len(payload) > MAX_DOC_BYTES:
        raise BackupRecoveryError("document exceeds canonical byte bound")
    return payload


def digest_bytes(payload: bytes) -> str:
    """SHA-256 of bounded bytes, returned as lowercase hex."""
    if not isinstance(payload, bytes):
        raise BackupRecoveryError("digest input must be bytes")
    if len(payload) > MAX_DOC_BYTES:
        raise BackupRecoveryError("digest input exceeds byte bound")
    return hashlib.sha256(payload).hexdigest()


def parse_bounded_document(raw: bytes) -> Any:
    """Parse one bounded JSON document with duplicate keys rejected.

    Catches the plain ``ValueError`` raised by CPython's integer-digit limit
    as well as ``json.JSONDecodeError``; neither may escape as a raw traceback
    from an untrusted checkpoint or provenance document.
    """
    if not isinstance(raw, bytes) or len(raw) > MAX_DOC_BYTES:
        raise BackupRecoveryError("document bytes exceed their bound")
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (_DuplicateKey, UnicodeError, ValueError, TypeError) as exc:
        raise BackupRecoveryError("document is not valid canonical JSON") from exc


def valid_label(value: Any) -> bool:
    """True only for an exact, lowercase, bounded ``str`` identifier."""
    return (type(value) is str and len(value.encode("utf-8")) <= MAX_LABEL_BYTES
            and LABEL.fullmatch(value) is not None)


def valid_deployment(value: Any) -> bool:
    """True only for an opaque bounded deployment label (never a path)."""
    return (type(value) is str and len(value.encode("utf-8")) <= MAX_LABEL_BYTES
            and DEPLOYMENT.fullmatch(value) is not None)


def valid_logical_path(value: Any) -> bool:
    """True for a bounded relative POSIX-style name with no traversal.

    Backslashes, absolute paths, ``..`` segments, duplicate separators and
    control characters are all refused. Logical names are what a backup and
    a staged restore refer to; real guest paths are resolved only by a
    reviewed host adapter (which this package never invokes).
    """
    if type(value) is not str or not value:
        return False
    if len(value.encode("utf-8")) > MAX_PATH_BYTES:
        return False
    if "\\" in value or "\x00" in value:
        return False
    if any(not char.isprintable() for char in value):
        return False
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return False
    return _RELATIVE.fullmatch(value) is not None


def safe_path(value: Any) -> Optional[Path]:
    """Return an absolute ``Path`` or ``None`` if the caller path is unsafe.

    Rejects non-str/PathLike objects, bytes, NUL, ``..`` components and a
    symlink at *any* existing component. Mirrors the project's bounded config
    recovery primitive so a hostile path cannot escape via a symlinked parent.
    """
    if isinstance(value, (bytes, bytearray)) or not isinstance(
            value, (str, os.PathLike)):
        return None
    try:
        text = os.fspath(value)
    except Exception:
        return None
    if not isinstance(text, str) or not text or "\x00" in text:
        return None
    if os.pardir in Path(text).parts:
        return None
    try:
        candidate = Path(os.path.abspath(text))
    except (OSError, ValueError):
        return None
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        except OSError:
            return None
        if stat.S_ISLNK(mode):
            return None
    return candidate


def contained(path: Path, root: Path) -> bool:
    """True when ``path`` is strictly under ``root`` (not equal to it)."""
    if not isinstance(path, Path) or not isinstance(root, Path):
        return False
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return path != root


@dataclass(frozen=True)
class SourceSpec:
    """One bounded owner-data or versioned-state item to back up."""

    logical_name: str
    relative_path: str
    scope: str

    def to_document(self) -> Dict[str, str]:
        return {
            "logical_name": self.logical_name,
            "relative_path": self.relative_path,
            "scope": self.scope,
        }

    @classmethod
    def from_document(cls, document: Any) -> "SourceSpec":
        if type(document) is not dict or set(document) != {
                "logical_name", "relative_path", "scope"}:
            raise BackupRecoveryError("source spec schema mismatch")
        if not valid_label(document["logical_name"]):
            raise BackupRecoveryError("invalid source logical name")
        if not valid_logical_path(document["relative_path"]):
            raise BackupRecoveryError("invalid source relative path")
        if document["scope"] not in BACKUP_SCOPE:
            raise BackupRecoveryError("source scope is outside the backup scope")
        return cls(document["logical_name"], document["relative_path"],
                   document["scope"])


@dataclass(frozen=True)
class BackupPlan:
    """Immutable, read-only description of what a backup would capture."""

    plan_id: str
    deployment_id: str
    sources: Tuple[SourceSpec, ...]
    description: str = ""

    @property
    def source_names(self) -> Tuple[str, ...]:
        return tuple(source.logical_name for source in self.sources)

    def to_document(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "plan_id": self.plan_id,
            "deployment_id": self.deployment_id,
            "sources": [source.to_document() for source in self.sources],
            "description": self.description,
        }

    def digest(self) -> str:
        return digest_bytes(canonical_bytes(self.to_document()))


def build_plan(plan_id: str, deployment_id: str, sources: Iterable[SourceSpec],
               description: str = "") -> BackupPlan:
    """Validate a caller plan without touching the filesystem.

    ``sources`` must be a finite list/tuple of :class:`SourceSpec`; an
    unbounded iterator or a string is refused. Duplicate logical names and
    duplicate relative paths are refused so a manifest cannot silently alias
    two different files under one identity.
    """
    if not valid_label(plan_id):
        raise BackupRecoveryError("invalid plan id")
    if not valid_deployment(deployment_id):
        raise BackupRecoveryError("invalid deployment id")
    if type(sources) not in (list, tuple) or not 1 <= len(sources) <= MAX_SOURCES:
        raise BackupRecoveryError("source set must hold 1 to 64 entries")
    if type(description) is not str or len(description.encode("utf-8")) > MAX_PATH_BYTES:
        raise BackupRecoveryError("invalid plan description")
    names: set = set()
    paths: set = set()
    checked: list = []
    for source in sources:
        if not isinstance(source, SourceSpec):
            raise BackupRecoveryError("source must be a SourceSpec")
        if source.logical_name in names or source.relative_path in paths:
            raise BackupRecoveryError("duplicate source identity or path")
        names.add(source.logical_name)
        paths.add(source.relative_path)
        checked.append(SourceSpec.from_document(source.to_document()))
    return BackupPlan(plan_id, deployment_id, tuple(checked), description)


def parse_plan_document(document: Any) -> BackupPlan:
    """Rebuild a plan from an untrusted durable document, fail closed."""
    if type(document) is not dict or set(document) != {
            "schema", "plan_id", "deployment_id", "sources", "description"}:
        raise BackupRecoveryError("plan document schema mismatch")
    if type(document["schema"]) is not int or document["schema"] != SCHEMA:
        raise BackupRecoveryError("unsupported plan schema")
    sources = document["sources"]
    specs = [SourceSpec.from_document(item) for item in sources] if type(
        sources) is list else sources
    return build_plan(document["plan_id"], document["deployment_id"], specs,
                      document["description"])


@dataclass(frozen=True)
class ProvenanceRecord:
    """Where a checkpoint came from, expressed only as bounded labels."""

    plan_id: str
    deployment_id: str
    guest_class: str
    captured_at: str
    notes: str = ""

    def to_document(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "plan_id": self.plan_id,
            "deployment_id": self.deployment_id,
            "guest_class": self.guest_class,
            "captured_at": self.captured_at,
            "notes": self.notes,
        }

    def digest(self) -> str:
        return digest_bytes(canonical_bytes(self.to_document()))


def parse_provenance_document(document: Any) -> ProvenanceRecord:
    if type(document) is not dict or set(document) != {
            "schema", "tool", "tool_version", "plan_id", "deployment_id",
            "guest_class", "captured_at", "notes"}:
        raise BackupRecoveryError("provenance document schema mismatch")
    if (type(document["schema"]) is not int or document["schema"] != SCHEMA
            or document["tool"] != TOOL_NAME
            or document["tool_version"] != TOOL_VERSION):
        raise BackupRecoveryError("unsupported provenance version")
    if not valid_label(document["plan_id"]) or not valid_deployment(
            document["deployment_id"]):
        raise BackupRecoveryError("invalid provenance identity")
    if document["guest_class"] not in ("SYNTHETIC", "REAL_GUEST_NOT_RUN"):
        raise BackupRecoveryError("invalid provenance guest class")
    if (type(document["captured_at"]) is not str
            or len(document["captured_at"].encode("utf-8")) > MAX_LABEL_BYTES
            or type(document["notes"]) is not str
            or len(document["notes"].encode("utf-8")) > MAX_PATH_BYTES):
        raise BackupRecoveryError("invalid provenance text field")
    return ProvenanceRecord(
        document["plan_id"], document["deployment_id"], document["guest_class"],
        document["captured_at"], document["notes"])


@dataclass(frozen=True)
class CheckpointRecord:
    """Durable checkpoint state; all flags are derived from stored fields."""

    schema: int
    plan_id: str
    deployment_id: str
    state: str
    generation: int
    provenance_digest: str
    integrity_digest: str
    rollback_deployment: Optional[str]

    def to_document(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "plan_id": self.plan_id,
            "deployment_id": self.deployment_id,
            "state": self.state,
            "generation": self.generation,
            "provenance_digest": self.provenance_digest,
            "integrity_digest": self.integrity_digest,
            "rollback_deployment": self.rollback_deployment,
        }

    @property
    def sealed(self) -> bool:
        return self.state == SEALED and self.generation >= 0

    @property
    def rollback_in_flight(self) -> bool:
        return self.state == ROLLBACK


def parse_checkpoint_document(document: Any) -> CheckpointRecord:
    required = {"schema", "plan_id", "deployment_id", "state", "generation",
                "provenance_digest", "integrity_digest", "rollback_deployment"}
    if type(document) is not dict or set(document) != required:
        raise BackupRecoveryError("checkpoint document schema mismatch")
    if type(document["schema"]) is not int or document["schema"] != SCHEMA:
        raise BackupRecoveryError("unsupported checkpoint schema")
    if not valid_label(document["plan_id"]) or not valid_deployment(
            document["deployment_id"]):
        raise BackupRecoveryError("invalid checkpoint identity")
    if document["state"] not in (PLANNING, SEALED, ROLLBACK, FAILED):
        raise BackupRecoveryError("invalid checkpoint state")
    if type(document["generation"]) is not int or isinstance(
            document["generation"], bool) or not 0 <= document["generation"] <= 1024:
        raise BackupRecoveryError("invalid checkpoint generation")
    for field in ("provenance_digest", "integrity_digest"):
        value = document[field]
        if (type(value) is not str or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)):
            raise BackupRecoveryError("invalid checkpoint digest")
    rollback = document["rollback_deployment"]
    if rollback is not None and not valid_deployment(rollback):
        raise BackupRecoveryError("invalid rollback deployment label")
    if document["state"] == ROLLBACK and rollback is None:
        raise BackupRecoveryError("rollback state needs a deployment label")
    return CheckpointRecord(
        document["schema"], document["plan_id"], document["deployment_id"],
        document["state"], document["generation"],
        document["provenance_digest"], document["integrity_digest"], rollback)


def bound_reasons(reasons: Iterable[str]) -> Tuple[str, ...]:
    """Project at most ``MAX_REASONS`` bounded reason codes in stable order."""
    result: list = []
    for reason in reasons:
        if not isinstance(reason, str) or not reason:
            raise BackupRecoveryError("reason must be a non-empty string")
        if len(reason.encode("utf-8")) > MAX_LABEL_BYTES:
            reason = reason[:MAX_LABEL_BYTES]
        if reason not in result:
            result.append(reason)
        if len(result) == MAX_REASONS:
            break
    return tuple(result)


@dataclass(frozen=True)
class RestoreDecision:
    """A contract-level decision; never a write or a live-system action."""

    action: str
    steps: Tuple[str, ...]
    reasons: Tuple[str, ...]
    target_root: Optional[str]
    deployment_check: str

    @property
    def allowed(self) -> bool:
        return self.action == ALLOW_STAGED

    @property
    def safe_to_apply(self) -> bool:
        # Derived from durable fields, not an overridable subclass flag.
        return (self.allowed and bool(self.steps) and self.deployment_check == OK
                and TARGET_NOT_CONTAINED not in self.reasons
                and OWNER_DATA_CONFLICT not in self.reasons)

    def to_document(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "steps": list(self.steps),
            "reasons": list(self.reasons),
            "target_root": self.target_root,
            "deployment_check": self.deployment_check,
            "allowed": self.allowed,
            "safe_to_apply": self.safe_to_apply,
        }
