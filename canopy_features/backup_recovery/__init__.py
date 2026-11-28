"""Bounded, read-only-first backup/recovery contract for LacOS.

This package defines a host-agnostic contract only. It never mutates an
immutable system, never writes to a live owner-data path, and never promotes
a restore into a running desktop. Real-guest application is deliberately out
of scope and is recorded ``BLOCKED`` / ``NOT_RUN`` in the accompanying docs.

Public entry points are re-exported here for callers and for the synthetic
fixture tool under ``tools/lacos_backup_recovery``.
"""
from .contract import (  # noqa: F401
    ALLOW_STAGED,
    BACKUP_SCOPE,
    BLOCKED,
    DEPLOYMENT_CHANGED,
    FAILED,
    GUEST_NOT_RUN,
    INTEGRITY_FAILED,
    MAX_DOC_BYTES,
    MAX_LABEL_BYTES,
    MAX_PATH_BYTES,
    MAX_REASONS,
    MAX_SOURCES,
    NOT_RUN,
    OK,
    OWNER_DATA_CONFLICT,
    PLANNING,
    PROVENANCE_MISMATCH,
    REFUSE,
    ROLLBACK,
    ROLLBACK_IN_FLIGHT,
    SCHEMA,
    SEALED,
    TARGET_NOT_CONTAINED,
    TOOL_NAME,
    TOOL_VERSION,
    BackupPlan,
    BackupRecoveryError,
    CheckpointRecord,
    ProvenanceRecord,
    RestoreDecision,
    SourceSpec,
    build_plan,
    canonical_bytes,
    contained,
    digest_bytes,
    parse_bounded_document,
    parse_checkpoint_document,
    parse_plan_document,
    parse_provenance_document,
    safe_path,
    valid_label,
    valid_logical_path,
)
from .integrity import (  # noqa: F401
    MAX_FILE_BYTES,
    FileDigest,
    IntegrityManifest,
    IntegrityResult,
    ManifestEntry,
    ManifestResult,
    build_manifest,
    hash_file,
    parse_manifest_document,
    verify_manifest,
)
from .checkpoint import (  # noqa: F401
    CHECKPOINT_NAME,
    CheckpointDecision,
    CheckpointJournal,
)
from .restore import (  # noqa: F401
    DENIED_ROOT_SEGMENTS,
    RollbackCheckpointView,
    evaluate_restore,
    rollback_gate,
    valid_restore_root,
)

__all__ = [
    "ALLOW_STAGED", "BACKUP_SCOPE", "BLOCKED", "DEPLOYMENT_CHANGED", "FAILED",
    "GUEST_NOT_RUN", "INTEGRITY_FAILED", "MAX_DOC_BYTES", "MAX_LABEL_BYTES",
    "MAX_PATH_BYTES", "MAX_REASONS", "MAX_SOURCES", "NOT_RUN", "OK",
    "OWNER_DATA_CONFLICT", "PLANNING", "PROVENANCE_MISMATCH", "REFUSE",
    "ROLLBACK", "ROLLBACK_IN_FLIGHT", "SCHEMA", "SEALED",
    "TARGET_NOT_CONTAINED", "TOOL_NAME", "TOOL_VERSION", "BackupPlan",
    "BackupRecoveryError", "CheckpointRecord", "ProvenanceRecord",
    "RestoreDecision", "SourceSpec", "build_plan", "canonical_bytes",
    "contained", "digest_bytes", "parse_bounded_document",
    "parse_checkpoint_document", "parse_plan_document",
    "parse_provenance_document", "safe_path", "valid_label",
    "valid_logical_path", "MAX_FILE_BYTES", "FileDigest", "IntegrityManifest",
    "IntegrityResult", "ManifestEntry", "ManifestResult", "build_manifest",
    "hash_file", "parse_manifest_document", "verify_manifest", "CHECKPOINT_NAME",
    "CheckpointDecision", "CheckpointJournal", "DENIED_ROOT_SEGMENTS",
    "RollbackCheckpointView", "evaluate_restore", "rollback_gate",
    "valid_restore_root",
]
