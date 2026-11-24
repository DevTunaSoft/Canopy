"""Durable, atomic task state and structured history for the Canopy supervisor."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time

STATE_VERSION = 1
MAX_HISTORY_EVENTS = 2048
ACTIVE_STATUSES = ("assigned", "running", "verifying", "publishing")
TERMINAL_STATUSES = ("awaiting_review", "done", "blocked", "failed", "cancelled")
ORDER = ("queued", "assigned", "running", "verifying", "publishing",
         "interrupted", "awaiting_review", "done", "blocked", "failed", "cancelled")


class LockBusy(RuntimeError):
    """Another supervisor already owns the state directory."""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(path: Path, text: str) -> None:
    """Write a small UTF-8 file atomically, flushing to disk before rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".canopy-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_json(path: Path, default: object):
    """Read JSON, returning default only for a missing file."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"corrupt state file: {path.name}") from exc


@contextmanager
def exclusive_lock(path: Path):
    """Process-wide exclusive lock released automatically on crash or exit."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "r+b" if path.exists() else "w+b"
    with path.open(mode) as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise LockBusy("another Canopy supervisor already holds the lock") from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise LockBusy("another Canopy supervisor already holds the lock") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class TaskStore:
    """Single owner of queue state, event history and dashboard output."""

    def __init__(self, state_root: Path):
        self.root = Path(state_root)
        self.tasks_path = self.root / "tasks.json"
        self.history_path = self.root / "history.jsonl"
        self.dashboard_path = self.root / "dashboard.md"
        self.config_path = self.root / "config.json"
        self.pause_path = self.root / "PAUSED"
        self.stop_path = self.root / "STOP"
        self.lock_path = self.root / "locks" / "supervisor.lock"
        for directory in ("logs", "evidence", "worktrees", "worker-data", "locks"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        data = read_json(self.tasks_path, None)
        if data is None:
            return {"version": STATE_VERSION, "updated_at": utcnow(), "tasks": []}
        if not isinstance(data, dict) or data.get("version") != STATE_VERSION or \
                not isinstance(data.get("tasks"), list):
            raise ValueError("unsupported or corrupt tasks.json; refusing to modify it")
        return data

    def save(self, data: dict) -> None:
        if data.get("version") != STATE_VERSION or not isinstance(data.get("tasks"), list):
            raise ValueError("invalid task state")
        data["updated_at"] = utcnow()
        atomic_write(self.tasks_path, json.dumps(data, indent=2, sort_keys=True) + "\n")

    @property
    def paused(self) -> bool:
        return self.pause_path.exists()

    def set_paused(self, paused: bool) -> None:
        if paused:
            atomic_write(self.pause_path, utcnow() + "\n")
        else:
            self.pause_path.unlink(missing_ok=True)

    def event(self, task_id: str, event: str, message: str = "", *, level: str = "INFO",
              worker: str | None = None, data: object = None) -> None:
        row = {
            "ts": utcnow(), "epoch": time.time(), "task_id": task_id, "event": event,
            "level": level, "message": str(message)[:500], "worker": worker,
        }
        if data is not None:
            row["data"] = data
        with self.history_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._trim_history()

    def _trim_history(self) -> None:
        """Keep the durable event journal bounded to the newest events."""
        lines = self.history_path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= MAX_HISTORY_EVENTS:
            return
        atomic_write(self.history_path, "\n".join(lines[-MAX_HISTORY_EVENTS:]) + "\n")

    def recent_events(self, limit: int = 12) -> list[dict]:
        if not self.history_path.exists():
            return []
        rows = []
        for line in self.history_path.read_text(encoding="utf-8").splitlines()[-limit * 4:]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return list(reversed(rows))[:limit]

    def dashboard(self, data: dict, config: dict) -> str:
        tasks = data.get("tasks", [])
        by_status: dict[str, list[dict]] = {}
        for task in tasks:
            by_status.setdefault(task.get("status", "unknown"), []).append(task)
        counts = " ".join(f"{status}={len(by_status.get(status, []))}"
                          for status in ORDER if by_status.get(status)) or "empty"
        lines = [
            "# Canopy supervisor status", "",
            f"Updated UTC: {data.get('updated_at', 'unknown')}",
            f"State: {'PAUSED (no new dispatch)' if self.paused else 'RUNNING'}",
            f"Model: {config.get('model', 'unset')}  |  Workers: "
            f"{config.get('max_workers', 0)}  |  Repo: {config.get('repo', 'unset')}",
            "", f"## Queue: {counts}", "",
            "| Task | Status | Worker | Branch | Attempt | PR |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        roadmap_path = self.root / "roadmap.json"
        if roadmap_path.is_file():
            try:
                catalog = json.loads(roadmap_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                catalog = None
            if isinstance(catalog, list):
                registered = {str(item.get("id")) for item in tasks}
                pending = sum(1 for item in catalog
                              if isinstance(item, dict)
                              and item.get("id") not in registered)
                lines.insert(6,
                    f"Roadmap: {len(catalog)} planned | {pending} not yet dispatched | "
                    f"{len(tasks)} recorded | {len([t for t in tasks if t.get('status') == 'running'])} active workers")
            else:
                lines.insert(6, "Roadmap: INVALID (no silent replacement)")
        for task in sorted(tasks, key=lambda item: str(item.get("id"))):
            pr = task.get("pr") or {}
            lines.append(
                f"| {task.get('id', '?')} | {task.get('status', '?')} "
                f"| {task.get('owner') or '-'} | {task.get('branch') or '-'} "
                f"| {task.get('attempts', 0)}/{task.get('max_attempts', 0)} "
                f"| {pr.get('number') or '-'} |"
            )
        active = [t for t in tasks if t.get("status") in ACTIVE_STATUSES]
        lines += ["", "## Active workers", ""]
        if not active:
            lines.append("- none")
        for task in active:
            lines.append(f"- {task.get('owner') or 'unassigned'}: {task['id']} "
                         f"@ {task['checkpoint'].get('stage', '?')}")
        published = [t for t in tasks if (t.get("pr") or {}).get("number")]
        lines += ["", "## Completed tasks and PRs", ""]
        if not published:
            lines.append("- none")
        for task in published:
            lines.append(f"- {task['id']}: PR #{task['pr']['number']} "
                         f"({task['status']}, draft)")
        lines += ["", "## Next actions", ""]
        queued = [t for t in tasks if t.get("status") == "queued"]
        lines.append(f"- dispatch {len(queued)} queued task(s); roadmap refills "
                     f"empty worker slots automatically")
        lines.append(f"- {len(published)} draft PR(s) await human review; no merge is automated")
        lines += ["", "## Active checkpoints", ""]
        if not active:
            lines.append("- none")
        for task in active:
            checkpoint = task.get("checkpoint") or {}
            lines.append(
                f"- {task['id']}: {checkpoint.get('stage', '?')} "
                f"@ {checkpoint.get('at', '?')} "
                f"heartbeat {task.get('heartbeat_at', '?')}"
            )
        lines += ["", "## Blockers", ""]
        blocked = [t for t in tasks if t.get("status") in ("blocked", "failed", "interrupted")]
        if not blocked:
            lines.append("- none")
        for task in blocked:
            lines.append(f"- {task['id']}: {str(task.get('last_error'))[:160]}")
        lines += ["", "## Recent events", ""]
        for row in self.recent_events():
            who = f" [{row['worker']}]" if row.get("worker") else ""
            lines.append(f"- {row['ts']} `{row['event']}` {row['task_id']}{who}: {row['message']}")
        lines += [
            "",
            "Green CI or a draft PR is not merge authorization. No merge is automated.",
            "",
        ]
        return "\n".join(lines)

    def write_dashboard(self, data: dict, config: dict) -> None:
        atomic_write(self.dashboard_path, self.dashboard(data, config))


def new_task(definition: dict, max_attempts: int) -> dict:
    """Create a persisted task with no owner and a fresh checkpoint."""
    now = utcnow()
    return {
        **definition,
        "status": "queued",
        "owner": None,
        "worktree": None,
        "pid": None,
        "attempts": 0,
        "max_attempts": max_attempts,
        "next_attempt_at": 0.0,
        "lease_expires_at": 0.0,
        "heartbeat_at": now,
        "created_at": now,
        "updated_at": now,
        "last_error": "",
        "checkpoint": {"stage": "created", "at": now, "sha": ""},
        "evidence": {},
        "pr": {},
    }


def advance(task: dict, status: str, stage: str, message: str = "", **fields) -> None:
    """Move one task forward and record a recovery checkpoint."""
    task["status"] = status
    task["updated_at"] = utcnow()
    task["checkpoint"] = {"stage": stage, "at": task["updated_at"], "sha": fields.get("sha", "")}
    if message:
        task["last_error"] = message[:500]
    for key, value in fields.items():
        if key != "sha":
            task[key] = value
