"""Bounded trusted host-event source for the Classic notification centre.

This module is a *pure in-process adapter*. It consumes immutable ``HostEvent``
objects emitted by the existing ``canopy_core.host_events.HostEvents`` bus and
projects them into the bounded record shape that
``prototype/classic/NotificationCenter.qml`` accepts. It creates no Qt object,
notification daemon, socket, process, timer, thread, D-Bus session or privileged
action; it does not call the compositor and does not observe OS notifications.

Trust boundary: only code holding the returned source object can emit into its
private bus. QML never constructs an event, chooses a payload field or changes
the topic list; it only reads ``connected()``, ``source()``, ``allowedTopics()``
and ``snapshot()`` from a host-injected controller. With no injected controller
the panel stays fail closed and shows its no-source disclosure.
"""
from collections import deque
from dataclasses import dataclass
import unicodedata

from canopy_core.host_events import (
    PROTOCOL_VERSION,
    TOPICS as HOST_EVENT_TOPICS,
    HostEvent,
    HostEvents,
    HostEventError,
)

__all__ = [
    "SOURCE",
    "MAX_ITEMS",
    "ALLOWED_TOPICS",
    "NoticeRecordError",
    "TrustedHostEventSource",
]

SOURCE = "host-events"
MAX_ITEMS = 12
ALLOWED_TOPICS = tuple(sorted(HOST_EVENT_TOPICS))
if len(ALLOWED_TOPICS) != 4 or PROTOCOL_VERSION != 2:  # pragma: no cover
    raise RuntimeError("host event contract changed; adapter must be reviewed")

MAX_ID_BYTES = 64
MAX_TITLE_BYTES = 120
MAX_BODY_BYTES = 280
MAX_VALUE_BYTES = 200

# Only field names already used by the documented host-event contract are
# projected. No field is added to that contract and no value is invented when
# a field is absent.
_TOPIC_TITLES = {
    "app.catalog.changed": "Application catalogue updated",
    "window.state.changed": "Window state updated",
    "session.state.changed": "Session state updated",
    "capabilities.report": "Host capability report",
}
_TOPIC_FIELDS = {
    "app.catalog.changed": ("item_count", "available"),
    "window.state.changed": ("window_count", "state"),
    "session.state.changed": ("state",),
    "capabilities.report": ("status", "component_count", "needs_recovery",
                           "has_active_pack"),
}
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


class NoticeRecordError(ValueError):
    """An event could not be projected into a safe bounded notice."""


@dataclass(frozen=True)
class _Notice:
    id: str
    title: str
    body: str
    source: str
    topic: str

    def as_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "source": self.source,
            "topic": self.topic,
        }


def _bounded_text(value, limit, label):
    if type(value) is not str or not value or len(value.encode("utf-8")) > limit:
        raise NoticeRecordError("invalid %s" % label)
    for char in value:
        if unicodedata.category(char) in _UNSAFE_CATEGORIES:
            raise NoticeRecordError("unsafe %s" % label)
    return value


def _render_scalar(value):
    if type(value) is bool:
        return "true" if value else "false"
    if value is None:
        return "none"
    if type(value) in (int, float):
        return str(value)
    if type(value) is str:
        return _bounded_text(value, MAX_VALUE_BYTES, "event value")
    raise NoticeRecordError("unsupported event value")


def _project(event):
    """Project one real HostEvent, or fail closed without emitting a row."""
    if type(event) is not HostEvent:
        raise NoticeRecordError("only real HostEvent instances are accepted")
    if event.version != PROTOCOL_VERSION or type(event.sequence) is not int \
            or event.sequence < 1:
        raise NoticeRecordError("invalid host event envelope")
    if type(event.topic) is not str or event.topic not in _TOPIC_TITLES:
        raise NoticeRecordError("unsupported host event topic")
    payload = event.payload
    parts = []
    for field in _TOPIC_FIELDS[event.topic]:
        if field not in payload:
            continue
        rendered = "%s=%s" % (field, _render_scalar(payload[field]))
        if len(rendered.encode("utf-8")) > MAX_VALUE_BYTES:
            raise NoticeRecordError("event value exceeds notice bound")
        parts.append(rendered)
    if not parts:
        raise NoticeRecordError("event carries no projected notice field")
    body = "; ".join(parts)
    _bounded_text(body, MAX_BODY_BYTES, "notice body")
    identifier = "%s:%s:%d" % (SOURCE, event.topic, event.sequence)
    _bounded_text(identifier, MAX_ID_BYTES, "notice id")
    return _Notice(id=identifier,
                   title=_TOPIC_TITLES[event.topic],
                   body=body,
                   source=SOURCE,
                   topic=event.topic)


class TrustedHostEventSource:
    """Host-owned adapter exposing real host events to the Classic centre.

    The adapter owns one ``HostEvents`` bus with its own callback explicitly
    allowlisted at construction. Every notice in ``snapshot()`` comes from a
    delivered ``HostEvent``. Capacity is fixed at 12 records; overflow drops
    the oldest record, never invents one.
    """

    def __init__(self, *, max_items=MAX_ITEMS):
        if type(max_items) is not int or not 1 <= max_items <= MAX_ITEMS:
            raise NoticeRecordError("invalid notice capacity")
        self._max_items = max_items
        self._records = deque(maxlen=max_items)
        self._dropped = 0
        self._closed = False
        self._callback = self._on_event
        self._bus = HostEvents(
            {topic: [self._callback] for topic in ALLOWED_TOPICS})
        self._tokens = tuple(self._bus.subscribe(topic, self._callback)
                             for topic in ALLOWED_TOPICS)

    def _ready(self):
        if self._closed or self._bus.closed:
            raise NoticeRecordError("host event source is closed")

    def _on_event(self, event):
        try:
            notice = _project(event)
        except (NoticeRecordError, HostEventError, UnicodeError):
            return
        if len(self._records) == self._max_items:
            self._dropped += 1
        self._records.append(notice)

    def emit(self, topic, payload):
        """Emit one real host event; only trusted host code may call this."""
        self._ready()
        return self._bus.emit(topic, payload)

    def connected(self):
        """True only while the trusted bus and all subscriptions are live."""
        if self._closed or self._bus.closed:
            return False
        return self._bus.subscription_count == len(ALLOWED_TOPICS)

    def source(self):
        return SOURCE

    def allowedTopics(self):
        return list(ALLOWED_TOPICS)

    def snapshot(self):
        """Fresh, bounded records; newest first. No records when disconnected."""
        if not self.connected():
            return []
        return [notice.as_dict() for notice in reversed(self._records)]

    @property
    def dropped_count(self):
        return self._dropped

    def close(self):
        if self._closed:
            return
        for token in self._tokens:
            if not self._bus.closed:
                self._bus.unsubscribe(token)
        self._bus.close()
        self._records.clear()
        self._closed = True
