"""Bounded, read-only virtual desktop switch request records at the host-event boundary.

This module is a pure in-process adapter over the existing
``canopy_core.host_events.HostEvents`` bus. A trusted host caller emits one of
the four already-documented v2 topics and may then serialize an explicit
switch *request* against the real ``HostEvent`` that was just delivered. The
result is an immutable record for inspection only.

It does not switch a workspace, activate a window, manage a compositor, bind a
key, poll, sleep, spawn a thread or process, open a socket, read a file or
touch Qt. It adds no host-event topic, field or payload shape and never
constructs an event itself: without a live event emitted by its own bus, a
request is refused. ``wm_requests`` is always zero and ``polling`` always
false; acceptance and observation are never claimed.

This is deliberately not the PE-086 workspace decision contract (native versus
graceful fallback from inventory and negotiation), the PE-067 window-reference
guard, PE-102 window activation, or the dock running-indicator source. It only
records a caller-supplied intent and the real host event that authorized it.
"""
from collections import deque
from dataclasses import dataclass
from types import MappingProxyType
import unicodedata

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    HostEvent,
    HostEvents,
)

SOURCE = "host-events"
SCHEMA = 1
MAX_REQUESTS = 16
MAX_TARGET_BYTES = 64
MAX_LABEL_BYTES = 120
MAX_WORKSPACES = 64

KIND_IDENTIFIER = "identifier"
KIND_INDEX = "index"
KIND_DIRECTION = "direction"
KINDS = (KIND_IDENTIFIER, KIND_INDEX, KIND_DIRECTION)
DIRECTIONS = ("next", "previous", "first", "last")

STATUS_RECORDED = "RECORDED"
STATUS_IGNORED = "IGNORED"
REASON_RECORDED = "RECORDED"
REASON_DUPLICATE = "DUPLICATE_REQUEST"

ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"
WM_REQUESTS = 0
POLLING_ENABLED = False

ALLOWED_TOPICS = tuple(sorted(HOST_EVENT_TOPICS))
if len(ALLOWED_TOPICS) != 4 or PROTOCOL_VERSION != 2:  # pragma: no cover
    raise RuntimeError("host event contract changed; adapter must be reviewed")

# A bounded string is not automatically a displayable, round-trippable name.
_UNSAFE_TEXT_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


class SwitchRequestError(ValueError):
    """Invalid trusted input, missing live event, or a closed recorder."""


@dataclass(frozen=True)
class VirtualDesktopSwitchRequest:
    """One immutable, inspectable switch request; no callback or side effect."""

    schema: int
    status: str
    reason: str
    source: str
    topic: str
    sequence: int
    kind: str
    target: object
    label: str
    acceptance: str
    observation: str
    wm_requests: int
    polling: bool

    def to_dict(self):
        """Fresh read-only view with a fixed, stable key order."""
        return MappingProxyType({
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "source": self.source,
            "topic": self.topic,
            "sequence": self.sequence,
            "kind": self.kind,
            "target": self.target,
            "label": self.label,
            "acceptance": self.acceptance,
            "observation": self.observation,
            "wm_requests": self.wm_requests,
            "polling": self.polling,
        })


def _safe_text(value, limit, field, *, allow_empty=False):
    if type(value) is not str:
        raise SwitchRequestError("invalid " + field)
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        # Unpaired surrogates must fail closed with the domain error.
        raise SwitchRequestError("unencodable " + field) from exc
    if len(encoded) > limit:
        raise SwitchRequestError("oversized " + field)
    if not allow_empty and not value.strip():
        raise SwitchRequestError(field + " must not be blank")
    for char in value:
        if unicodedata.category(char) in _UNSAFE_TEXT_CATEGORIES:
            raise SwitchRequestError("unsafe " + field)
    return value


def _kind(value):
    if type(value) is not str or value not in KINDS:
        raise SwitchRequestError("unknown request kind")
    return value


def _identifier(value):
    return _safe_text(value, MAX_TARGET_BYTES, "workspace identifier")


def _index(value):
    # Strict type gate: bool aliases int and would otherwise record True as 1.
    if type(value) is not int or not 1 <= value <= MAX_WORKSPACES:
        raise SwitchRequestError("workspace index is out of range")
    return value


def _direction(value):
    if type(value) is not str or value not in DIRECTIONS:
        raise SwitchRequestError("unknown switch direction")
    return value


def _target(kind, value):
    if kind == KIND_IDENTIFIER:
        return _identifier(value)
    if kind == KIND_INDEX:
        return _index(value)
    return _direction(value)


class VirtualDesktopSwitchRecorder:
    """Host-owned bus plus a bounded, read-only request record store.

    Every request must name a real ``HostEvent`` emitted by this instance and
    still within the bounded live-event window. Duplicate requests are counted
    and ignored. Capacity overflow drops the oldest record, never invents one.
    """

    def __init__(self, *, max_requests=MAX_REQUESTS):
        if (type(max_requests) is not int
                or not 1 <= max_requests <= MAX_REQUESTS):
            raise SwitchRequestError("invalid request capacity")
        self._limit = max_requests
        self._closed = False
        self._callback = self._on_event
        self._bus = HostEvents(
            {topic: [self._callback] for topic in ALLOWED_TOPICS})
        self._tokens = tuple(self._bus.subscribe(topic, self._callback)
                             for topic in ALLOWED_TOPICS)
        self._events = deque(maxlen=max_requests)
        self._event_keys = set()
        self._requests = deque(maxlen=max_requests)
        self._request_keys = set()
        self._ignored = 0

    def _ready(self):
        if self._closed or self._bus.closed:
            raise SwitchRequestError("switch request recorder is closed")

    def _on_event(self, event):
        # Callback exceptions are swallowed by the bus; fail closed silently.
        if type(event) is not HostEvent or event.version != PROTOCOL_VERSION:
            return
        if type(event.sequence) is not int or event.sequence < 1:
            return
        if type(event.topic) is not str or event.topic not in ALLOWED_TOPICS:
            return
        key = (event.topic, event.sequence)
        if key in self._event_keys:
            return
        if len(self._events) == self._limit:
            old = self._events.popleft()
            self._event_keys.discard((old.topic, old.sequence))
        self._events.append(event)
        self._event_keys.add(key)

    def emit(self, topic, payload):
        """Emit one existing host event; only trusted host code may call this."""
        self._ready()
        return self._bus.emit(topic, payload)

    def _authorize(self, event):
        if type(event) is not HostEvent:
            raise SwitchRequestError("a real host event is required")
        if event.version != PROTOCOL_VERSION or type(event.sequence) is not int \
                or event.sequence < 1 or event.topic not in ALLOWED_TOPICS:
            raise SwitchRequestError("invalid host event envelope")
        if (event.topic, event.sequence) not in self._event_keys:
            raise SwitchRequestError("host event is not live on this recorder")
        if not any(live is event for live in self._events):
            raise SwitchRequestError("host event is not live on this recorder")

    @staticmethod
    def _record(status, reason, event, kind, target, label):
        return VirtualDesktopSwitchRequest(
            schema=SCHEMA,
            status=status,
            reason=reason,
            source=SOURCE,
            topic=event.topic,
            sequence=event.sequence,
            kind=kind,
            target=target,
            label=label,
            acceptance=ACCEPTANCE_NOT_ESTABLISHED,
            observation=OBSERVATION_NOT_PERFORMED,
            wm_requests=WM_REQUESTS,
            polling=POLLING_ENABLED,
        )

    def request(self, event, *, kind, target, label=None):
        """Serialize a read-only switch request against a live host event."""
        self._ready()
        self._authorize(event)
        kind = _kind(kind)
        target = _target(kind, target)
        label = "" if label is None else _safe_text(
            label, MAX_LABEL_BYTES, "request label", allow_empty=True)
        key = (event.topic, event.sequence, kind, target)
        if key in self._request_keys:
            self._ignored += 1
            return self._record(STATUS_IGNORED, REASON_DUPLICATE, event,
                                kind, target, label)
        if len(self._requests) == self._limit:
            old = self._requests.popleft()
            self._request_keys.discard((old.topic, old.sequence,
                                        old.kind, old.target))
        record = self._record(STATUS_RECORDED, REASON_RECORDED, event,
                              kind, target, label)
        self._requests.append(record)
        self._request_keys.add(key)
        return record

    def connected(self):
        """True only while the trusted bus and all subscriptions are live."""
        if self._closed or self._bus.closed:
            return False
        return self._bus.subscription_count == len(ALLOWED_TOPICS)

    def allowedTopics(self):
        return list(ALLOWED_TOPICS)

    def snapshot(self) -> tuple:
        """Fresh, bounded, newest-first read-only records; empty when closed."""
        if not self.connected():
            return ()
        return tuple(record.to_dict() for record in reversed(self._requests))

    @property
    def ignored_count(self):
        return self._ignored

    def close(self):
        """Drop every live event and request; later requests fail closed."""
        if self._closed:
            return
        for token in self._tokens:
            if not self._bus.closed:
                self._bus.unsubscribe(token)
        self._bus.close()
        self._events.clear()
        self._event_keys.clear()
        self._requests.clear()
        self._request_keys.clear()
        self._closed = True


__all__ = [
    "SOURCE", "SCHEMA", "MAX_REQUESTS", "MAX_TARGET_BYTES", "MAX_LABEL_BYTES",
    "MAX_WORKSPACES", "KIND_IDENTIFIER", "KIND_INDEX", "KIND_DIRECTION",
    "KINDS", "DIRECTIONS", "STATUS_RECORDED", "STATUS_IGNORED",
    "REASON_RECORDED", "REASON_DUPLICATE", "ACCEPTANCE_NOT_ESTABLISHED",
    "OBSERVATION_NOT_PERFORMED", "WM_REQUESTS", "POLLING_ENABLED",
    "ALLOWED_TOPICS", "SwitchRequestError", "VirtualDesktopSwitchRequest",
    "VirtualDesktopSwitchRecorder",
]
