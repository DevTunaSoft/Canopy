"""Fail-closed restore decisions with owner-data safety and no core mutation.

This module produces a *decision and a staged plan*, never an applied restore.
The only legal destination is a dedicated staging root below ``restore/`` that
is reviewed by a host before any promotion. Live owner-data paths, immutable
system paths and atomic deployment state are never named as write targets.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Tuple

from .contract import (
    ALLOW_STAGED,
    BLOCKED,
    INTEGRITY_FAILED,
    MAX_SOURCES,
    MAX_PATH_BYTES,
    NOT_RUN,
    OK,
    OWNER_DATA_CONFLICT,
    PROVENANCE_MISMATCH,
    REFUSE,
    ROLLBACK_IN_FLIGHT,
    TARGET_NOT_CONTAINED,
    BackupPlan,
    BackupRecoveryError,
    CheckpointRecord,
    ProvenanceRecord,
    RestoreDecision,
    bound_reasons,
    valid_deployment,
)
from .integrity import IntegrityManifest, IntegrityResult

CORE_MUTATION_REFUSED = "CORE_MUTATION_REFUSED"
CHECKPOINT_NOT_SEALED = "CHECKPOINT_NOT_SEALED"
DEPLOYMENT_CHANGED = "DEPLOYMENT_CHANGED"
GUEST_NOT_RUN = "GUEST_NOT_RUN"
INVALID_INPUT = "INVALID_INPUT"
ROLLBACK_CHECKPOINT_MISSING = "ROLLBACK_CHECKPOINT_MISSING"
ROLLBACK_NOT_PINNED = "ROLLBACK_NOT_PINNED"

_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_TIME_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")

DENIED_ROOT_SEGMENTS = frozenset({
    "core", "canopy_core", "deployment", "system", "usr", "etc", "opt",
    "var", "boot", "home", "root",
})
_SEGMENT = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


def valid_restore_root(value: Any) -> bool:
    """True only for a bounded dedicated staging root under ``restore/``.

    A host root, a deployment path and any core/system segment are refused so
    a staged restore can never name a live owner file or an immutable system
    path as its destination.
    """
    if type(value) is not str or not value:
        return False
    if len(value.encode("utf-8")) > MAX_PATH_BYTES or "\x00" in value or "\\" in value:
        return False
    if any(not char.isprintable() for char in value):
        return False
    parts = value.split("/")
    if len(parts) < 2 or parts[0] != "restore":
        return False
    if any(part in ("", ".", "..") for part in parts):
        return False
    if any(part in DENIED_ROOT_SEGMENTS for part in parts[1:]):
        return False
    return all(_SEGMENT.fullmatch(part) is not None for part in parts)


@dataclass(frozen=True)
class RollbackCheckpointView:
    """Read-only mirror of the in-flight atomic-update rollback checkpoint.

    The P1 atomic-updates contract describes a retained previous deployment
    with ``deployment_id``, ``commit_digest``, ``pinned`` and ``created_at``.
    This view accepts those four plain values without importing that unmerged
    module, so backup/recovery can gate on "a pinned rollback exists" while
    remaining independent of its release state.
    """

    deployment_id: str
    commit_digest: str
    pinned: bool
    created_at: str

    def __post_init__(self) -> None:
        if not valid_deployment(self.deployment_id):
            raise BackupRecoveryError("rollback deployment label is invalid")
        if type(self.commit_digest) is not str or not _DIGEST_RE.fullmatch(
                self.commit_digest):
            raise BackupRecoveryError("rollback commit digest is invalid")
        if type(self.pinned) is not bool:
            raise BackupRecoveryError("rollback pinned flag must be bool")
        if (type(self.created_at) is not str or len(self.created_at) > 32
                or not _TIME_RE.fullmatch(self.created_at)):
            raise BackupRecoveryError("rollback timestamp is invalid")

    def to_document(self) -> dict:
        return {
            "deployment_id": self.deployment_id,
            "commit_digest": self.commit_digest,
            "pinned": self.pinned,
            "created_at": self.created_at,
        }


def rollback_gate(view: RollbackCheckpointView) -> Tuple[str, ...]:
    """Return refusal reasons for a mirrored rollback checkpoint."""
    if not isinstance(view, RollbackCheckpointView):
        raise BackupRecoveryError("rollback view must be a RollbackCheckpointView")
    if not view.pinned:
        return (ROLLBACK_CHECKPOINT_MISSING, ROLLBACK_NOT_PINNED)
    return ()


def _as_names(values: Any) -> frozenset:
    """Validate a caller set of bounded logical names, fail closed."""
    if type(values) not in (list, tuple, set, frozenset):
        raise BackupRecoveryError("owner target set must be a finite collection")
    names = set()
    for value in values:
        if type(value) is not str or not value or len(value.encode("utf-8")) > MAX_PATH_BYTES:
            raise BackupRecoveryError("owner target name is invalid")
        names.add(value)
    return frozenset(names)


def evaluate_restore(
    *,
    checkpoint: CheckpointRecord,
    plan: BackupPlan,
    provenance: ProvenanceRecord,
    manifest: IntegrityManifest,
    integrity: IntegrityResult,
    current_deployment_id: str,
    target_root: str,
    existing_targets: Iterable[str] = (),
    acked_targets: Iterable[str] = (),
    guest_class: str = "SYNTHETIC",
    rollback_view: Optional[RollbackCheckpointView] = None,
) -> RestoreDecision:
    """Derive a bounded restore decision; perform no I/O and no promotion.

    ``ALLOW_STAGED`` means a reviewed host *may* stage bytes into the dedicated
    root. It never means restore to a live owner path or to an immutable
    deployment. Every gate that fails adds a reason and downgrades the action
    to ``REFUSE`` or ``BLOCKED``/``NOT_RUN``; no flag is inferred from an
    overridable property.
    """
    for name, expected in (
        ("checkpoint", CheckpointRecord), ("plan", BackupPlan),
        ("provenance", ProvenanceRecord), ("manifest", IntegrityManifest),
        ("integrity", IntegrityResult),
    ):
        if not isinstance(locals()[name], expected):
            raise BackupRecoveryError(name + " must be a contract record")
    if not valid_deployment(current_deployment_id):
        raise BackupRecoveryError("current deployment id is invalid")
    if type(guest_class) is not str or guest_class not in (
            "SYNTHETIC", "REAL_GUEST_NOT_RUN"):
        raise BackupRecoveryError("guest class is invalid")
    existing = _as_names(existing_targets)
    acked = _as_names(acked_targets)
    if rollback_view is not None and not isinstance(
            rollback_view, RollbackCheckpointView):
        raise BackupRecoveryError("rollback view must be a RollbackCheckpointView")

    reasons: list = []
    if guest_class != "SYNTHETIC":
        return RestoreDecision(NOT_RUN, (), bound_reasons((GUEST_NOT_RUN,)),
                               None, GUEST_NOT_RUN)

    if checkpoint.rollback_in_flight:
        reasons.append(ROLLBACK_IN_FLIGHT)
    if rollback_view is not None:
        reasons.extend(rollback_gate(rollback_view))
    if not checkpoint.sealed:
        reasons.append(CHECKPOINT_NOT_SEALED)
    deployment_check = OK if checkpoint.deployment_id == current_deployment_id else DEPLOYMENT_CHANGED
    if deployment_check != OK:
        reasons.append(DEPLOYMENT_CHANGED)

    if (provenance.digest() != checkpoint.provenance_digest
            or provenance.plan_id != plan.plan_id
            or provenance.deployment_id != checkpoint.deployment_id):
        reasons.append(PROVENANCE_MISMATCH)

    if not integrity.verified:
        reasons.append(INTEGRITY_FAILED)
    if manifest.plan_digest != plan.digest():
        reasons.append(INTEGRITY_FAILED)
    if manifest.digest() != checkpoint.integrity_digest:
        reasons.append(INTEGRITY_FAILED)

    if not valid_restore_root(target_root):
        reasons.append(TARGET_NOT_CONTAINED)

    conflicts: list = []
    for source in plan.sources:
        first = source.logical_name.split("/")[0]
        if first in DENIED_ROOT_SEGMENTS:
            reasons.append(CORE_MUTATION_REFUSED)
        if source.logical_name in existing and source.logical_name not in acked:
            conflicts.append(source.logical_name)
    if conflicts:
        reasons.append(OWNER_DATA_CONFLICT)

    ordered = tuple(dict.fromkeys(reasons))
    if ordered:
        return RestoreDecision(REFUSE, (), bound_reasons(ordered),
                               target_root if valid_restore_root(target_root) else None,
                               deployment_check)

    steps: list = []
    for source in plan.sources:
        step = "STAGE " + source.logical_name + " -> " + target_root + "/" + source.relative_path
        if len(step.encode("utf-8")) > MAX_PATH_BYTES * 2:
            raise BackupRecoveryError("restore step exceeds its bound")
        steps.append(step)
        if len(steps) > MAX_SOURCES:
            raise BackupRecoveryError("restore plan exceeds source bound")
    steps.append("REVIEW_REQUIRED before any promotion")
    return RestoreDecision(ALLOW_STAGED, tuple(steps), bound_reasons((OK,)),
                           target_root, OK)
