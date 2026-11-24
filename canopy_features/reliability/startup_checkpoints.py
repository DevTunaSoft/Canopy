"""Durable startup checkpoints with fail-closed rollback decisions.

Small offline model of an ordered startup sequence. The caller supplies a
dedicated state directory and the trusted step names. Each completed step is
published with an atomic, synced write before the caller treats it as live.
After a crash, ``recover()`` derives a rollback decision only from durable,
schema-valid bytes and persists the decision before any unwind begins.

Limits: single owner (no cross-process lock), no threads, no polling, no
process or Qt launch, no session writes, no telemetry. This does not prove a
working desktop; a reviewed host must call it from the real startup path.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA = 1
STATE_NAME = "startup.json"
MAX_STEPS = 64
MAX_NAME_BYTES = 64
MAX_STATE_BYTES = 16 * 1024
NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
IN_PROGRESS = "IN_PROGRESS"
COMPLETE = "COMPLETE"
ROLLBACK = "ROLLBACK"
START_FRESH = "START_FRESH"
READY = "READY"
FAIL_CLOSED = "FAIL_CLOSED"


class CheckpointError(ValueError):
    """Invalid plan, unsafe state path, or a refused state transition."""


@dataclass(frozen=True)
class RecoveryDecision:
    """What a restarted host may do, derived only from durable state."""

    action: str
    completed: Tuple[str, ...]
    unwind: Tuple[str, ...]
    target: Optional[str]
    reason: str

    @property
    def safe_to_start(self) -> bool:
        return self.action in (START_FRESH, READY)

    @property
    def needs_rollback(self) -> bool:
        return bool(self.unwind)


def _fsync_dir(directory: Path) -> None:
    # POSIX needs a parent sync to make the rename durable. Windows cannot
    # open a directory this way; the atomic replace is still the boundary.
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
    fd, temporary = tempfile.mkstemp(
        prefix=".canopy-startup-", suffix=".tmp", dir=str(path.parent))
    staged = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
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


class StartupCheckpoints:
    """Single-owner journal of ordered startup steps in one state directory."""

    def __init__(self, state_dir: str | os.PathLike, steps: Sequence[str]):
        """Accept a str or os.PathLike state directory; other types fail closed."""
        if not isinstance(state_dir, (str, os.PathLike)):
            raise CheckpointError("state directory must be a path")
        try:
            directory = Path(state_dir)
        except (TypeError, ValueError):
            raise CheckpointError("state directory must be a path") from None
        if directory.is_symlink():
            raise CheckpointError("state directory must not be a symlink")
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise CheckpointError("state path is not a directory")
        if (type(steps) not in (list, tuple) or not 1 <= len(steps) <= MAX_STEPS):
            raise CheckpointError("startup plan must hold 1 to 64 steps")
        names: List[str] = []
        for name in steps:
            if (type(name) is not str or len(name.encode("utf-8")) > MAX_NAME_BYTES
                    or not NAME.fullmatch(name)):
                raise CheckpointError("invalid startup step name")
            if name in names:
                raise CheckpointError("duplicate startup step name")
            names.append(name)
        self._directory = directory
        self._path = directory / STATE_NAME
        if self._path.is_symlink():
            raise CheckpointError("state file must not be a symlink")
        self._steps = tuple(names)

    @property
    def steps(self) -> Tuple[str, ...]:
        return self._steps

    @property
    def path(self) -> Path:
        return self._path

    def _new_record(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "steps": list(self._steps),
            "completed": [],
            "status": IN_PROGRESS,
        }

    def _write(self, record: Dict[str, Any]) -> Optional[str]:
        payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(payload) > MAX_STATE_BYTES:
            return "checkpoint exceeds byte bound"
        try:
            _atomic_write(self._path, payload)
        except OSError:
            return "checkpoint could not be written durably"
        return None

    def _read(self) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if self._path.is_symlink():
            return None, "checkpoint path is a symlink"
        try:
            if not self._path.exists():
                return None, "no checkpoint"
            if self._path.stat().st_size > MAX_STATE_BYTES:
                return None, "checkpoint exceeds byte bound"
            raw = self._path.read_bytes()
        except OSError:
            return None, "checkpoint is unreadable"
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            return None, "checkpoint is not valid UTF-8 JSON"
        return record, self._check(record)

    def _check(self, record: Any) -> Optional[str]:
        if type(record) is not dict or set(record) != {
                "schema", "steps", "completed", "status"}:
            return "checkpoint schema mismatch"
        if type(record["schema"]) is not int or record["schema"] != SCHEMA:
            return "unsupported checkpoint version"
        plan, done, status = record["steps"], record["completed"], record["status"]
        if (type(plan) is not list or not 1 <= len(plan) <= MAX_STEPS
                or any(type(name) is not str or not NAME.fullmatch(name) for name in plan)
                or len(set(plan)) != len(plan)):
            return "invalid startup plan in checkpoint"
        if type(done) is not list or any(type(name) is not str for name in done):
            return "invalid completed list in checkpoint"
        if done != plan[:len(done)] or len(done) > len(plan):
            return "completed steps are not a plan prefix"
        if status not in (IN_PROGRESS, COMPLETE, ROLLBACK):
            return "invalid checkpoint status"
        if status == COMPLETE and len(done) != len(plan):
            return "completed checkpoint misses steps"
        # A ROLLBACK journal may legitimately hold a full completed plan: a
        # crash after the last complete() but before finish() must unwind every
        # durable step. Rejecting that state would make recover()'s own
        # persisted decision unreadable, flipping a second recover() to
        # FAIL_CLOSED instead of returning the identical rollback decision.
        return None

    def begin(self) -> None:
        """Publish a fresh plan. Refuses to overwrite any existing state."""
        record, error = self._read()
        if record is not None or error != "no checkpoint":
            raise CheckpointError("existing or unreadable checkpoint; call reset() first")
        failure = self._write(self._new_record())
        if failure:
            raise CheckpointError(failure)

    def reset(self) -> None:
        """Explicitly discard prior state and publish a fresh plan atomically."""
        failure = self._write(self._new_record())
        if failure:
            raise CheckpointError(failure)

    def complete(self, step: str) -> None:
        """Durably mark the next step done before its effects are trusted."""
        record, error = self._read()
        if record is None or error is not None:
            raise CheckpointError("no trusted startup journal: " + str(error))
        if record["status"] != IN_PROGRESS:
            raise CheckpointError("journal is not accepting steps")
        done = record["completed"]
        if len(done) >= len(record["steps"]):
            raise CheckpointError("all steps completed; call finish()")
        if type(step) is not str or step != record["steps"][len(done)]:
            raise CheckpointError("out-of-order or unknown startup step")
        record["completed"] = done + [step]
        failure = self._write(record)
        if failure:
            raise CheckpointError(failure)

    def finish(self) -> None:
        """Mark a complete, durable startup as READY for later boots."""
        record, error = self._read()
        if record is None or error is not None:
            raise CheckpointError("no trusted startup journal: " + str(error))
        if record["status"] != IN_PROGRESS:
            raise CheckpointError("journal is not accepting completion")
        if len(record["completed"]) != len(record["steps"]):
            raise CheckpointError("unfinished steps remain")
        record["status"] = COMPLETE
        failure = self._write(record)
        if failure:
            raise CheckpointError(failure)

    def recover(self) -> RecoveryDecision:
        """Decide and durably record rollback for a crashed startup."""
        record, error = self._read()
        if error == "no checkpoint":
            return RecoveryDecision(START_FRESH, (), (), None, "no durable checkpoint exists")
        if record is None or error is not None:
            return RecoveryDecision(FAIL_CLOSED, (), (), None,
                                    "untrusted checkpoint: " + str(error))
        done = tuple(record["completed"])
        unwind = tuple(reversed(done))
        target = done[-1] if done else None
        if record["status"] == COMPLETE:
            return RecoveryDecision(READY, done, (), None, "all startup steps are durable")
        decision = RecoveryDecision(
            ROLLBACK, done, unwind, target, "partial startup; unwind durable steps")
        if record["status"] == IN_PROGRESS:
            record["status"] = ROLLBACK
            failure = self._write(record)
            if failure:
                return RecoveryDecision(FAIL_CLOSED, done, (), target,
                                        "rollback decision was not durable")
        return decision
