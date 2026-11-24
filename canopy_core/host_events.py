"""Versioned, host-owned, single-thread event primitive (not a Qt bridge).

Only callbacks explicitly supplied by trusted HOST code at construction can
subscribe. This module never loads Shell Packs/QML, creates a worker, polls,
opens sockets, grants permissions or observes real desktop/window events.
"""
from dataclasses import dataclass
import math
import re
from threading import get_ident
from types import MappingProxyType

PROTOCOL_VERSION = 1
CAPABILITIES_TOPIC = "capabilities.report"
TOPICS = frozenset({
    "app.catalog.changed", "window.state.changed", "session.state.changed",
    CAPABILITIES_TOPIC,
})
MAX_SUBSCRIBERS = 64
MAX_PAYLOAD_FIELDS = 8
MAX_VALUE_BYTES = 512
FORBIDDEN_FIELDS = frozenset({
    "__proto__", "prototype", "constructor", "password", "secret", "token",
    "credential", "cookie", "authorization", "private_key",
})
# FIELD names are lowercase ASCII with underscores. An exact deny-list alone
# lets credential-bearing compounds (user_password, access_token, api_key)
# through and publishes their values in dispatch records/reports. Strong words
# are refused inside any name; short aliases are refused as whole components,
# so ordinary names such as monkey_count or keyboard_layout stay accepted.
_CREDENTIAL_WORDS = frozenset({
    "token", "secret", "password", "passwd", "credential", "apikey",
    "privatekey", "accesstoken", "refreshtoken", "passphrase",
})
_CREDENTIAL_ALIASES = frozenset({
    "pw", "pwd", "pass", "key", "api", "auth", "cookie", "bearer",
    "private", "signature", "cert", "certificate", "accesskey",
})
FIELD = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")


class HostEventError(ValueError):
    """Invalid caller, callback, protocol version or event payload."""


class HostEventsBusy(RuntimeError):
    """Callbacks may not reenter or mutate the active dispatch."""


class HostEventsClosed(RuntimeError):
    """No new events or subscriptions after lifecycle shutdown."""


@dataclass(frozen=True)
class HostEvent:
    version: int
    topic: str
    sequence: int
    fields: tuple

    @property
    def payload(self):
        """New immutable mapping, so observers cannot mutate published data."""
        return MappingProxyType(dict(self.fields))


@dataclass(frozen=True)
class DispatchResult:
    event: HostEvent
    delivered: int
    callback_failures: int


def _valid_topic(topic):
    if type(topic) is not str or topic not in TOPICS:
        raise HostEventError("unsupported host event topic")


def _is_credential_field(folded_name):
    """True for credential-bearing field names, including compounds."""
    if any(word in folded_name for word in _CREDENTIAL_WORDS):
        return True
    return any(part in _CREDENTIAL_ALIASES
               for part in folded_name.split("_") if part)


def _encode_fields(payload):
    if type(payload) is not dict or len(payload) > MAX_PAYLOAD_FIELDS:
        raise HostEventError("invalid or oversized host event payload")
    result = []
    for key, value in payload.items():
        if type(key) is not str or not FIELD.fullmatch(key):
            raise HostEventError("unsupported host event field name")
        folded = key.casefold()
        if folded in FORBIDDEN_FIELDS or _is_credential_field(folded):
            raise HostEventError("unsupported host event field name")
        if type(value) is str:
            try:
                encoded = value.encode("utf-8", "strict")
            except UnicodeError as exc:
                raise HostEventError("invalid UTF-8 event value") from exc
            if len(encoded) > MAX_VALUE_BYTES:
                raise HostEventError("event string exceeds bound")
        elif type(value) is int:
            if abs(value) > 1_000_000_000_000:
                raise HostEventError("integer value exceeds bound")
        elif type(value) is float:
            if not math.isfinite(value) or abs(value) > 1_000_000_000_000:
                raise HostEventError("non-finite or unbounded float")
        elif type(value) not in (bool, type(None)):
            raise HostEventError("nested, executable or untrusted event value")
        result.append((key, value))
    return tuple(sorted(result))


class HostEvents:
    """Deterministic, bounded event bus owned by a single host event-loop thread.

    A trusted factory passes the exact allowlisted callbacks; plugins cannot
    register arbitrary code via event metadata or dynamically extend this
    allowlist. This does not sandbox those already trusted callbacks.
    """

    def __init__(self, trusted_callbacks, *, version=PROTOCOL_VERSION,
                 max_subscribers=MAX_SUBSCRIBERS):
        if type(version) is not int or version != PROTOCOL_VERSION:
            raise HostEventError("unsupported host event protocol version")
        if (type(max_subscribers) is not int or
                not 1 <= max_subscribers <= MAX_SUBSCRIBERS):
            raise HostEventError("invalid subscription bound")
        if type(trusted_callbacks) is not dict:
            raise HostEventError("explicit trusted host callback map required")
        if not set(trusted_callbacks).issubset(TOPICS):
            raise HostEventError("unknown trusted callback topic")
        vetted = {}
        for topic, callbacks in trusted_callbacks.items():
            _valid_topic(topic)
            if type(callbacks) not in (list, tuple) or len(callbacks) > MAX_SUBSCRIBERS:
                raise HostEventError("invalid trusted callback allowlist")
            if any(not callable(callback) for callback in callbacks):
                raise HostEventError("untrusted or noncallable callback entry")
            if any(a is b for i, a in enumerate(callbacks) for b in callbacks[i + 1:]):
                raise HostEventError("duplicate callback identity in host allowlist")
            vetted[topic] = tuple(callbacks)
        self._trusted = vetted
        self._subscriptions = {}
        self._next_token = 1
        self._sequence = 0
        self._max_subscribers = max_subscribers
        self._dispatching = False
        self._closed = False
        self._owner_thread = get_ident()

    def _ready(self):
        if get_ident() != self._owner_thread:
            raise HostEventError("host event bus used from a different thread")
        if self._closed:
            raise HostEventsClosed("host event bus is closed")
        if self._dispatching:
            raise HostEventsBusy("host callback cannot reenter event dispatcher")

    def subscribe(self, topic, callback):
        self._ready()
        _valid_topic(topic)
        if not any(callback is approved for approved in self._trusted.get(topic, ())):
            raise HostEventError("callback not allowlisted by host")
        if len(self._subscriptions) >= self._max_subscribers:
            raise HostEventError("subscription limit reached")
        if any(t == topic and f is callback for t, f in self._subscriptions.values()):
            raise HostEventError("duplicate active subscription")
        token = self._next_token
        self._next_token += 1
        self._subscriptions[token] = (topic, callback)
        return token

    def unsubscribe(self, token):
        self._ready()
        if type(token) is not int or token < 1:
            raise HostEventError("invalid subscription token")
        return self._subscriptions.pop(token, None) is not None

    def emit(self, topic, payload):
        self._ready()
        _valid_topic(topic)
        frozen_fields = _encode_fields(payload)
        self._sequence += 1
        event = HostEvent(PROTOCOL_VERSION, topic, self._sequence, frozen_fields)
        deliveries = failures = 0
        # Snapshot keeps the subscriber order deterministic. Mutation of the
        # bus from a callback raises HostEventsBusy and is counted as failure.
        self._dispatching = True
        try:
            for subscribed_topic, callback in tuple(self._subscriptions.values()):
                if subscribed_topic != topic:
                    continue
                try:
                    callback(event)
                    deliveries += 1
                except Exception:
                    # Do not disclose callback exception messages or secrets.
                    failures += 1
        finally:
            self._dispatching = False
        return DispatchResult(event, deliveries, failures)

    def close(self):
        if get_ident() != self._owner_thread:
            raise HostEventError("host event bus used from a different thread")
        if self._dispatching:
            raise HostEventsBusy("host callback cannot close dispatcher")
        if self._closed:
            return
        self._subscriptions.clear()
        self._trusted.clear()
        self._closed = True

    @property
    def subscription_count(self):
        return len(self._subscriptions)

    @property
    def closed(self):
        return self._closed
