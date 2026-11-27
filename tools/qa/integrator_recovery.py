#!/usr/bin/env python3
"""Bounded, safe restart helper for the Canopy integrator daemon.

This module is intentionally small and dependency-free. It NEVER kills a live
process and NEVER clears a lock owned by a live process (even when that
process's heartbeat is stale). It only clears a lock whose owner is dead or
whose PID was reused, then starts a detached replacement with bounded attempts.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import subprocess
import sys
import warnings
from typing import Any

from tools.qa.integrator_lock import (  # type: ignore[import-not-found]
    RECOVERY_COOLDOWN_SECONDS, LockState, clear_stale_lock, lock_state,
    process_alive,
)

_PRIVATE_SCRATCH = pathlib.Path(
    os.environ.get("CANOPY_PRIVATE_SCRATCH", "private-evidence/scratch"))
DEFAULT_LOCK = _PRIVATE_SCRATCH / "canopy_integrator.lock"
DEFAULT_DAEMON = _PRIVATE_SCRATCH / "canopy_integrator.py"
DEFAULT_LOG = _PRIVATE_SCRATCH / "canopy_integrator_restart.log"
MAX_ATTEMPTS_PER_WINDOW = 2


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso() -> str:
    return _now().isoformat()


def _parse(value: object) -> datetime.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def recovery_state_path(lock: pathlib.Path) -> pathlib.Path:
    return lock.with_name(lock.name + ".recovery.json")


def _within_cooldown(state: dict[str, Any]) -> bool:
    stamp = _parse(state.get("last_attempt"))
    if stamp is None:
        return False
    return (_now() - stamp).total_seconds() < RECOVERY_COOLDOWN_SECONDS


def _launch_detached(daemon: pathlib.Path, log: pathlib.Path) -> int:
    flags = 0
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kwargs["start_new_session"] = True
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        with log.open("ab") as handle:
            proc = subprocess.Popen(
                [sys.executable, str(daemon)],
                stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT,
                creationflags=flags, close_fds=True, cwd=str(daemon.parent), **kwargs)
        pid = proc.pid
        del proc  # intentionally detached; never wait for a long-lived daemon
    return pid


def recover(lock: pathlib.Path = DEFAULT_LOCK,
            daemon: pathlib.Path = DEFAULT_DAEMON,
            log: pathlib.Path = DEFAULT_LOG,
            *, stale_seconds: int = 180,
            launch: bool = True) -> dict[str, Any]:
    """Return a bounded recovery decision; start a daemon only when safe."""
    state_path = recovery_state_path(lock)
    state = _read_json(state_path)
    observed: LockState = lock_state(lock, stale_seconds)
    result: dict[str, Any] = {
        "lock_status": observed.status,
        "reason": observed.reason,
        "action": "none",
        "pid": (observed.info or {}).get("pid"),
    }
    if observed.status == "absent":
        result["action"] = "none"
        result["reason"] = "no_stale_lock"
        return result
    # A live owner (even with a stale heartbeat) is never touched.
    if observed.status == "live":
        result["action"] = "keep"
        return result
    if observed.status == "stale" and process_alive(
            (observed.info or {}).get("pid"), (observed.info or {}).get("start")):
        result["action"] = "alert_only"
        result["reason"] = "heartbeat_stale_but_process_alive"
        return result
    if _within_cooldown(state):
        result["action"] = "recovery_limit"
        result["reason"] = "cooldown"
        return result
    count = int(state.get("attempts_in_window", 0) or 0)
    if count >= MAX_ATTEMPTS_PER_WINDOW:
        result["action"] = "recovery_limit"
        result["reason"] = "max_attempts"
        return result
    cleared, clear_reason = clear_stale_lock(lock, stale_seconds)
    if not cleared:
        result["action"] = "alert_only"
        result["reason"] = clear_reason
        return result
    result["lock_cleared"] = True
    result["clear_reason"] = clear_reason
    state_path.write_text(json.dumps({
        "last_attempt": _iso(),
        "attempts_in_window": count + 1,
        "last_reason": clear_reason,
    }, sort_keys=True), encoding="utf-8")
    if not launch:
        result["action"] = "would_restart"
        return result
    try:
        pid = _launch_detached(daemon, log)
    except OSError as exc:
        result["action"] = "restart_failed"
        result["error"] = repr(exc)[:300]
    else:
        result["action"] = "restarted"
        result["new_pid"] = pid
    return result


if __name__ == "__main__":
    print(json.dumps(recover(), sort_keys=True))
