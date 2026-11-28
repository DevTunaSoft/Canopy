"""Durable, bounded checkpoint journal with explicit rollback interaction.

The journal records *claims* (provenance digest, integrity digest, deployment
label) atomically. It never touches a live owner-data path or an immutable
system path. ``recover()`` derives its decision only from durable, schema
valid bytes so a restarted host never trusts an in-memory plan it cannot
prove. A rollback marker always wins over a sealed checkpoint: the host must
finish unwinding the atomic update before a restore may even be considered.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple

from .contract import (
    BLOCKED,
    FAILED,
    MAX_DOC_BYTES,
    OK,
    PLANNING,
    ROLLBACK,
    SEALED,
    BackupPlan,
    BackupRecoveryError,
    CheckpointRecord,
    ProvenanceRecord,
    bound_reasons,
    canonical_bytes,
    parse_bounded_document,
    parse_checkpoint_document,
    safe_path,
)

CHECKPOINT_NAME = "backup_checkpoint.json"

RESUME = "RESUME"
WAIT_ROLLBACK = "WAIT_ROLLBACK"
START_FRESH = "START_FRESH"
INVALID = "INVALID"


@dataclass(frozen=True)
class CheckpointDecision:
    """What a restarted host may do, derived only from durable bytes."""

    action: str
    record: Optional[CheckpointRecord]
    reasons: Tuple[str, ...]

    @property
    def may_restore(self) -> bool:
        return (self.action == RESUME and self.record is not None
                and self.record.sealed and not self.record.rollback_in_flight)


def _fsync_dir(directory: Path) -> None:
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(str(directory), flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, payload: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(
        prefix=".canopy-backup-", suffix=".tmp", dir=str(path.parent))
    staged = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
        _fsync_dir(path.parent)
    finally:
        try:
            staged.unlink()
        except OSError:
            pass


class CheckpointJournal:
    """Single-owner durable journal in one caller-provided state directory."""

    MAX_GENERATION = 1024

    def __init__(self, state_dir: Any):
        directory = safe_path(state_dir)
        if directory is None:
            raise BackupRecoveryError("checkpoint state directory is unsafe")
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BackupRecoveryError("could not create checkpoint directory") from exc
        if not directory.is_dir():
            raise BackupRecoveryError("checkpoint path is not a directory")
        self._directory = directory
        self._path = directory / CHECKPOINT_NAME
        try:
            if self._path.is_symlink():
                raise BackupRecoveryError("checkpoint file must not be a symlink")
        except OSError as exc:
            raise BackupRecoveryError("could not inspect checkpoint file") from exc

    @property
    def path(self) -> Path:
        return self._path

    def _read(self) -> Tuple[Optional[CheckpointRecord], Optional[str]]:
        """Return a durable record and a status, never raw file content."""
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return None, "no checkpoint"
        except OSError:
            return None, "unreadable"
        if len(raw) > MAX_DOC_BYTES:
            return None, "oversize"
        try:
            document = parse_bounded_document(raw)
            record = parse_checkpoint_document(document)
        except BackupRecoveryError as exc:
            raise BackupRecoveryError("durable checkpoint is untrusted") from exc
        if canonical_bytes(record.to_document()) != raw:
            raise BackupRecoveryError("durable checkpoint is not canonical")
        return record, OK

    def _write(self, record: CheckpointRecord) -> None:
        payload = canonical_bytes(record.to_document())
        if len(payload) > MAX_DOC_BYTES:
            raise BackupRecoveryError("checkpoint exceeds byte bound")
        try:
            _atomic_write(self._path, payload)
        except OSError as exc:
            raise BackupRecoveryError("checkpoint could not be written durably") from exc

    def begin(self, plan: BackupPlan, provenance: ProvenanceRecord,
              integrity_digest: str) -> CheckpointRecord:
        """Publish a fresh PLANNING record; refuse to overwrite existing state."""
        if not isinstance(plan, BackupPlan) or not isinstance(
                provenance, ProvenanceRecord):
            raise BackupRecoveryError("plan and provenance must be contract records")
        if (type(integrity_digest) is not str or len(integrity_digest) != 64
                or any(char not in "0123456789abcdef" for char in integrity_digest)):
            raise BackupRecoveryError("invalid integrity digest")
        if provenance.plan_id != plan.plan_id or provenance.deployment_id != plan.deployment_id:
            raise BackupRecoveryError("provenance does not match the plan")
        try:
            self._path.read_bytes()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise BackupRecoveryError("existing checkpoint could not be read") from exc
        else:
            raise BackupRecoveryError("checkpoint already exists; recover or reset first")
        record = CheckpointRecord(
            schema=1, plan_id=plan.plan_id, deployment_id=plan.deployment_id,
            state=PLANNING, generation=0,
            provenance_digest=provenance.digest(),
            integrity_digest=integrity_digest, rollback_deployment=None)
        self._write(record)
        return record

    def seal(self) -> CheckpointRecord:
        """Move a PLANNING record to SEALED without changing any digest."""
        record, status = self._read()
        if record is None or status != OK:
            raise BackupRecoveryError("no trusted checkpoint to seal")
        if record.state != PLANNING:
            raise BackupRecoveryError("only a PLANNING checkpoint can be sealed")
        sealed = CheckpointRecord(
            record.schema, record.plan_id, record.deployment_id, SEALED,
            record.generation, record.provenance_digest, record.integrity_digest,
            record.rollback_deployment)
        self._write(sealed)
        return sealed

    def mark_rollback(self, target_deployment: str) -> CheckpointRecord:
        """Record an in-flight atomic-update rollback; always bumps generation."""
        from .contract import valid_deployment
        if not valid_deployment(target_deployment):
            raise BackupRecoveryError("rollback deployment label is invalid")
        record, status = self._read()
        if record is None or status != OK:
            raise BackupRecoveryError("no trusted checkpoint for rollback")
        if record.state == ROLLBACK:
            raise BackupRecoveryError("rollback is already recorded")
        if record.generation >= self.MAX_GENERATION:
            raise BackupRecoveryError("checkpoint generation is exhausted")
        rolling = CheckpointRecord(
            record.schema, record.plan_id, record.deployment_id, ROLLBACK,
            record.generation + 1, record.provenance_digest,
            record.integrity_digest, target_deployment)
        self._write(rolling)
        return rolling

    def finish_rollback(self, settled_deployment: str) -> CheckpointRecord:
        """Settle a rollback back to SEALED at the deployment now booted."""
        from .contract import valid_deployment
        if not valid_deployment(settled_deployment):
            raise BackupRecoveryError("settled deployment label is invalid")
        record, status = self._read()
        if record is None or status != OK or record.state != ROLLBACK:
            raise BackupRecoveryError("no rollback in flight to finish")
        settled = CheckpointRecord(
            record.schema, record.plan_id, settled_deployment, SEALED,
            record.generation, record.provenance_digest, record.integrity_digest,
            None)
        self._write(settled)
        return settled

    def recover(self) -> CheckpointDecision:
        """Derive a restart decision from durable bytes only."""
        try:
            record, status = self._read()
        except BackupRecoveryError:
            return CheckpointDecision(INVALID, None, bound_reasons(("UNTRUSTED_CHECKPOINT",)))
        if status == "no checkpoint":
            return CheckpointDecision(START_FRESH, None, bound_reasons(("NO_CHECKPOINT",)))
        if record is None:
            return CheckpointDecision(
                INVALID, None, bound_reasons(((status or "UNKNOWN").upper(),)))
        if record.rollback_in_flight:
            return CheckpointDecision(
                WAIT_ROLLBACK, record,
                bound_reasons(("ROLLBACK_IN_FLIGHT", "ATOMIC_UPDATE_SETTLING")))
        if record.state == FAILED:
            return CheckpointDecision(
                BLOCKED, record, bound_reasons(("CHECKPOINT_FAILED",)))
        if record.state == PLANNING:
            return CheckpointDecision(
                INVALID, record, bound_reasons(("UNSEALED_CHECKPOINT",)))
        return CheckpointDecision(RESUME, record, bound_reasons((OK,)))
