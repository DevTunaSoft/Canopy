"""Bounded, in-memory coalescing of catalog and cache write requests.

A caller declares the named write targets and calls ``mark_dirty`` whenever a
snapshot changes. Repeated marks for one target collapse into one pending
write; ``flush`` returns immutable write intents only when the caller explicitly
requests a flush on a host lifecycle event. ``invalidate`` drops pending work
without producing a write.

This module performs no filesystem I/O, clock reads, threads, timers or
polling. It emits intents; executing any write is the host's responsibility.
Counts and generations saturate at fixed ceilings, and both the number of
pending targets and their total payload bytes are bounded.
"""
from dataclasses import dataclass
from types import MappingProxyType

MAX_TARGETS = 32
MAX_NAME_CHARS = 48
MAX_PAYLOAD_BYTES = 65536
MAX_PENDING_BYTES = 4 * MAX_PAYLOAD_BYTES
GENERATION_CEILING = 4096
COUNTER_CEILING = 4096

CLAIM_NO_POLLING = "no_polling"
CLAIM_NO_TIMERS = "no_timers"
CLAIM_NO_THREADS = "no_threads"
CLAIM_NO_FILESYSTEM_IO = "no_filesystem_io"
CLAIM_COALESCED_LAST_VALUE_WINS = "coalesced_last_value_wins"
CLAIM_EXPLICIT_INVALIDATION = "explicit_invalidation"
CLAIM_NO_PAYLOAD_IN_DIAGNOSTICS = "no_payload_in_diagnostics"

FIXED_CLAIMS = (
    CLAIM_COALESCED_LAST_VALUE_WINS,
    CLAIM_EXPLICIT_INVALIDATION,
    CLAIM_NO_FILESYSTEM_IO,
    CLAIM_NO_PAYLOAD_IN_DIAGNOSTICS,
    CLAIM_NO_POLLING,
    CLAIM_NO_THREADS,
    CLAIM_NO_TIMERS,
)

__all__ = [
    "COUNTER_CEILING", "CLAIM_COALESCED_LAST_VALUE_WINS",
    "CLAIM_EXPLICIT_INVALIDATION", "CLAIM_NO_FILESYSTEM_IO",
    "CLAIM_NO_PAYLOAD_IN_DIAGNOSTICS", "CLAIM_NO_POLLING", "CLAIM_NO_THREADS",
    "CLAIM_NO_TIMERS", "DEFAULT_TARGETS", "FIXED_CLAIMS",
    "GENERATION_CEILING", "MAX_NAME_CHARS", "MAX_PAYLOAD_BYTES",
    "MAX_PENDING_BYTES", "MAX_TARGETS", "DiskActivityError", "DirtyWrite",
    "DiskActivitySnapshot", "DiskWriteCoalescer", "WriteIntent", "WriteTarget",
]


class DiskActivityError(ValueError):
    """Invalid target, payload or bound in a disk-activity contract."""


def _valid_name(value):
    if type(value) is not str or not 0 < len(value) <= MAX_NAME_CHARS:
        return False
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_"
    return (value[0] in "abcdefghijklmnopqrstuvwxyz"
            and all(char in allowed for char in value))


@dataclass(frozen=True)
class WriteTarget:
    """One named write target and its maximum payload in bytes."""

    name: str
    max_payload_bytes: int

    def __post_init__(self):
        if not _valid_name(self.name):
            raise DiskActivityError("write target name must be bounded ascii")
        if (type(self.max_payload_bytes) is not int
                or not 1 <= self.max_payload_bytes <= MAX_PAYLOAD_BYTES):
            raise DiskActivityError("write target payload bound out of range")


@dataclass(frozen=True)
class DirtyWrite:
    """Caller-facing result of marking one target dirty."""

    target: str
    generation: int
    payload: bytes
    coalesced: bool


@dataclass(frozen=True)
class WriteIntent:
    """One pending write, emitted only by an explicit flush."""

    target: str
    generation: int
    payload: bytes


@dataclass(frozen=True)
class DiskActivitySnapshot:
    """Immutable diagnostics; payload bytes are never echoed."""

    pending_targets: tuple
    pending_count: int
    pending_bytes: int
    coalesced_count: int
    flush_count: int
    invalidated_count: int
    claims: tuple

    def to_dict(self):
        """Return a read-only view of counts and claims, never payload bytes."""
        return MappingProxyType({
            "pending_targets": self.pending_targets,
            "pending_count": self.pending_count,
            "pending_bytes": self.pending_bytes,
            "coalesced_count": self.coalesced_count,
            "flush_count": self.flush_count,
            "invalidated_count": self.invalidated_count,
            "claims": list(self.claims),
        })


DEFAULT_TARGETS = (
    WriteTarget("launcher_catalog", MAX_PAYLOAD_BYTES),
    WriteTarget("icon_cache", MAX_PAYLOAD_BYTES),
    WriteTarget("dock_pin_cache", 4096),
    WriteTarget("launcher_favorites_cache", 4096),
)


class DiskWriteCoalescer:
    """Coalesce dirty snapshots into at most one pending write per target."""

    __slots__ = ("_targets", "_pending", "_pending_bytes", "_coalesced",
                 "_flushed", "_invalidated", "_generation")

    def __init__(self, targets=DEFAULT_TARGETS):
        if isinstance(targets, (str, bytes, bytearray, dict)) or not hasattr(targets, "__iter__"):
            raise DiskActivityError("targets must be an iterable of WriteTarget records")
        self._targets = {}
        for target in targets:
            if not isinstance(target, WriteTarget):
                raise DiskActivityError("targets must be WriteTarget records")
            if len(self._targets) >= MAX_TARGETS:
                raise DiskActivityError("too many write targets")
            if target.name in self._targets:
                raise DiskActivityError("duplicate write target")
            self._targets[target.name] = target
        if not self._targets:
            raise DiskActivityError("at least one write target is required")
        self._pending = {}
        self._pending_bytes = 0
        self._coalesced = 0
        self._flushed = 0
        self._invalidated = 0
        self._generation = 0

    def mark_dirty(self, name, payload):
        """Coalesce one bounded payload into the pending write for a target."""
        if type(name) is not str or name not in self._targets:
            raise DiskActivityError("unknown write target")
        target = self._targets[name]
        if (type(payload) is not bytes
                or not 0 < len(payload) <= target.max_payload_bytes):
            raise DiskActivityError("payload must be bounded bytes")
        coalesced = name in self._pending
        previous_bytes = len(self._pending[name][1]) if coalesced else 0
        if self._pending_bytes - previous_bytes + len(payload) > MAX_PENDING_BYTES:
            raise DiskActivityError("pending payload total out of range")
        if coalesced:
            self._coalesced = min(COUNTER_CEILING, self._coalesced + 1)
            self._pending_bytes -= previous_bytes
        self._generation = min(GENERATION_CEILING, self._generation + 1)
        self._pending[name] = (self._generation, payload)
        self._pending_bytes += len(payload)
        return DirtyWrite(name, self._generation, payload, coalesced)

    def flush(self, names=None):
        """Emit at most one intent per explicitly requested pending target.

        With no names, all pending targets are emitted in insertion order.
        With names, the caller's order is preserved and unknown or repeated
        names fail closed. A flush never creates work or waits for work.
        """
        if names is None:
            ordered = tuple(self._pending)
        else:
            if isinstance(names, (str, bytes, bytearray)) or not hasattr(names, "__iter__"):
                raise DiskActivityError("flush names must be an iterable")
            ordered = []
            seen = set()
            for name in names:
                if type(name) is not str or name not in self._targets:
                    raise DiskActivityError("unknown write target")
                if name in seen:
                    raise DiskActivityError("duplicate flush target")
                seen.add(name)
                if name in self._pending:
                    ordered.append(name)
        intents = tuple(WriteIntent(name, *self._pending.pop(name))
                        for name in ordered)
        self._pending_bytes -= sum(len(intent.payload) for intent in intents)
        self._flushed = min(COUNTER_CEILING, self._flushed + len(intents))
        return intents

    def invalidate(self, name):
        """Drop one pending write without emitting it; report whether it existed."""
        if type(name) is not str or name not in self._targets:
            raise DiskActivityError("unknown write target")
        if name not in self._pending:
            return False
        self._pending_bytes -= len(self._pending.pop(name)[1])
        self._invalidated = min(COUNTER_CEILING, self._invalidated + 1)
        return True

    def invalidate_all(self):
        """Drop every pending write without emitting it; return the count."""
        dropped = len(self._pending)
        self._pending.clear()
        self._pending_bytes = 0
        self._invalidated = min(COUNTER_CEILING, self._invalidated + dropped)
        return dropped

    def snapshot(self):
        """Return an immutable, payload-free view of bounded state."""
        return DiskActivitySnapshot(
            tuple(self._pending), len(self._pending), self._pending_bytes,
            self._coalesced, self._flushed, self._invalidated, FIXED_CLAIMS)
