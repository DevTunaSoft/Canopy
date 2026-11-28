"""Single upstream notification-daemon owner proof (read-only contract).

This module never requests a D-Bus name, registers a service, starts a
notification daemon or checks one out. It validates a bounded host observation
that must describe exactly one upstream Plasma owner of
``org.freedesktop.Notifications`` with zero foreign daemons, zero Canopy-owned
daemons/fixtures and zero activatable duplicate service files. Every doubt is
a fixed-token refusal; no rejected value or exception text reaches the state
surface. This is a contract, not a claim that a live desktop was observed.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass
import unicodedata

__all__ = [
    "ACCEPT", "ACCEPTED", "BUS_NAME", "CLOSED", "INVALID_OWNER_OBSERVATION",
    "MAX_OBSERVATION_FIELDS", "MAX_PID", "NO_OBSERVATION", "OBSERVATION_KEYS",
    "REFUSED", "SINGLE_UPSTREAM_OWNER", "UNAVAILABLE", "DaemonOwnerError",
    "DaemonOwnerProof", "OwnerState",
]

BUS_NAME = "org.freedesktop.Notifications"
ALLOWED_OWNER_COMMS = frozenset({"plasmashell"})
MAX_OBSERVATION_FIELDS = 8
MAX_PID = (1 << 31) - 1
MAX_TEXT_BYTES = 64

OBSERVATION_KEYS = frozenset({
    "well_known_name", "owner", "owner_pid", "owner_comm",
    "foreign_daemon_count", "canopy_daemon_count",
    "activatable_service_files",
})

ACCEPT = "accept"
ACCEPTED = "accepted"
REFUSED = "refused"
SINGLE_UPSTREAM_OWNER = "single_upstream_owner"
UNAVAILABLE = "unavailable"
CLOSED = "closed"
NO_OBSERVATION = "no_observation"
INVALID_OWNER_OBSERVATION = "INVALID_OWNER_OBSERVATION"

_UNIQUE_NAME = re.compile(r":1\.[0-9]{1,9}(?:\.[0-9]{1,9})?\Z")
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


class DaemonOwnerError(ValueError):
    """Invalid bound or an operation after explicit shutdown."""


@dataclass(frozen=True)
class OwnerState:
    """Fixed-token single-owner view; the owner name is never echoed."""

    status: str
    reason: str
    refusal: object
    owner_verified: bool
    foreign_daemon_count: int
    canopy_daemon_count: int
    activatable_service_files: int
    probe_count: int

    def as_dict(self):
        return {
            "status": self.status, "reason": self.reason,
            "refusal": self.refusal, "owner_verified": self.owner_verified,
            "foreign_daemon_count": self.foreign_daemon_count,
            "canopy_daemon_count": self.canopy_daemon_count,
            "activatable_service_files": self.activatable_service_files,
            "probe_count": self.probe_count,
        }


class DaemonOwnerProof:
    """Host-owned, bounded proof over one daemon-ownership observation.

    ``observe()`` spends one unit of a fixed budget and returns a fixed token.
    A first accepted observation may establish a single upstream owner; any
    later conflicting observation is refused. ``state()`` is a pure read.
    """

    def __init__(self, *, max_probes=8):
        if type(max_probes) is not int or not 1 <= max_probes <= 8:
            raise DaemonOwnerError("invalid probe bound")
        self._max_probes = max_probes
        self._probe_count = 0
        self._owner = None
        self._established = False
        self._refusal = None
        self._closed = False
        self._counts = dict(foreign=0, canopy=0, service_files=0)

    @staticmethod
    def _text(value, limit, expected=None):
        if type(value) is not str or not value:
            return None
        if len(value) > limit or len(value.encode("utf-8", "strict")) > limit:
            return None
        if any(unicodedata.category(char) in _UNSAFE_CATEGORIES
               for char in value):
            return None
        if expected is not None and value != expected:
            return None
        return value

    @staticmethod
    def _zero(value):
        return type(value) is int and value == 0

    @classmethod
    def _validate(cls, observation):
        if not isinstance(observation, Mapping):
            return None
        try:
            items = tuple(observation.items())
        except Exception:
            return None
        if not 1 <= len(items) <= MAX_OBSERVATION_FIELDS:
            return None
        seen = {}
        for key, value in items:
            if type(key) is not str or key not in OBSERVATION_KEYS or key in seen:
                return None
            seen[key] = value
        if frozenset(seen) != OBSERVATION_KEYS:
            return None
        if cls._text(seen["well_known_name"], MAX_TEXT_BYTES, BUS_NAME) is None:
            return None
        owner = cls._text(seen["owner"], MAX_TEXT_BYTES)
        if owner is None or _UNIQUE_NAME.fullmatch(owner) is None:
            return None
        pid = seen["owner_pid"]
        if type(pid) is not int or not 1 <= pid <= MAX_PID:
            return None
        comm = seen["owner_comm"]
        if type(comm) is not str or comm not in ALLOWED_OWNER_COMMS:
            return None
        for field in ("foreign_daemon_count", "canopy_daemon_count",
                      "activatable_service_files"):
            if not cls._zero(seen[field]):
                return None
        return owner

    def _ready(self):
        if self._closed:
            raise DaemonOwnerError("daemon owner proof is closed")

    def observe(self, observation):
        """Validate one bounded host report; return a fixed token."""
        self._ready()
        if self._probe_count >= self._max_probes:
            self._refusal = INVALID_OWNER_OBSERVATION
            self._probe_count += 1
            return REFUSED
        self._probe_count += 1
        try:
            owner = self._validate(observation)
        except Exception:
            owner = None
        if owner is None or (self._established and owner != self._owner):
            self._refusal = INVALID_OWNER_OBSERVATION
            return REFUSED
        self._owner = owner
        self._established = True
        self._refusal = None
        return ACCEPT

    def state(self):
        """Pure bounded view; no probe, no bus query, no process scan."""
        verified = self._established and self._refusal is None
        if self._closed:
            status, reason = UNAVAILABLE, CLOSED
        elif self._refusal is not None:
            status, reason = UNAVAILABLE, INVALID_OWNER_OBSERVATION
        elif not verified:
            status, reason = UNAVAILABLE, NO_OBSERVATION
        else:
            status, reason = SINGLE_UPSTREAM_OWNER, "none"
        return OwnerState(
            status=status, reason=reason, refusal=self._refusal,
            owner_verified=verified,
            foreign_daemon_count=self._counts["foreign"],
            canopy_daemon_count=self._counts["canopy"],
            activatable_service_files=self._counts["service_files"],
            probe_count=min(self._probe_count, self._max_probes))

    def close(self):
        """Idempotent shutdown; no upstream daemon is touched."""
        if self._closed:
            return
        self._closed = True
        self._established = False
        self._refusal = None
