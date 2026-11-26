"""Bounded trust gate for host events before they reach shell state.

This is a pure in-process ingress bridge. Trusted host code grants a fixed
source identity a fixed subset of the existing protocol-v2 topics from
``canopy_core.host_events``; this module neither extends that contract nor
creates events, callbacks, threads, timers, sockets, processes or I/O.

Every hostile or oversized event is refused with a fixed reason token before
it can enter the bounded pending queue. Only an explicit ``drain()`` hands
frozen records to trusted shell code. Source checks use object identity, so a
lookalike value cannot impersonate a grant through ``__eq__``/``__hash__``.
This is an in-process boundary, not authentication or a sandbox for already
trusted host code, and it does not claim Qt, Mint or visual acceptance.
"""
from collections import deque
from dataclasses import dataclass
from types import MappingProxyType

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    _encode_fields,
)

__all__ = [
    "MAX_BATCH",
    "MAX_EVENT_BYTES",
    "MAX_PENDING",
    "EventTrustBoundary",
    "EventTrustError",
    "IngressEvent",
    "SourceGrant",
]

MAX_PENDING = 16
MAX_BATCH = 16
MAX_EVENT_BYTES = 2048
if PROTOCOL_VERSION != 2 or len(HOST_EVENT_TOPICS) != 4:  # pragma: no cover
    raise RuntimeError("host event contract changed; trust gate must be reviewed")


class EventTrustError(ValueError):
    """A source, topic, payload, bound or lifecycle check failed closed."""


@dataclass(frozen=True)
class SourceGrant:
    """One exact source identity and its immutable topic subset."""

    source: object
    topics: frozenset


@dataclass(frozen=True)
class IngressEvent:
    """Frozen queue record; payload is a fresh read-only mapping."""

    version: int
    topic: str
    sequence: int
    fields: tuple

    @property
    def payload(self):
        return MappingProxyType(dict(self.fields))


def _validate_grants(grants):
    if type(grants) not in (tuple, list) or not grants:
        raise EventTrustError("explicit source grants required")
    vetted = []
    seen = []
    for grant in grants:
        if type(grant) is not SourceGrant or grant.source is None:
            raise EventTrustError("invalid host source grant")
        if type(grant.topics) is not frozenset or not grant.topics:
            raise EventTrustError("invalid granted topic set")
        if any(type(topic) is not str or topic not in HOST_EVENT_TOPICS
               for topic in grant.topics):
            raise EventTrustError("grant cannot extend the event contract")
        if any(grant.source is prior for prior in seen):
            raise EventTrustError("duplicate host source grant")
        seen.append(grant.source)
        vetted.append(grant)
    return tuple(vetted)


class EventTrustBoundary:
    """Accept only granted host events into a bounded, drainable queue."""

    def __init__(self, grants, *, max_pending=MAX_PENDING,
                 max_batch=MAX_BATCH):
        if (type(max_pending) is not int or
                not 1 <= max_pending <= MAX_PENDING):
            raise EventTrustError("invalid pending-event bound")
        if type(max_batch) is not int or not 1 <= max_batch <= MAX_BATCH:
            raise EventTrustError("invalid drain bound")
        self._grants = _validate_grants(grants)
        self._max_pending = max_pending
        self._max_batch = max_batch
        self._queue = deque()
        self._sequence = 0
        self._rejection_count = 0
        self._last_rejection = None
        self._closed = False

    def _reject(self, reason):
        # Only fixed tokens are recorded; never echo a hostile source or
        # payload into rejection state, logs or shell-facing records.
        self._rejection_count += 1
        self._last_rejection = reason
        raise EventTrustError("host event rejected: " + reason)

    def ingest(self, source, topic, payload):
        """Validate one host event, then queue it; return its sequence.

        A rejection leaves the queue, sequence and shell state untouched.
        """
        if self._closed:
            self._reject("CLOSED")
        grant = next((g for g in self._grants if g.source is source), None)
        if grant is None:
            self._reject("UNTRUSTED_SOURCE")
        if type(topic) is not str or topic not in grant.topics:
            self._reject("UNSUPPORTED_TOPIC")
        try:
            fields = _encode_fields(payload)
        except Exception as exc:
            # A hostile caller must receive the domain error, never a raw
            # UnicodeError/TypeError/ValueError from payload inspection.
            if isinstance(exc, EventTrustError):
                raise
            self._reject("INVALID_PAYLOAD")
        total = sum(len(key.encode("utf-8", "strict")) +
                    len(str(value).encode("utf-8", "strict"))
                    for key, value in fields)
        if total > MAX_EVENT_BYTES:
            self._reject("OVERSIZED_EVENT")
        if len(self._queue) >= self._max_pending:
            self._reject("QUEUE_FULL")
        self._sequence += 1
        self._queue.append(IngressEvent(
            PROTOCOL_VERSION, topic, self._sequence, fields))
        return self._sequence

    def drain(self, limit=None):
        """Remove and return up to ``limit`` frozen records in arrival order.

        ``None`` means the configured ``max_batch``, so the default never
        exceeds the capacity chosen by trusted host code.
        """
        if self._closed:
            self._reject("CLOSED")
        if limit is None:
            limit = self._max_batch
        if type(limit) is not int or not 1 <= limit <= self._max_batch:
            self._reject("INVALID_LIMIT")
        ready = []
        for _ in range(min(limit, len(self._queue))):
            ready.append(self._queue.popleft())
        return tuple(ready)

    def close(self):
        """Drop every grant and pending record; later operations fail closed."""
        if self._closed:
            return
        self._queue.clear()
        self._grants = ()
        self._closed = True

    @property
    def pending(self):
        return len(self._queue)

    @property
    def rejection_count(self):
        return self._rejection_count

    @property
    def last_rejection(self):
        return self._last_rejection

    @property
    def closed(self):
        return self._closed
