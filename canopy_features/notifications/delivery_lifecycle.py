"""Bounded notification delivery lifecycle at the trusted source boundary.

This pure in-process adapter composes the already-reviewed
``TrustedHostEventSource`` and ``HostSnapshotProducer`` into one bounded,
fail-closed delivery queue with explicit dedup, overflow and unavailability
states. Every queued row originates in a real ``HostEvent`` published through
the trusted host-only ``deliver()`` call; no row is invented, no payload value
is echoed into a refusal, and no caller data leaves the process.

It creates no Qt object, D-Bus/socket connection, notification daemon, process,
timer, poll, thread, filesystem access or desktop announcement. It is NOT a
real desktop notification, Linux Mint acceptance, screen-reader behaviour or
owner visual approval. The compiled bridge remains a separate workstream.
"""
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

from canopy_features.notifications.host_event_source import MAX_ITEMS
from canopy_features.notifications.host_snapshot_producer import (
    HostSnapshotProducer,
    SnapshotProducerError,
    compose,
)

__all__ = [
    "AVAILABLE",
    "CLOSED",
    "DUPLICATE",
    "INVALID_PAYLOAD",
    "INVALID_QUEUE_RECORD",
    "INVALID_SNAPSHOT",
    "MAX_CAPACITY",
    "NONE",
    "QUEUED",
    "REJECTED",
    "SOURCE_LOST",
    "UNAVAILABLE",
    "DeliveryOutcome",
    "LifecycleState",
    "NotificationDeliveryLifecycle",
    "NotificationLifecycleError",
]

# The queued projection can never outgrow the trusted source's own bound.
MAX_CAPACITY = MAX_ITEMS

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
NONE = "none"
CLOSED = "closed"
SOURCE_LOST = "source_lost"
INVALID_SNAPSHOT = "invalid_snapshot"

QUEUED = "queued"
DUPLICATE = "duplicate"
REJECTED = "rejected"

# Fixed refusal tokens. Never include a rejected payload, value or exception
# text: caller-supplied material must not reach a snapshot/refusal surface.
INVALID_PAYLOAD = "INVALID_NOTICE_PAYLOAD"
INVALID_QUEUE_RECORD = "INVALID_QUEUE_RECORD"


class NotificationLifecycleError(ValueError):
    """Invalid lifecycle argument or operation after explicit shutdown."""


@dataclass(frozen=True)
class DeliveryOutcome:
    """Fixed-token result of one host-only delivery attempt."""

    status: str
    id: str
    refusal: object = None

    def as_dict(self):
        return {"status": self.status, "id": self.id,
                "refusal": self.refusal}


@dataclass(frozen=True)
class LifecycleState:
    """Explicit availability and bounded delivery counters."""

    status: str
    reason: str
    refusal: object
    pending_count: int
    queued_count: int
    delivered_count: int
    duplicate_count: int
    dropped_count: int
    rejected_count: int

    def as_dict(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "refusal": self.refusal,
            "pending_count": self.pending_count,
            "queued_count": self.queued_count,
            "delivered_count": self.delivered_count,
            "duplicate_count": self.duplicate_count,
            "dropped_count": self.dropped_count,
            "rejected_count": self.rejected_count,
        }


class NotificationDeliveryLifecycle:
    """Host-owned, bounded delivery view over one trusted snapshot producer.

    ``deliver()`` publishes one real host event, then admits at most one new
    projected row. A payload the trusted producer cannot project, a rejected
    bus event, or a corrupt/multi-row snapshot is refused with a fixed token
    and leaves the queue untouched. Repeated ids (a replayed snapshot) are
    counted as duplicates and never enqueued a second time. When the queue is
    full the oldest pending row is evicted and the drop is counted, never
    silently lost. ``status()`` always reports an explicit available/unavailable
    state with a fixed reason; a closed or source-less lifecycle exposes zero
    rows and refuses all delivery.
    """

    def __init__(self, *, producer=None, capacity=MAX_CAPACITY):
        if type(capacity) is not int or not 1 <= capacity <= MAX_CAPACITY:
            raise NotificationLifecycleError("invalid delivery capacity")
        if producer is None:
            self._producer = HostSnapshotProducer()
            self._owns_producer = True
        elif type(producer) is HostSnapshotProducer and producer.connected():
            self._producer = producer
            self._owns_producer = False
        else:
            raise NotificationLifecycleError("trusted snapshot producer required")
        self._capacity = capacity
        self._pending = deque()
        self._seen = deque(maxlen=capacity)
        self._seen_set = set()
        self._counts = dict(queued=0, delivered=0, duplicates=0,
                            dropped=0, rejected=0)
        self._refusal = None
        self._closed = False

    def _ready(self):
        if self._closed:
            raise NotificationLifecycleError("notification lifecycle is closed")

    def _clear_pending(self):
        self._pending.clear()
        self._seen.clear()
        self._seen_set.clear()

    def _identifiers(self, records):
        """Best-effort ids; an unusable id becomes None and fails closed later."""
        result = []
        for record in records:
            try:
                identifier = self._row(record).get("id")
            except Exception:
                identifier = None
            result.append(identifier if type(identifier) is str else None)
        return tuple(result)

    def _view_ready(self):
        """True only while a live, trusted view exists; clears rows otherwise."""
        if (self._closed or self._refusal == INVALID_QUEUE_RECORD
                or not self._producer.connected()):
            self._clear_pending()
            return False
        return True

    def _refuse(self, token):
        self._counts["rejected"] += 1
        self._refusal = token
        return DeliveryOutcome(REJECTED, "", token)

    def _row(self, record):
        """Return a fresh dict for a trusted record, or fail closed."""
        if isinstance(record, Mapping):
            return dict(record)
        if hasattr(record, "as_dict"):
            return record.as_dict()
        raise NotificationLifecycleError("unsupported snapshot record")

    def _enqueue(self, record):
        """Validate and queue exactly one record; return a fixed status token."""
        try:
            row = self._row(record)
            validated = compose([row], max_records=1).records[0]
        except Exception:
            # A hostile record or a broken mapping can raise an arbitrary
            # built-in. Translate it to the module's fixed token; never echo
            # the rejected object's exception text or keep a partial row.
            return self._refuse(INVALID_QUEUE_RECORD).status
        identifier = validated.id
        if identifier in self._seen_set:
            self._counts["duplicates"] += 1
            return DUPLICATE
        if len(self._pending) >= self._capacity:
            self._pending.popleft()
            self._counts["dropped"] += 1
        self._pending.append(validated.as_dict())
        if len(self._seen) >= self._capacity:
            self._seen_set.discard(self._seen.popleft())
        self._seen.append(identifier)
        self._seen_set.add(identifier)
        self._counts["queued"] += 1
        return QUEUED

    def deliver(self, topic, payload):
        """Publish one trusted host event and admit its single projected row."""
        self._ready()
        try:
            before = frozenset(self._identifiers(
                self._producer.snapshot().records))
            self._producer.publish(topic, payload)
            after = self._producer.snapshot()
            ids = self._identifiers(after.records)
        except Exception:
            return self._refuse(INVALID_PAYLOAD)
        if self._producer.refusal is not None:
            return self._refuse(INVALID_PAYLOAD)
        duplicates = [identifier for identifier in ids
                      if identifier not in before
                      and identifier in self._seen_set]
        fresh = [(record, identifier)
                 for record, identifier in zip(after.records, ids)
                 if identifier not in self._seen_set
                 and identifier not in before]
        if duplicates:
            self._counts["duplicates"] += len(duplicates)
        if not fresh:
            if duplicates:
                self._refusal = None
                return DeliveryOutcome(DUPLICATE, duplicates[0])
            # The bus accepted the payload but no notice was projected: this
            # is a malformed payload for the notice contract, not a success.
            return self._refuse(INVALID_PAYLOAD)
        if len(fresh) != 1:
            return self._refuse(INVALID_QUEUE_RECORD)
        record, identifier = fresh[0]
        status = self._enqueue(record)
        if status == REJECTED:
            return DeliveryOutcome(REJECTED, "", INVALID_QUEUE_RECORD)
        self._refusal = None
        return DeliveryOutcome(status, identifier if status == QUEUED else "")

    def take(self):
        """Deliver the oldest pending row to trusted host code, or None.

        A closed or source-less view returns None instead of a row; it never
        raises a raw built-in or releases stale notice material.
        """
        if not self._view_ready() or not self._pending:
            return None
        row = self._pending.popleft()
        self._counts["delivered"] += 1
        return dict(row)

    def snapshot(self):
        """Fresh, newest-first immutable rows; empty when view is unavailable."""
        if not self._view_ready():
            return ()
        try:
            rows = [dict(row) for row in reversed(self._pending)]
            snapshot = compose(rows, max_records=self._capacity)
        except Exception:
            self._refusal = INVALID_QUEUE_RECORD
            return ()
        return tuple(row.as_dict() for row in snapshot.records)

    def status(self):
        """Explicit availability, reason, refusal and bounded counters."""
        if self._closed:
            state, reason = UNAVAILABLE, CLOSED
        elif not self._producer.connected():
            self._clear_pending()
            state, reason = UNAVAILABLE, SOURCE_LOST
        elif self._refusal == INVALID_QUEUE_RECORD:
            self._clear_pending()
            state, reason = UNAVAILABLE, INVALID_SNAPSHOT
        else:
            state, reason = AVAILABLE, NONE
        return LifecycleState(
            status=state, reason=reason, refusal=self._refusal,
            pending_count=len(self._pending),
            queued_count=self._counts["queued"],
            delivered_count=self._counts["delivered"],
            duplicate_count=self._counts["duplicates"],
            dropped_count=self._counts["dropped"],
            rejected_count=self._counts["rejected"])

    def close(self):
        """Fail-closed cleanup; an injected producer stays host-owned."""
        if self._closed:
            return
        if self._owns_producer:
            self._producer.close()
        self._clear_pending()
        self._refusal = None
        self._closed = True
