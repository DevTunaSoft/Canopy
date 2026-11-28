"""Bounded notification-center badge derived only from trusted host events.

The badge is a pure projection of the existing ``HostSnapshotProducer``
snapshot. It accepts only an exact, connected trusted producer, validates the
whole snapshot through the existing ``compose`` contract, and exposes one
frozen count/label view. It draws no pixels, opens no notification center,
starts no daemon, and invents no row. A broken or disconnected source is
``unavailable`` with a fixed reason and a zero badge.
"""
from dataclasses import dataclass

from canopy_features.notifications.host_snapshot_producer import (
    MAX_ITEMS,
    HostSnapshotProducer,
    compose,
)

__all__ = [
    "AVAILABLE", "CLOSED", "INVALID_SNAPSHOT", "NONE", "SOURCE_LOST",
    "UNAVAILABLE", "MAX_BADGE", "BadgeState", "NotificationCenterBadge",
    "CenterBadgeError",
]

MAX_BADGE = 99

AVAILABLE = "available"
UNAVAILABLE = "unavailable"
NONE = "none"
CLOSED = "closed"
SOURCE_LOST = "source_lost"
INVALID_SNAPSHOT = "invalid_snapshot"


class CenterBadgeError(ValueError):
    """Invalid bound, untrusted producer or operation after shutdown."""


@dataclass(frozen=True)
class BadgeState:
    """Fixed-token badge view; the label is derived, never caller-supplied."""

    status: str
    reason: str
    refusal: object
    count: int
    label: str

    def as_dict(self):
        return {"status": self.status, "reason": self.reason,
                "refusal": self.refusal, "count": self.count,
                "label": self.label}


class NotificationCenterBadge:
    """Read-only badge view over one trusted snapshot producer.

    ``state()`` composes a fresh bounded snapshot and counts its records. It
    never stores caller rows, never mutates the producer and never reports a
    positive badge for an unavailable source. ``close()`` is explicit and
    idempotent; an injected producer stays host-owned.
    """

    def __init__(self, *, producer=None, max_badge=MAX_BADGE):
        if type(max_badge) is not int or not 1 <= max_badge <= MAX_BADGE:
            raise CenterBadgeError("invalid badge bound")
        if producer is None:
            self._producer = HostSnapshotProducer()
            self._owns_producer = True
        elif type(producer) is HostSnapshotProducer and producer.connected():
            self._producer = producer
            self._owns_producer = False
        else:
            raise CenterBadgeError("trusted snapshot producer required")
        self._max_badge = max_badge
        self._closed = False
        self._refusal = None

    def _count(self):
        """Compose the current trusted rows; fail closed on any doubt."""
        snapshot = self._producer.snapshot()
        try:
            rows = tuple(snapshot.records)
            records = tuple(row.as_dict() if hasattr(row, "as_dict")
                            else dict(row) for row in rows)
            validated = compose(list(records), max_records=MAX_ITEMS)
        except Exception:
            self._refusal = INVALID_SNAPSHOT
            return None
        if len(validated.records) != len(records):
            self._refusal = INVALID_SNAPSHOT
            return None
        return min(len(validated.records), self._max_badge)

    def state(self):
        """Pure bounded read; no I/O, no event emission, no source mutation."""
        if self._closed:
            return BadgeState(UNAVAILABLE, CLOSED, None, 0, "")
        if not self._producer.connected():
            self._refusal = None
            return BadgeState(UNAVAILABLE, SOURCE_LOST, None, 0, "")
        count = self._count()
        if count is None:
            return BadgeState(UNAVAILABLE, INVALID_SNAPSHOT,
                              self._refusal, 0, "")
        self._refusal = None
        label = "" if count == 0 else (
            "%d+" % self._max_badge if count >= self._max_badge else str(count))
        return BadgeState(AVAILABLE, NONE, None, count, label)

    def close(self):
        """Fail-closed cleanup; an injected producer is not closed."""
        if self._closed:
            return
        if self._owns_producer:
            self._producer.close()
        self._closed = True
        self._refusal = None
