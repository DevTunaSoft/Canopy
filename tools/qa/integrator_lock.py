#!/usr/bin/env python3
"""Atomic, stale-safe process lock for long-running Canopy tools.

The lock file is JSON containing the owning PID, the OS process start time
(PID-reuse guard), a UUID token (release/touch ownership guard), an ISO-8601
heartbeat timestamp and the owner name. Legacy plain-integer locks are kept
live while their PID is alive (safe migration) and recoverable only after that
PID dies.

 acquire() uses O_CREAT|O_EXCL, so two contenders cannot both win.
 release() and touch() verify the UUID token before touching the file.
 A live-but-silent process is never killed or unlocked by this module; it is
reported as a distinct state so a supervisor can alert instead of forking a
second integrator.
"""
from __future__ import annotations

import ctypes
import datetime
import json
import os
import platform
import pathlib
import time
import uuid
from dataclasses import dataclass
from typing import Any

STALE_SECONDS = 180
RECOVERY_COOLDOWN_SECONDS = 900
MAX_ACQUIRE_ATTEMPTS = 3


class LockHeld(RuntimeError):
    """Another live process owns the lock."""


@dataclass(frozen=True)
class LockState:
    status: str  # absent | live | stale
    info: dict[str, Any] | None
    reason: str


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(moment: datetime.datetime | None = None) -> str:
    return (moment or _now()).isoformat()


def _parse_iso(value: object) -> datetime.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong),
                ("dwHighDateTime", ctypes.c_ulong)]


def process_start_time(pid: int) -> float | None:
    """Return process creation time as Unix seconds, or None if unavailable."""
    if pid <= 0:
        return None
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFO
            if not handle:
                return None
            creation = _FILETIME()
            dummy = (_FILETIME(), _FILETIME(), _FILETIME())
            ok = kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(dummy[0]),
                ctypes.byref(dummy[1]), ctypes.byref(dummy[2]))
            kernel32.CloseHandle(handle)
            if not ok:
                return None
            raw = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return raw / 10_000_000.0 - 11_644_473_600.0
        except Exception:
            return None
    try:
        return os.stat("/proc/%d" % pid).st_ctime
    except OSError:
        return None


def process_alive(pid: object, start: object = None) -> bool:
    """Return True only for a live process whose start time still matches."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            alive = bool(ok) and code.value == 259  # STILL_ACTIVE
        except Exception:
            alive = False
    else:
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            alive = False
    if not alive:
        return False
    if isinstance(start, (int, float)):
        current = process_start_time(pid)
        if current is None or abs(current - float(start)) > 2.0:
            return False
    return True


def read_lock(path: str | pathlib.Path) -> dict[str, Any] | None:
    """Read a JSON or legacy integer lock; never raise on corrupt content."""
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return {"malformed": True, "reason": "unreadable"}
    if not text:
        # O_CREAT|O_EXCL creates the file before its JSON is written. A fresh
        # empty file means "writer still starting", not a corrupt stale lock.
        return {"pending": True}
    if text.isdigit():
        return {"pid": int(text), "legacy": True}
    try:
        data = json.loads(text)
    except ValueError:
        return {"malformed": True, "reason": "not json"}
    return data if isinstance(data, dict) else {"malformed": True, "reason": "not object"}


def lock_state(path: str | pathlib.Path,
               stale_seconds: int = STALE_SECONDS) -> LockState:
    """Classify a lock without modifying it."""
    info = read_lock(path)
    if info is None:
        return LockState("absent", None, "missing")
    if info.get("pending"):
        try:
            mtime = datetime.datetime.fromtimestamp(
                pathlib.Path(path).stat().st_mtime, datetime.timezone.utc)
        except OSError:
            return LockState("stale", info, "pending_unreadable")
        if (_now() - mtime).total_seconds() <= stale_seconds:
            return LockState("live", info, "lock_being_written")
        return LockState("stale", info, "pending_writer_dead")
    if info.get("legacy"):
        if process_alive(info.get("pid")):
            return LockState("live", info, "legacy_live_owner")
        return LockState("stale", info, "legacy_dead_owner")
    if info.get("malformed"):
        return LockState("stale", info, info.get("reason", "malformed"))
    if not process_alive(info.get("pid"), info.get("start")):
        return LockState("stale", info, "owner_dead_or_pid_reused")
    stamp = _parse_iso(info.get("ts"))
    if stamp is None:
        return LockState("stale", info, "heartbeat_unreadable")
    age = (_now() - stamp).total_seconds()
    if age > stale_seconds:
        return LockState("stale", info, "heartbeat_stale_but_process_alive")
    return LockState("live", info, "live")


def clear_stale_lock(path: str | pathlib.Path,
                     stale_seconds: int = STALE_SECONDS) -> tuple[bool, str]:
    """Remove a lock only when its owner is definitely gone.

    A live process with a stale heartbeat is deliberately NOT unlocked; the
    caller must alert instead of starting a competing integrator.
    """
    state = lock_state(path, stale_seconds)
    if state.status == "absent":
        return True, "absent"
    if state.status == "live":
        return False, "live"
    info = state.info or {}
    if info.get("legacy") or info.get("malformed"):
        pathlib.Path(path).unlink(missing_ok=True)
        return True, "cleared_" + state.reason
    if process_alive(info.get("pid"), info.get("start")):
        return False, state.reason
    pathlib.Path(path).unlink(missing_ok=True)
    return True, "cleared_" + state.reason


class LockHandle:
    """Owned lock handle. Use as a context manager when possible."""

    def __init__(self, path: str | pathlib.Path, token: str, info: dict[str, Any]):
        self.path = pathlib.Path(path)
        self.token = token
        self.info = info

    def _matches(self) -> bool:
        current = read_lock(self.path)
        return bool(current and current.get("token") == self.token)

    def touch(self) -> None:
        """Refresh heartbeat atomically, only if this handle still owns it."""
        current = read_lock(self.path)
        if not current or current.get("token") != self.token:
            raise LockHeld("lock token changed")
        updated = dict(current)
        updated["ts"] = _iso()
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(updated, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)

    def release(self) -> None:
        """Delete the lock only if this handle still owns it."""
        if self._matches():
            self.path.unlink(missing_ok=True)

    def __enter__(self) -> "LockHandle":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def acquire(path: str | pathlib.Path, *, owner: str = "integrator",
            stale_seconds: int = STALE_SECONDS,
            attempts: int = MAX_ACQUIRE_ATTEMPTS) -> LockHandle:
    """Acquire the lock atomically, recovering only definitely stale locks."""
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Always allow one retry after clearing a stale lock, even when the caller
    # asked for a single attempt; the clear itself is not an acquisition try.
    for attempt in range(1, max(2, attempts) + 1):
        token = uuid.uuid4().hex
        info = {
            "owner": owner,
            "pid": os.getpid(),
            "start": process_start_time(os.getpid()),
            "token": token,
            "ts": _iso(),
            "host": os.environ.get("COMPUTERNAME") or platform.node(),
        }
        try:
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            state = lock_state(target, stale_seconds)
            if state.status == "live":
                raise LockHeld("live lock: pid %s" % (state.info or {}).get("pid"))
            if state.status == "stale" and "heartbeat_stale_but_process_alive" in state.reason:
                raise LockHeld(state.reason)
            cleared, reason = clear_stale_lock(target, stale_seconds)
            if not cleared:
                raise LockHeld(reason)
            continue
        try:
            os.write(fd, json.dumps(info, sort_keys=True).encode("utf-8"))
        finally:
            os.close(fd)
        return LockHandle(target, token, info)
    raise LockHeld("could not acquire after %d attempts" % attempts)
