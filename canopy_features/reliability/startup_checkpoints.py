"""Offline model of ordered startup steps with crash-safe rollback decisions.

This is a small, pure-Python, single-process modelling component. It does NOT
launch Qt, touch a compositor, start a service, poll, or prove a working
desktop. A host must wire it into the compiled Classic application separately.

Durability contract:
- Each transition appends one canonical JSON line to a journal.
- Publishing uses a temp file in the same directory, flush + fsync, then
  os.replace and a best-effort directory fsync. A crash before publish leaves
  only a stale temp file, which recovery ignores and removes.
- A "begin" record is a write-ahead intent. Only a "commit" record proves a
  step completed. Recovery never promotes an intent into a committed step.
- Every record chains to the previous record SHA-256. A torn, reordered,
  unknown or tampered record rejects the whole journal and fails closed to a
  cold start.

State bytes are hashed, never stored. Bounded record, journal, step and state
limits keep memory and disk use finite. No secrets are written to the journal
or included in error messages.
"""

import hashlib
import json
import os
from pathlib import Path
import re
from dataclasses import dataclass
from typing import Optional, Tuple


FORMAT_VERSION = 1
MAX_STEPS = 64
MAX_STATE_BYTES = 4096
MAX_RECORD_BYTES = 1024
MAX_JOURNAL_BYTES = 131_072
TEMP_SUFFIX = ".tmp"
ZERO_HASH = "0" * 64

# Modelled order of the real Classic Qt startup path in prototype/classic/main.cpp:
# parse QCoreApplication arguments, verify exact artwork, construct the QQml
# engine, load Main.qml, then emit CANOPY_CLASSIC_WINDOW_READY. This is a model
# only; nothing here calls Qt or observes a real session.
CLASSIC_STARTUP_STEPS = (
    "parse_args", "verify_artwork", "create_engine", "load_qml", "window_ready",
)

_STEP_NAME = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")
_HEX256 = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "version", "sequence", "step_index", "phase", "state_sha256", "prev_sha256",
})
_ALL_KEYS = _FIELDS | {"sha256"}
_PHASES = frozenset({"begin", "commit"})


class CheckpointError(ValueError):
    """Invalid step, state, journal or rollback target. No write is performed."""


@dataclass(frozen=True)
class RollbackDecision:
    """What a restarted host may safely treat as completed startup state.

    ``target`` is the last step allowed to stand, or None for a cold start.
    ``completed`` is the validated committed prefix. ``discarded`` lists steps
    that were only began, or that were found in an untrusted journal.
    """

    target: Optional[str]
    completed: Tuple[str, ...]
    discarded: Tuple[str, ...]
    reason: str

    @property
    def safe(self) -> bool:
        """True only if the target is a validated committed step or cold start."""
        return self.target is None or self.target in self.completed


def _canonical(obj: dict) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate journal field")
        result[key] = value
    return result


def _fsync_parent(path: Path) -> None:
    """Best effort: directory fsync is unavailable on Windows."""
    try:
        descriptor = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


class StartupCheckpoints:
    """Durable startup-step journal with fail-closed rollback decisions.

    Callers supply the ordered step allowlist. Single writer, single process:
    concurrent writers are not supported and need an external lock.
    """

    def __init__(self, path, steps=CLASSIC_STARTUP_STEPS):
        self._path = Path(path)
        if (type(steps) not in (tuple, list) or not steps
                or len(steps) > MAX_STEPS):
            raise CheckpointError("invalid startup step count")
        if any(type(step) is not str or not _STEP_NAME.fullmatch(step)
               for step in steps):
            raise CheckpointError("invalid startup step name")
        if len(set(steps)) != len(steps):
            raise CheckpointError("duplicate startup step name")
        if self._path.is_dir():
            raise CheckpointError("journal path must name a file")
        if not self._path.parent.is_dir():
            raise CheckpointError("journal parent directory must exist")
        self._steps = tuple(steps)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def temp_path(self) -> Path:
        return self._path.with_name(self._path.name + TEMP_SUFFIX)

    @property
    def steps(self) -> Tuple[str, ...]:
        return self._steps

    def _require_step(self, step) -> int:
        if type(step) is not str or step not in self._steps:
            raise CheckpointError("unknown startup step")
        return self._steps.index(step)

    @staticmethod
    def _record(sequence, step_index, phase, state_hash, previous) -> dict:
        fields = {
            "version": FORMAT_VERSION,
            "sequence": sequence,
            "step_index": step_index,
            "phase": phase,
            "state_sha256": state_hash,
            "prev_sha256": previous,
        }
        fields["sha256"] = hashlib.sha256(_canonical(fields)).hexdigest()
        return fields

    @staticmethod
    def _dump(records) -> bytes:
        return b"".join(_canonical(record) + b"\n" for record in records)

    def _publish(self, data: bytes) -> None:
        temp = self.temp_path
        descriptor = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self._path)
        _fsync_parent(self._path)

    def _scan(self):
        """Return (records, completed, pending, ok). Never trusts a stale temp."""
        invalid = ((), (), None, False)
        temp = self.temp_path
        if temp.exists() or temp.is_symlink():
            try:
                temp.unlink()
            except OSError:
                return invalid
        if self._path.is_symlink():
            return invalid
        try:
            data = self._path.read_bytes()
        except FileNotFoundError:
            return ((), (), None, True)
        except OSError:
            return invalid
        if not data:
            return ((), (), None, True)
        if len(data) > MAX_JOURNAL_BYTES:
            return invalid

        records = []
        completed = []
        pending = None
        expected_sequence = 1
        previous = ZERO_HASH
        for raw in data.splitlines():
            if not raw or len(raw) > MAX_RECORD_BYTES:
                return invalid
            try:
                record = json.loads(
                    raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys,
                )
            except (UnicodeError, ValueError):
                return invalid
            if type(record) is not dict or set(record) != _ALL_KEYS:
                return invalid
            if (type(record["version"]) is not int
                    or record["version"] != FORMAT_VERSION
                    or type(record["sequence"]) is not int
                    or record["sequence"] != expected_sequence
                    or type(record["step_index"]) is not int
                    or not 0 <= record["step_index"] < len(self._steps)
                    or record["phase"] not in _PHASES):
                return invalid
            for key in ("state_sha256", "prev_sha256", "sha256"):
                if (type(record[key]) is not str
                        or not _HEX256.fullmatch(record[key])):
                    return invalid
            if record["prev_sha256"] != previous:
                return invalid
            fields = {key: record[key] for key in _FIELDS}
            if hashlib.sha256(_canonical(fields)).hexdigest() != record["sha256"]:
                return invalid

            index = record["step_index"]
            if record["phase"] == "begin":
                if pending is not None or index != len(completed):
                    return invalid
                pending = index
            else:
                if pending != index:
                    return invalid
                pending = None
                completed.append(self._steps[index])
            previous = record["sha256"]
            expected_sequence += 1
            records.append(record)

        pending_step = self._steps[pending] if pending is not None else None
        return (tuple(records), tuple(completed), pending_step, True)

    def decide(self) -> RollbackDecision:
        """Read only: choose the last state safe to stand after a restart."""
        records, completed, pending, ok = self._scan()
        if not ok:
            return RollbackDecision(None, (), (), "CORRUPT_JOURNAL")
        if pending is not None:
            discarded = (pending,)
            target = completed[-1] if completed else None
            reason = "PARTIAL_STATE"
        elif completed:
            discarded = ()
            target = completed[-1]
            reason = "CLEAN"
        else:
            discarded = ()
            target = None
            reason = "NO_JOURNAL"
        return RollbackDecision(target, completed, discarded, reason)

    def begin(self, step) -> None:
        """Durably record intent before running a step. No state is applied."""
        index = self._require_step(step)
        records, completed, pending, ok = self._scan()
        if not ok:
            raise CheckpointError("journal is corrupt; recover before new steps")
        if pending is not None:
            raise CheckpointError("a startup step is already in progress")
        if index != len(completed):
            raise CheckpointError("startup step is out of order")
        previous = records[-1]["sha256"] if records else ZERO_HASH
        record = self._record(len(records) + 1, index, "begin", ZERO_HASH, previous)
        self._publish(self._dump(records) + _canonical(record) + b"\n")

    def commit(self, step, state: bytes) -> None:
        """Durably prove a began step completed, storing only its state digest."""
        index = self._require_step(step)
        if type(state) is not bytes or len(state) > MAX_STATE_BYTES:
            raise CheckpointError("state must be bytes within the size bound")
        records, completed, pending, ok = self._scan()
        if not ok:
            raise CheckpointError("journal is corrupt; recover before new steps")
        if pending != step or index != len(completed):
            raise CheckpointError("step is not the active in-progress step")
        previous = records[-1]["sha256"]
        state_hash = hashlib.sha256(state).hexdigest()
        record = self._record(
            len(records) + 1, index, "commit", state_hash, previous,
        )
        self._publish(self._dump(records) + _canonical(record) + b"\n")

    def abort(self) -> None:
        """Discard a trailing begin intent; committed records stay untouched."""
        records, completed, pending, ok = self._scan()
        if not ok:
            raise CheckpointError("journal is corrupt; recover before new steps")
        if pending is None:
            return
        self._publish(self._prefix_for_steps(records, len(completed)))

    @staticmethod
    def _prefix_for_steps(records, keep_steps) -> bytes:
        if keep_steps <= 0:
            return b""
        kept = 0
        kept_records = []
        for record in records:
            kept_records.append(record)
            if record["phase"] == "commit":
                kept += 1
                if kept == keep_steps:
                    break
        return StartupCheckpoints._dump(kept_records)

    def rollback_to(self, step: Optional[str] = None) -> RollbackDecision:
        """Atomically keep only committed steps through ``step``.

        ``None`` means a cold start: every record is dropped. A target must be
        in the validated committed prefix; intents and corrupt tails are never
        published. The returned decision is a record of what was kept.
        """
        decision = self.decide()
        if not decision.safe:
            raise CheckpointError("refusing unsafe rollback decision")
        if step is not None and step not in decision.completed:
            raise CheckpointError("rollback target is not a committed step")
        keep_steps = (decision.completed.index(step) + 1 if step is not None
                      else 0)
        records, _completed, _pending, ok = self._scan()
        data = self._prefix_for_steps(records, keep_steps) if ok else b""
        self._publish(data)
        return RollbackDecision(
            target=step,
            completed=decision.completed[:keep_steps],
            discarded=(),
            reason="ROLLED_BACK",
        )
