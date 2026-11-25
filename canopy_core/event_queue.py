"""Bounded, versioned, in-process shell event queue.

Trusted shell-core producers append versioned events; trusted consumers drain
them in deterministic FIFO order. Storage is a fixed-capacity deque, so it
never grows past the configured bound. This module starts no timer, polling
loop, worker thread or child process; it opens no socket and reads no file.

This is an in-memory data structure only. It does not observe real desktop
events, load Shell Packs, authenticate callers or sandbox already-trusted
shell code. Overflow and invalid events are handled explicitly by policy.
"""
from collections import deque
from dataclasses import dataclass
import math
import re
from types import MappingProxyType

PROTOCOL_VERSION = 1
TOPICS = frozenset({
    "app.catalog.changed", "window.state.changed", "session.state.changed",
})
OVERFLOW_POLICIES = frozenset({"reject", "drop_oldest", "drop_newest"})
DEFAULT_OVERFLOW = "reject"
DEFAULT_CAPACITY = 64
MAX_CAPACITY = 1024
MAX_SEQUENCE = 1_000_000_000_000
MAX_PAYLOAD_FIELDS = 8
MAX_VALUE_BYTES = 512
FORBIDDEN_FIELDS = frozenset({
    "__proto__", "prototype", "constructor", "password", "secret", "token",
    "credential", "cookie", "authorization", "private_key",
})
FIELD = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")


class QueueError(ValueError):
    """Invalid event, topic, payload, version, policy or configuration."""


class QueueOverflow(RuntimeError):
    """Queue is full and overflow policy is 'reject'."""


class QueueClosed(RuntimeError):
    """Queue is closed; publishing or draining is no longer allowed."""


@dataclass(frozen=True)
class ShellEvent:
    """Immutable queued event with a read-only payload view."""

    version: int
    topic: str
    sequence: int
    fields: tuple

    @property
    def payload(self):
        return MappingProxyType(dict(self.fields))


@dataclass(frozen=True)
class PublishResult:
    """Outcome of one publish: the stamped event, whether it queued and evictions."""

    event: ShellEvent
    queued: bool
    evicted: int


def _valid_topic(topic):
    if type(topic) is not str or topic not in TOPICS:
        raise QueueError("unsupported shell event topic")


def _encode_fields(payload):
    """Validate and freeze a payload into a sorted tuple of scalar pairs."""
    if type(payload) is not dict or len(payload) > MAX_PAYLOAD_FIELDS:
        raise QueueError("invalid or oversized shell event payload")
    result = []
    for key, value in payload.items():
        if (type(key) is not str or not FIELD.fullmatch(key)
                or key.casefold() in FORBIDDEN_FIELDS):
            raise QueueError("unsupported shell event field name")
        if type(value) is str:
            try:
                encoded = value.encode("utf-8", "strict")
            except UnicodeError as exc:
                raise QueueError("invalid UTF-8 event value") from exc
            if len(encoded) > MAX_VALUE_BYTES:
                raise QueueError("event string exceeds bound")
        elif type(value) is int:
            if abs(value) > MAX_SEQUENCE:
                raise QueueError("integer value exceeds bound")
        elif type(value) is float:
            if not math.isfinite(value) or abs(value) > MAX_SEQUENCE:
                raise QueueError("non-finite or unbounded float")
        elif type(value) not in (bool, type(None)):
            raise QueueError("nested, executable or untrusted event value")
        result.append((key, value))
    return tuple(sorted(result))


def validate_event(event):
    """Validate a pre-built event and return its normalized field tuple."""
    if not isinstance(event, ShellEvent):
        raise QueueError("not a ShellEvent")
    if type(event.version) is not int or event.version != PROTOCOL_VERSION:
        raise QueueError("unsupported event protocol version")
    _valid_topic(event.topic)
    if type(event.sequence) is not int or not 1 <= event.sequence <= MAX_SEQUENCE:
        raise QueueError("invalid event sequence")
    return _encode_fields(dict(event.fields))


class ShellEventQueue:
    """Deterministic, bounded FIFO queue owned by trusted shell-core code."""

    def __init__(self, *, capacity=DEFAULT_CAPACITY, overflow=DEFAULT_OVERFLOW,
                 version=PROTOCOL_VERSION):
        if type(version) is not int or version != PROTOCOL_VERSION:
            raise QueueError("unsupported shell event protocol version")
        if type(capacity) is not int or not 1 <= capacity <= MAX_CAPACITY:
            raise QueueError("invalid queue capacity")
        if type(overflow) is not str or overflow not in OVERFLOW_POLICIES:
            raise QueueError("unsupported overflow policy")
        self._capacity = capacity
        self._overflow = overflow
        self._events = deque()
        self._sequence = 0
        self._dropped = 0
        self._closed = False

    def _ready(self):
        if self._closed:
            raise QueueClosed("shell event queue is closed")

    def _enqueue(self, topic, fields):
        self._ready()
        full = len(self._events) >= self._capacity
        if full and self._overflow == "reject":
            raise QueueOverflow("shell event queue is full")
        if full and self._overflow == "drop_newest":
            self._dropped += 1
            dropped = ShellEvent(PROTOCOL_VERSION, topic, 0, fields)
            return PublishResult(dropped, False, 0)
        evicted = 0
        if full:
            self._events.popleft()
            evicted = 1
            self._dropped += 1
        self._sequence += 1
        event = ShellEvent(PROTOCOL_VERSION, topic, self._sequence, fields)
        self._events.append(event)
        return PublishResult(event, True, evicted)

    def publish(self, topic, payload):
        """Validate a payload, stamp a sequence and enqueue under the policy."""
        self._ready()
        _valid_topic(topic)
        return self._enqueue(topic, _encode_fields(payload))

    def publish_event(self, event):
        """Validate a pre-built versioned event, then re-stamp its sequence."""
        self._ready()
        fields = validate_event(event)
        return self._enqueue(event.topic, fields)

    def drain(self, limit=None):
        """Remove and return up to 'limit' events in FIFO order."""
        self._ready()
        if limit is None:
            count = len(self._events)
        else:
            if type(limit) is not int or limit < 0:
                raise QueueError("invalid drain limit")
            count = min(limit, len(self._events))
        result = []
        for _ in range(count):
            result.append(self._events.popleft())
        return tuple(result)

    def pop(self):
        """Remove and return the oldest event, or None when empty."""
        self._ready()
        return self._events.popleft() if self._events else None

    def peek(self):
        """Return the oldest event without removing it, or None when empty."""
        self._ready()
        return self._events[0] if self._events else None

    def clear(self):
        """Drop all queued events; dropped counter and sequence are unchanged."""
        self._ready()
        self._events.clear()

    def close(self):
        """Release queued events and make publish/drain permanently invalid."""
        if self._closed:
            return
        self._events.clear()
        self._closed = True

    @property
    def size(self):
        return len(self._events)

    @property
    def capacity(self):
        return self._capacity

    @property
    def overflow(self):
        return self._overflow

    @property
    def dropped(self):
        return self._dropped

    @property
    def sequence(self):
        return self._sequence

    @property
    def is_empty(self):
        return not self._events

    @property
    def closed(self):
        return self._closed
