"""Bounded, read-only notification host snapshot producer.

This module composes the records already projected by the trusted
``TrustedHostEventSource`` into one bounded, immutable snapshot in the wire
shape understood by the Classic notification centre::

    {"source": "host-events", "records": [{id, title, body, source, topic}, ...]}

Every row originates in a real ``HostEvent`` delivered by the trusted
in-process bus; this module never invents a notification, topic or payload.
It is pure and read-only on the snapshot path: no Qt object, D-Bus, socket,
daemon, process, timer, poll, filesystem read or environment access. With no
events, the snapshot has zero rows.

This is NOT a compiled Qt bridge, a live notification source, a screen-reader
announcement, Linux Mint acceptance or owner visual approval. Those remain
``NOT_RUN``. The compiled shell wiring is owned by a separate workstream.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import json
import unicodedata

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    HostEventError,
)

from canopy_features.notifications.host_event_source import (
    MAX_ITEMS,
    SOURCE,
    NoticeRecordError,
    TrustedHostEventSource,
)

__all__ = [
    "ALLOWED_TOPICS",
    "MAX_BODY_BYTES",
    "MAX_ID_BYTES",
    "MAX_JSON_BYTES",
    "MAX_RECORDS",
    "MAX_TITLE_BYTES",
    "RECORD_KEYS",
    "SOURCE",
    "HostSnapshot",
    "HostSnapshotProducer",
    "SnapshotProducerError",
    "compose",
]

MAX_RECORDS = MAX_ITEMS
MAX_JSON_BYTES = 65_536
MAX_ID_BYTES = 64
MAX_TITLE_BYTES = 120
MAX_BODY_BYTES = 280
ALLOWED_TOPICS = tuple(sorted(HOST_EVENT_TOPICS))
if len(ALLOWED_TOPICS) != 4 or PROTOCOL_VERSION != 2:  # pragma: no cover
    raise RuntimeError("host event contract changed; producer must be reviewed")

# Exact projected-record shape; no extra field is copied into the snapshot.
RECORD_KEYS = frozenset({"id", "title", "body", "source", "topic"})
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


class SnapshotProducerError(ValueError):
    """A supplied record or producer argument failed the snapshot contract."""


@dataclass(frozen=True)
class _Record:
    id: str
    title: str
    body: str
    source: str
    topic: str

    def as_dict(self):
        return {"id": self.id, "title": self.title, "body": self.body,
                "source": self.source, "topic": self.topic}


@dataclass(frozen=True)
class HostSnapshot:
    """Frozen wire-format snapshot; records are newest first."""

    source: str
    records: tuple

    def as_dict(self):
        return {"source": self.source,
                "records": [record.as_dict() for record in self.records]}

    def to_json_bytes(self):
        return json.dumps(self.as_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _bounded_text(value, limit, label, *, nonempty=False):
    # Reject wrong container types before encoding or category lookups; an
    # unhashable or non-str value must never leak a raw built-in exception.
    if type(value) is not str:
        raise SnapshotProducerError("invalid %s" % label)
    if nonempty and not value:
        raise SnapshotProducerError("empty %s" % label)
    encoded_len = len(value.encode("utf-8"))
    if encoded_len < 1 or encoded_len > limit:
        raise SnapshotProducerError("unbounded %s" % label)
    for char in value:
        if unicodedata.category(char) in _UNSAFE_CATEGORIES:
            raise SnapshotProducerError("unsafe %s" % label)
    return value


def _validate_record(record):
    if not isinstance(record, Mapping):
        raise SnapshotProducerError("record has an unexpected key set")
    try:
        keys = frozenset(record)
    except TypeError as exc:
        # A hostile Mapping can iterate an unhashable key. That is a rejected
        # record, never a raw built-in exception from the public compose().
        raise SnapshotProducerError("record has an unexpected key set") from exc
    if keys != RECORD_KEYS:
        raise SnapshotProducerError("record has an unexpected key set")
    topic = record["topic"]
    if type(topic) is not str or topic not in ALLOWED_TOPICS:
        raise SnapshotProducerError("unsupported host event topic")
    if record["source"] != SOURCE:
        raise SnapshotProducerError("unsupported snapshot source")
    return _Record(
        id=_bounded_text(record["id"], MAX_ID_BYTES, "record id", nonempty=True),
        title=_bounded_text(record["title"], MAX_TITLE_BYTES, "record title"),
        body=_bounded_text(record["body"], MAX_BODY_BYTES, "record body"),
        source=SOURCE,
        topic=topic,
    )


def compose(records, *, max_records=MAX_RECORDS, max_bytes=MAX_JSON_BYTES):
    """Compose a frozen snapshot from trusted source records.

    Whole-input validation: any bad record rejects the entire input with
    ``SnapshotProducerError``; no partial snapshot is returned. Field and
    collection bounds match the Classic notification centre's record guard.
    """
    if type(max_records) is not int or not 1 <= max_records <= MAX_RECORDS:
        raise SnapshotProducerError("invalid snapshot capacity")
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_JSON_BYTES:
        raise SnapshotProducerError("invalid snapshot byte bound")
    if type(records) not in (list, tuple) or len(records) > max_records:
        raise SnapshotProducerError("invalid or oversized record collection")
    projected = []
    seen_ids = set()
    for record in records:
        validated = _validate_record(record)
        if validated.id in seen_ids:
            raise SnapshotProducerError("duplicate snapshot record id")
        seen_ids.add(validated.id)
        projected.append(validated)
    snapshot = HostSnapshot(SOURCE, tuple(projected))
    if len(snapshot.to_json_bytes()) > max_bytes:
        raise SnapshotProducerError("snapshot exceeds byte bound")
    return snapshot


class HostSnapshotProducer:
    """Host-owned read-only view over one trusted host-event source."""

    def __init__(self, *, source=None, max_records=MAX_RECORDS,
                 max_bytes=MAX_JSON_BYTES):
        if type(max_records) is not int or not 1 <= max_records <= MAX_RECORDS:
            raise SnapshotProducerError("invalid snapshot capacity")
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_JSON_BYTES:
            raise SnapshotProducerError("invalid snapshot byte bound")
        if source is None:
            self._source = TrustedHostEventSource()
            self._owns_source = True
        elif type(source) is TrustedHostEventSource and source.connected():
            self._source = source
            self._owns_source = False
        else:
            raise SnapshotProducerError("trusted host event source required")
        self._max_records = max_records
        self._max_bytes = max_bytes
        self._refusal = None
        self._closed = False

    def publish(self, topic, payload):
        """Explicit host-only injection of a real event into the trusted bus."""
        if self._closed:
            raise SnapshotProducerError("snapshot producer is closed")
        try:
            return self._source.emit(topic, payload)
        except (HostEventError, NoticeRecordError, ValueError, TypeError,
                UnicodeError, RuntimeError) as exc:
            # Translate bus refusals to this module's domain error; never
            # echo the rejected payload or leave a partial row behind.
            raise SnapshotProducerError("host event refused") from exc

    def connected(self):
        return not self._closed and self._source.connected()

    def source(self):
        return SOURCE

    def allowedTopics(self):
        return list(ALLOWED_TOPICS)

    def snapshot(self):
        if not self.connected():
            self._refusal = None
            return HostSnapshot(SOURCE, ())
        try:
            snapshot = compose(self._source.snapshot(),
                               max_records=self._max_records,
                               max_bytes=self._max_bytes)
        except (SnapshotProducerError, ValueError, TypeError,
                UnicodeError, AttributeError):
            # A rejected whole input produces empty rows; a fixed token is
            # recorded instead of echoing hostile record content.
            self._refusal = "INVALID_SNAPSHOT_RECORD"
            return HostSnapshot(SOURCE, ())
        self._refusal = None
        return snapshot

    @property
    def refusal(self):
        return self._refusal

    def as_dict(self):
        return self.snapshot().as_dict()

    def to_json_bytes(self):
        return self.snapshot().to_json_bytes()

    def close(self):
        if self._closed:
            return
        if self._owns_source:
            self._source.close()
        self._closed = True
