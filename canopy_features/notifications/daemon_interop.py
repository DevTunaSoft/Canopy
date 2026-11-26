"""Bounded native notification daemon interoperability contracts.

This is a **pure in-process contract** at the existing trusted source boundary.
It never opens a transport, contacts a daemon, launches a process, observes the
desktop, or reads the filesystem or environment. It creates no Qt object,
timer, poll, thread, socket or background service. It does **not** claim that a
daemon exists or that any notification was delivered.

The interop state is computed from two bounded, host-only probes over the
already-reviewed trusted source:

* a **source-loss probe** reads the trusted source's liveness and records a
  bounded loss event when the source is closed, disconnected, returns anything
  other than exact ``True``, or raises;
* a **capability probe** validates one bounded, host-supplied observation that
  must carry the exact native-interop contract token and an exact boolean
  acknowledgement.

Nothing is inferred, invented or echoed. A missing, hostile, oversized or
unrecognised observation, an exhausted probe budget, a lost source or an
explicit close all fail closed to the ``unavailable`` state with a fixed reason
and a fixed refusal token. Recovery requires an explicit host-only
``reattach()`` followed by a fresh capability probe. No host-event topic,
payload field or protocol version is added or changed by this module.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import unicodedata

from canopy_features.notifications.host_event_source import TrustedHostEventSource
from canopy_features.notifications.host_snapshot_producer import HostSnapshotProducer

__all__ = [
    "AVAILABLE",
    "AVAILABLE_KEY",
    "CAPABILITY_ABSENT",
    "CAPABILITY_KEY",
    "CAPABILITY_PRESENT",
    "CAPABILITY_REFUSED",
    "CLOSED",
    "INTEROP_CLOSED",
    "INVALID_CAPABILITY",
    "INVALID_SOURCE",
    "MAX_CAPABILITY_FIELDS",
    "MAX_PROBES",
    "MAX_TOKEN_BYTES",
    "NATIVE_INTEROP",
    "NONE",
    "NOT_PROBED",
    "NO_SOURCE",
    "PROBE_LIMIT",
    "SOURCE_LIVE",
    "SOURCE_LOST",
    "UNAVAILABLE",
    "DaemonInteropError",
    "InteropState",
    "NotificationDaemonInterop",
]

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
NONE = "none"
NOT_PROBED = "not_probed"
SOURCE_LIVE = "source_live"
SOURCE_LOST = "source_lost"
CAPABILITY_PRESENT = "capability_present"
CAPABILITY_ABSENT = "capability_absent"
CAPABILITY_REFUSED = "capability_refused"
PROBE_LIMIT = "probe_limit"
CLOSED = "closed"
NO_SOURCE = "no_source"

# Fixed refusal tokens. Caller data, exception text and rejected values never
# reach these tokens or the state surface.
INVALID_CAPABILITY = "INVALID_CAPABILITY_OBSERVATION"
INVALID_SOURCE = "INVALID_SOURCE_PROBE"
INTEROP_CLOSED = "INTEROP_CLOSED"

MAX_PROBES = 16
MAX_CAPABILITY_FIELDS = 8
MAX_TOKEN_BYTES = 64

NATIVE_INTEROP = "native_notification_daemon"
CAPABILITY_KEY = "capability"
AVAILABLE_KEY = "available"
_ALLOWED_KEYS = frozenset({CAPABILITY_KEY, AVAILABLE_KEY})
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_TRUSTED_TYPES = (TrustedHostEventSource, HostSnapshotProducer)
_REFUSAL_REASONS = {
    INVALID_CAPABILITY: CAPABILITY_REFUSED,
    INVALID_SOURCE: SOURCE_LOST,
    PROBE_LIMIT: PROBE_LIMIT,
    INTEROP_CLOSED: CLOSED,
}


class DaemonInteropError(ValueError):
    """Invalid bound, untrusted source or operation after explicit shutdown."""


@dataclass(frozen=True)
class InteropState:
    """Explicit availability, bounded probe view and fixed refusal token."""

    status: str
    reason: str
    refusal: object
    source_probe: str
    capability_probe: str
    probe_count: int
    loss_count: int

    def as_dict(self):
        """Fresh copy; mutation cannot affect a later state read."""
        return {
            "status": self.status,
            "reason": self.reason,
            "refusal": self.refusal,
            "source_probe": self.source_probe,
            "capability_probe": self.capability_probe,
            "probe_count": self.probe_count,
            "loss_count": self.loss_count,
        }


class NotificationDaemonInterop:
    """Host-owned, bounded interop view over one trusted source.

    ``probe_source`` and ``probe_capability`` each spend one unit of a fixed
    probe budget, expose only fixed tokens, and never retain caller data.
    ``state`` is a pure read of the last probes; it performs no I/O and starts
    unprobed. A lost source stays lost until explicit host ``reattach``.
    """

    def __init__(self, source=None, *, max_probes=MAX_PROBES):
        if type(max_probes) is not int or not 1 <= max_probes <= MAX_PROBES:
            raise DaemonInteropError("invalid probe bound")
        if source is None:
            source = TrustedHostEventSource()
            self._owns_source = True
        else:
            self._owns_source = False
            self._check_source(source)
        self._source = source
        self._max_probes = max_probes
        self._probe_count = 0
        self._loss_count = 0
        self._source_probe = NOT_PROBED
        self._capability_probe = NOT_PROBED
        self._refusal = None
        self._closed = False
        self._lost = False

    @staticmethod
    def _check_source(source):
        if type(source) not in _TRUSTED_TYPES:
            raise DaemonInteropError("trusted source required")
        try:
            live = source.connected()
        except Exception:
            live = False
        if live is not True:
            raise DaemonInteropError("trusted source is not connected")

    def _ready(self):
        if self._closed:
            raise DaemonInteropError("interop is closed")

    def _spend(self):
        self._ready()
        if self._probe_count >= self._max_probes:
            self._refusal = PROBE_LIMIT
            return False
        self._probe_count += 1
        return True

    def probe_source(self):
        """Read source liveness once; any non-true answer is a bounded loss."""
        if not self._spend():
            return SOURCE_LOST
        try:
            live = self._source.connected()
        except Exception:
            live = False
        if live is not True:
            self._source_probe = SOURCE_LOST
            self._capability_probe = NOT_PROBED
            self._loss_count += 1
            self._lost = True
            self._refusal = INVALID_SOURCE
            return SOURCE_LOST
        self._source_probe = SOURCE_LIVE
        return SOURCE_LIVE

    @staticmethod
    def _validate_observation(observation):
        if not isinstance(observation, Mapping):
            return False
        try:
            if not 1 <= len(observation) <= MAX_CAPABILITY_FIELDS:
                return False
            items = tuple(observation.items())
        except Exception:
            return False
        seen = {}
        for key, value in items:
            if type(key) is not str or key not in _ALLOWED_KEYS or key in seen:
                return False
            seen[key] = value
        if set(seen) != _ALLOWED_KEYS:
            return False
        token = seen[CAPABILITY_KEY]
        if type(token) is not str or token != NATIVE_INTEROP:
            return False
        if len(token.encode("utf-8", "strict")) > MAX_TOKEN_BYTES:
            return False
        if any(unicodedata.category(char) in _UNSAFE_CATEGORIES
               for char in token):
            return False
        return seen[AVAILABLE_KEY] is True

    def probe_capability(self, observation):
        """Validate one bounded host observation; fail closed on any doubt."""
        self._ready()
        if self._source_probe == NOT_PROBED:
            self.probe_source()
        if not self._spend():
            self._capability_probe = NOT_PROBED
            return CAPABILITY_ABSENT
        if self._lost:
            self._capability_probe = NOT_PROBED
            self._refusal = INVALID_SOURCE
            return CAPABILITY_ABSENT
        try:
            valid = self._validate_observation(observation)
        except Exception:
            valid = False
        if not valid:
            self._capability_probe = CAPABILITY_ABSENT
            self._refusal = INVALID_CAPABILITY
            return CAPABILITY_ABSENT
        self._capability_probe = CAPABILITY_PRESENT
        self._refusal = None
        return CAPABILITY_PRESENT

    def probe(self, observation=None):
        """One bounded interop cycle: source liveness, then capability."""
        self._ready()
        self.probe_source()
        if observation is not None:
            self.probe_capability(observation)
        return self.state()

    def state(self):
        """Pure, bounded availability view; never probes or mutates."""
        source_probe = self._source_probe
        capability_probe = self._capability_probe
        probe_count = self._probe_count
        loss_count = self._loss_count
        if self._closed:
            return InteropState(UNAVAILABLE, CLOSED, INTEROP_CLOSED,
                                source_probe, capability_probe,
                                probe_count, loss_count)
        if self._refusal is not None:
            reason = _REFUSAL_REASONS.get(self._refusal, self._refusal)
            return InteropState(UNAVAILABLE, reason, self._refusal,
                                source_probe, capability_probe,
                                probe_count, loss_count)
        if self._lost:
            return InteropState(UNAVAILABLE, SOURCE_LOST, INVALID_SOURCE,
                                source_probe, capability_probe,
                                probe_count, loss_count)
        if self._source_probe != SOURCE_LIVE:
            return InteropState(UNAVAILABLE, NO_SOURCE, None,
                                source_probe, capability_probe,
                                probe_count, loss_count)
        if self._capability_probe != CAPABILITY_PRESENT:
            return InteropState(UNAVAILABLE, CAPABILITY_ABSENT, None,
                                source_probe, capability_probe,
                                probe_count, loss_count)
        return InteropState(AVAILABLE, NONE, None,
                            source_probe, capability_probe,
                            probe_count, loss_count)

    def reattach(self, source):
        """Explicit host-only recovery from a recorded source loss."""
        self._ready()
        self._check_source(source)
        if self._owns_source:
            self._source.close()
            self._owns_source = False
        self._source = source
        self._lost = False
        self._source_probe = NOT_PROBED
        self._capability_probe = NOT_PROBED
        self._refusal = None
        self.probe_source()
        return self.state()

    def close(self):
        """Idempotent shutdown; only a self-owned source is closed."""
        if self._closed:
            return
        if self._owns_source:
            self._source.close()
        self._closed = True
        self._capability_probe = NOT_PROBED
        self._refusal = INTEROP_CLOSED
