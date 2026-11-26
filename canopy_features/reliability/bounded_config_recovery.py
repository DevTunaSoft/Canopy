"""Bounded, fail-closed reads for caller-owned installer/session config files.

This is a pure host-side primitive. It reads at most ``max_bytes + 1`` bytes
from one caller-supplied path, never writes, never logs file content, and
never follows a symlink in the path. A rejected document is reported as
``CORRUPT`` together with its bounded raw bytes so a caller can preserve them
in a bounded snapshot before replacing the file; oversized, unreadable and
unsafe paths are reported without retaining any content and must never be
overwritten.

The status vocabulary is deliberately small and fixed: ``OK``, ``CORRUPT``,
``MISSING``, ``OVERSIZE``, ``UNREADABLE`` and ``UNSAFE_PATH``. Duplicate JSON
object keys are corrupt: ``json.loads`` otherwise silently keeps the last one
and can manufacture a false clean result.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "OK", "CORRUPT", "MISSING", "OVERSIZE", "UNREADABLE", "UNSAFE_PATH",
    "SNAPSHOT_SUFFIX", "MAX_SNAPSHOTS",
    "LoadedConfig", "ConfigRecoveryError", "read_bounded_config",
    "quarantine_config", "write_bounded_config",
]

OK = "OK"
CORRUPT = "CORRUPT"
MISSING = "MISSING"
OVERSIZE = "OVERSIZE"
UNREADABLE = "UNREADABLE"
UNSAFE_PATH = "UNSAFE_PATH"

SNAPSHOT_SUFFIX = ".corrupt"
MAX_SNAPSHOTS = 3


class ConfigRecoveryError(ValueError):
    """A config path, bound or recovery operation is invalid."""


@dataclass(frozen=True)
class LoadedConfig:
    """Bounded result of one read; ``raw`` is empty only for refused states."""

    status: str
    document: object
    raw: bytes


class _DuplicateKey(ValueError):
    """Internal sentinel: a JSON object repeated a key."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey("duplicate JSON key")
        result[key] = value
    return result


def _path_from(value):
    """Return a safe absolute ``Path`` or ``None`` if it cannot be trusted."""
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
        return Path(os.path.abspath(text))
    except (OSError, ValueError):
        return None


def _safe_path(path):
    """Reject a symlink at any existing component of ``path``."""
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        except OSError:
            return False
        if stat.S_ISLNK(mode):
            return False
    return True


def read_bounded_config(path, *, max_bytes):
    """Read one config file with a strict byte bound and no writes.

    ``max_bytes`` must be a positive ``int``. The file is opened with a plain
    bounded ``read`` so a hostile file cannot be materialized in full even if
    its reported size changes between a stat and the read. No exception text
    or status includes file content.
    """
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ConfigRecoveryError("config byte bound must be positive")
    candidate = _path_from(path)
    if candidate is None or not _safe_path(candidate):
        return LoadedConfig(UNSAFE_PATH, None, b"")
    try:
        with candidate.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except FileNotFoundError:
        return LoadedConfig(MISSING, None, b"")
    except OSError:
        return LoadedConfig(UNREADABLE, None, b"")
    if len(raw) > max_bytes:
        return LoadedConfig(OVERSIZE, None, b"")
    try:
        document = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (_DuplicateKey, UnicodeError, ValueError, TypeError):
        return LoadedConfig(CORRUPT, None, raw)
    return LoadedConfig(OK, document, raw)


def _snapshot_paths(path):
    """Return the bounded, boundary-checked rotation slots for one path."""
    candidate = _path_from(path)
    if candidate is None or not _safe_path(candidate):
        raise ConfigRecoveryError("unsafe config recovery path")
    slots = []
    for index in range(MAX_SNAPSHOTS):
        suffix = SNAPSHOT_SUFFIX if index == 0 else (
            SNAPSHOT_SUFFIX + "." + str(index))
        slot = Path(str(candidate) + suffix)
        if not _safe_path(slot):
            raise ConfigRecoveryError("unsafe config snapshot path")
        slots.append(slot)
    return slots


def quarantine_config(path, raw, *, max_bytes):
    """Keep bounded raw snapshots before a caller replaces ``path``.

    At most :data:`MAX_SNAPSHOTS` snapshots are retained, newest at the
    unsuffixed ``.corrupt`` path. The original config is never touched here.
    A staging file is written first and a failed rotation is rolled back, so
    a failed quarantine neither loses an earlier snapshot nor leaves a
    temporary artifact behind.
    """
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ConfigRecoveryError("config byte bound must be positive")
    if not isinstance(raw, bytes) or not 0 < len(raw) <= max_bytes:
        raise ConfigRecoveryError("corrupt config bytes exceed their bound")
    slots = _snapshot_paths(path)

    staged = None
    rotated = []
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".canopy-config-recovery-", dir=str(slots[0].parent))
        staged = Path(temporary)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        # Rotate from oldest to newest, then publish the new snapshot last.
        for index in range(len(slots) - 1, 0, -1):
            if slots[index - 1].exists():
                os.replace(str(slots[index - 1]), str(slots[index]))
                rotated.append(index)
        os.replace(str(staged), str(slots[0]))
        staged = None
    except OSError as exc:
        for index in reversed(rotated):
            try:
                if slots[index].exists():
                    os.replace(str(slots[index]), str(slots[index - 1]))
            except OSError:  # pragma: no cover - best-effort rollback
                pass
        raise ConfigRecoveryError("could not quarantine config bytes") from exc
    finally:
        if staged is not None:
            try:
                staged.unlink()
            except OSError:  # pragma: no cover - best-effort cleanup
                pass
    return tuple(slots)


def write_bounded_config(path, document, *, max_bytes):
    """Atomically publish a bounded JSON document to ``path``.

    The caller owns the replacement decision; this function only performs the
    write after its byte and path bounds are satisfied. A failure leaves no
    staging artifact and does not touch an existing file.
    """
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ConfigRecoveryError("config byte bound must be positive")
    candidate = _path_from(path)
    if candidate is None or not _safe_path(candidate):
        raise ConfigRecoveryError("unsafe config recovery path")
    try:
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ConfigRecoveryError("config is not JSON serializable") from exc
    if len(payload) > max_bytes:
        raise ConfigRecoveryError("config exceeds its byte bound")

    staged = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".canopy-config-recovery-", dir=str(candidate.parent))
        staged = Path(temporary)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(staged), str(candidate))
        staged = None
    except OSError as exc:
        raise ConfigRecoveryError("could not write config") from exc
    finally:
        if staged is not None:
            try:
                staged.unlink()
            except OSError:  # pragma: no cover - best-effort cleanup
                pass
