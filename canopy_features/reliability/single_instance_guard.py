"""Offline single-instance lock and takeover policy for shell-owned processes.

This is a one-shot decision helper, not a daemon:

- No background thread, service, idle loop or polling loop.
- No privileged operation. The liveness probe only asks whether a PID exists.
- Bounded state: one small lock file plus one small guard file on disk.
- Platform-neutral core. Tests inject a deterministic PID liveness probe; the
  default probe uses ``os.kill(pid, 0)`` on POSIX and a Win32 handle query on
  Windows.

Limits (kept explicit so nobody mistakes this for a desktop proof):

- Advisory. A shell must call :meth:`SingleInstanceGuard.acquire` at startup
  and :meth:`SingleInstanceGuard.release` at exit. Nothing here stops a second
  process by itself.
- PID-only identity. A recycled PID of a *dead* owner is treated as stale only
  when the recorded PID is no longer alive. A recycled PID that is alive is
  conservatively reported as a competing instance, so the guard never silently
  kills or replaces a live process.
- This module is not wired into the compiled Qt application. Integration and
  any Linux Mint runtime evidence remain future work.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterator, Optional, Tuple

__all__ = [
    "LockDecision",
    "LockRecord",
    "SingleInstanceGuard",
    "TakeoverPolicy",
    "pid_is_alive",
]

LOCK_VERSION = 1
MAX_LOCK_BYTES = 4096

ACQUIRED = "ACQUIRED"
STALE_TAKEN_OVER = "STALE_TAKEN_OVER"
LIVE_TAKEN_OVER = "LIVE_TAKEN_OVER"
ALREADY_OWNED = "ALREADY_OWNED"
COMPETING_INSTANCE = "COMPETING_INSTANCE"
STALE_LOCK_BLOCKED = "STALE_LOCK_BLOCKED"
INVALID_LOCK = "INVALID_LOCK"

_ABSENT = "ABSENT"
_VALID = "VALID"
_INVALID = "INVALID"

_GRANTED = frozenset((ACQUIRED, STALE_TAKEN_OVER, LIVE_TAKEN_OVER,
                      ALREADY_OWNED))


class TakeoverPolicy(Enum):
    """How an existing lock is treated when this process wants ownership."""

    NEVER = "never"
    STALE_ONLY = "stale_only"
    ALWAYS = "always"


@dataclass(frozen=True)
class LockRecord:
    """Validated contents of a lock file."""

    pid: int
    owner: str

    def to_text(self) -> str:
        payload = {
            "version": LOCK_VERSION,
            "pid": self.pid,
            "owner": self.owner,
        }
        return json.dumps(payload, sort_keys=True) + "\n"

    @classmethod
    def parse(cls, text: str) -> "LockRecord":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("lock record must be an object")
        if data.get("version") != LOCK_VERSION:
            raise ValueError("unsupported lock version")
        pid = data.get("pid")
        owner = data.get("owner")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise ValueError("lock pid must be a positive integer")
        if not isinstance(owner, str) or not owner:
            raise ValueError("lock owner must be a non-empty string")
        return cls(pid=pid, owner=owner)


@dataclass(frozen=True)
class LockDecision:
    """Result of one acquire attempt. No exception detail is stored."""

    status: str
    pid: int
    previous_pid: Optional[int] = None
    reason: str = ""

    @property
    def granted(self) -> bool:
        return self.status in _GRANTED


def pid_is_alive(pid: int) -> bool:
    """Default liveness probe: True only if a process with this PID exists.

    A caller injects its own probe in tests. On POSIX, ``PermissionError``
    means the process exists but is not signalable, so it counts as alive.
    """
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
        except ImportError:  # pragma: no cover - Windows always has ctypes
            return False
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            return True
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_fd(fd: int) -> None:
    """Take an exclusive advisory lock, blocking only in the kernel."""
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        # msvcrt does not block indefinitely; a bounded startup retry is not
        # an idle polling loop. No sleep-and-check runs after acquisition.
        for _ in range(50):
            try:
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                return
            except OSError:
                continue
        raise TimeoutError("single-instance guard file stayed locked")
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock_fd(fd: int) -> None:
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_UN)


class SingleInstanceGuard:
    """Claim, inspect and release one named lock file.

    :param lock_path: path to a small, user-owned lock file.
    :param probe: callable ``(pid) -> bool``; defaults to :func:`pid_is_alive`.
    """

    def __init__(self, lock_path: os.PathLike | str,
                 probe: Optional[Callable[[int], bool]] = None) -> None:
        self.lock_path = os.fspath(lock_path)
        self._probe = pid_is_alive if probe is None else probe
        if not callable(self._probe):
            raise TypeError("probe must be callable")

    @contextmanager
    def _guarded(self) -> Iterator[None]:
        guard_path = self.lock_path + ".guard"
        fd = os.open(guard_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _lock_fd(fd)
            try:
                yield
            finally:
                _unlock_fd(fd)
        finally:
            os.close(fd)

    def read(self) -> Tuple[str, Optional[LockRecord]]:
        """Return ``(state, record)`` where state is ABSENT, VALID or INVALID."""
        try:
            with open(self.lock_path, "rb") as handle:
                data = handle.read(MAX_LOCK_BYTES + 1)
        except FileNotFoundError:
            return _ABSENT, None
        except OSError:
            return _INVALID, None
        if len(data) > MAX_LOCK_BYTES:
            return _INVALID, None
        try:
            return _VALID, LockRecord.parse(data.decode("utf-8"))
        except (UnicodeError, ValueError, TypeError):
            return _INVALID, None

    def _write(self, record: LockRecord) -> None:
        directory = os.path.dirname(os.path.abspath(self.lock_path))
        fd, temporary = tempfile.mkstemp(prefix=".canopy-lock-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(record.to_text())
            os.replace(temporary, self.lock_path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    @staticmethod
    def _normalise_pid(pid: Optional[int]) -> int:
        if pid is None:
            return os.getpid()
        if isinstance(pid, bool) or not isinstance(pid, int):
            raise TypeError("pid must be an integer")
        if pid <= 0:
            raise ValueError("pid must be positive")
        return pid

    def acquire(self, pid: Optional[int] = None, owner: str = "canopy-shell",
                policy: TakeoverPolicy = TakeoverPolicy.STALE_ONLY) -> LockDecision:
        """Decide whether this process may own the lock.

        Only ``STALE_ONLY`` is the safe default: a dead owner's lock is
        reclaimed, a live owner is never replaced. ``ALWAYS`` is an explicit,
        dangerous opt-in for a live takeover. ``NEVER`` assumes nothing.
        """
        if not isinstance(policy, TakeoverPolicy):
            raise TypeError("policy must be a TakeoverPolicy")
        if not isinstance(owner, str) or not owner:
            raise ValueError("owner must be a non-empty string")
        own_pid = self._normalise_pid(pid)
        mine = LockRecord(pid=own_pid, owner=owner)

        with self._guarded():
            state, existing = self.read()
            if state == _ABSENT:
                self._write(mine)
                return LockDecision(ACQUIRED, own_pid)

            if state == _INVALID:
                if policy is TakeoverPolicy.ALWAYS:
                    self._write(mine)
                    return LockDecision(
                        STALE_TAKEN_OVER, own_pid,
                        reason="malformed lock replaced by explicit policy",
                    )
                return LockDecision(INVALID_LOCK, own_pid,
                                    reason="lock file is unreadable or malformed")

            assert existing is not None
            if existing.pid == own_pid:
                return LockDecision(ALREADY_OWNED, own_pid,
                                    previous_pid=existing.pid,
                                    reason="lock already records this PID")

            if self._probe(existing.pid):
                if policy is TakeoverPolicy.ALWAYS:
                    self._write(mine)
                    return LockDecision(
                        LIVE_TAKEN_OVER, own_pid, previous_pid=existing.pid,
                        reason="live owner replaced by explicit policy",
                    )
                return LockDecision(COMPETING_INSTANCE, own_pid,
                                    previous_pid=existing.pid,
                                    reason="another live process owns the lock")

            if policy is TakeoverPolicy.NEVER:
                return LockDecision(STALE_LOCK_BLOCKED, own_pid,
                                    previous_pid=existing.pid,
                                    reason="stale lock kept by NEVER policy")
            self._write(mine)
            return LockDecision(STALE_TAKEN_OVER, own_pid,
                                previous_pid=existing.pid,
                                reason="dead owner's lock reclaimed")

    def release(self, pid: Optional[int] = None) -> bool:
        """Remove the lock only while it still records this process's PID."""
        own_pid = self._normalise_pid(pid)
        with self._guarded():
            state, existing = self.read()
            if state != _VALID or existing is None or existing.pid != own_pid:
                return False
            try:
                os.unlink(self.lock_path)
            except FileNotFoundError:
                return False
            return True
