"""Versioned, host-owned, single-thread event primitive (not a Qt bridge).

Only callbacks explicitly supplied by trusted HOST code at construction can
subscribe. This module never loads Shell Packs/QML, creates a worker, polls,
opens sockets, grants permissions or observes real desktop/window events.

The dispatch boundary carries a lazy, bounded limiter adapted from the
reviewed Classic host-event bridge: 16 tokens, one refill per second from a
monotonic clock sampled only inside ``emit()``, a fixed 16-entry outcome ring
and a four-entry catalog fingerprint ring. There is no process-lifetime event
freeze. An exhausted bucket does **not** drop a legitimate event: trusted
callbacks still commit authoritative state and the outcome honestly says
``*-deferred``. A fresh catalog refresh is emitted before its token is
charged, or carried by one boolean latch to the next real dispatch that
observes a token. The latch is one bit, never a queue, timer or background
wakeup; no new topic, payload field or transport is introduced.
"""
from collections import deque
from dataclasses import dataclass
import math
import re
from threading import get_ident
from time import monotonic
from types import MappingProxyType

PROTOCOL_VERSION = 2
# v2 keeps the three v1 topics and adds one explicit host-request topic.
CAPABILITIES_TOPIC = "capabilities.report"
TOPICS = frozenset({
    "app.catalog.changed", "window.state.changed", "session.state.changed",
    CAPABILITIES_TOPIC,
})
# Lazy limiter bounds from the reviewed Classic bridge. These are structural
# constants: callers cannot grow the bucket, history, ring or clock rate.
BUCKET_CAPACITY = 16
BUCKET_REFILL_MS = 1000
OUTCOME_HISTORY_MAX = 16
REFRESH_FINGERPRINT_MAX = 4
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
    # Fixed outcome token only. "*-deferred" means the bucket was empty after
    # the authoritative state had already been committed, never that the event
    # was dropped. No caller text is carried here.
    outcome: str = ""


def _default_clock():
    """Monotonic milliseconds; the only clock sample sites are emit/refill."""
    return monotonic() * 1000.0


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
                 max_subscribers=MAX_SUBSCRIBERS, clock=None):
        if type(version) is not int or version != PROTOCOL_VERSION:
            raise HostEventError("unsupported host event protocol version")
        if (type(max_subscribers) is not int or
                not 1 <= max_subscribers <= MAX_SUBSCRIBERS):
            raise HostEventError("invalid subscription bound")
        if clock is not None and not callable(clock):
            raise HostEventError("host event clock must be callable")
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
        self._clock = clock if clock is not None else _default_clock
        # All limiter state is fixed-size and host-owned. Only emit() samples
        # the clock; no timer, polling loop, thread or queue exists.
        # The injected clock is numeric milliseconds; float() keeps the
        # arithmetic well-defined for int and monotonic-derived clocks alike.
        self._tokens = BUCKET_CAPACITY
        self._last_refill = self._now()
        self._outcomes = deque(maxlen=OUTCOME_HISTORY_MAX)
        self._fingerprints = deque(maxlen=REFRESH_FINGERPRINT_MAX)
        self._refresh_pending = False
        self._refresh_requests = 0
        self._dispatch_count = 0
        self._accepted_count = 0
        self._rejected_count = 0
        self._last_outcome = "unset"

    def _now(self):
        """Sample the injected monotonic clock in milliseconds, validated."""
        value = self._clock()
        if (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value)):
            return float(value)
        raise HostEventError("invalid host event clock value")

    def _record(self, outcome):
        """Append one fixed token to the 16-entry outcome ring."""
        self._last_outcome = outcome
        self._outcomes.append(outcome)
        if outcome == "rejected":
            self._rejected_count += 1
        else:
            self._accepted_count += 1

    def _refill(self):
        """Lazy token refill; a backwards clock never grants credit."""
        current = self._now()
        if current <= self._last_refill:
            return
        elapsed = current - self._last_refill
        steps = int(elapsed // BUCKET_REFILL_MS)
        if steps <= 0:
            return
        self._tokens = min(BUCKET_CAPACITY,
                           self._tokens + min(steps, BUCKET_CAPACITY))
        self._last_refill = current - (elapsed % BUCKET_REFILL_MS)

    def _take(self):
        self._refill()
        if self._tokens == 0:
            return False
        self._tokens -= 1
        return True

    def _flush_pending(self):
        """Carry one latched refresh to the next real event with a token.

        Reconciliation is exempt from a new token charge: its producer work
        already happened on the event that latched it. The latch is cleared
        once and never retried in the background.
        """
        if self._refresh_pending and self._tokens > 0:
            self._refresh_pending = False
            self._refresh_requests += 1

    def _commit_outcome(self, topic, fields):
        if topic == "app.catalog.changed":
            fingerprint = (int(self._last_refill // BUCKET_REFILL_MS), fields)
            if fingerprint in self._fingerprints:
                return "catalog-refresh-coalesced"
            self._fingerprints.append(fingerprint)
            if self._take():
                # Authoritative refresh precedes the token charge. A fresh
                # catalog state is never lost to an exhausted bucket.
                self._refresh_requests += 1
                return "catalog-refresh-requested"
            self._refresh_pending = True
            return "catalog-refresh-pending"
        applied = {
            "capabilities.report": "quick-controls-applied",
            "session.state.changed": "session-observed",
            "window.state.changed": "window-applied",
        }[topic]
        return applied + ("-deferred" if not self._take() else "")

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
        try:
            _valid_topic(topic)
            frozen_fields = _encode_fields(payload)
        except HostEventError:
            # Fail closed and record one fixed token; invalid traffic spends
            # no bucket token, starts no refresh and advances no sequence.
            self._record("rejected")
            raise
        # Lazy refill and latch flush happen only when a real host event is
        # dispatched. No clock sample, timer or wakeup occurs elsewhere.
        self._refill()
        self._flush_pending()
        self._dispatch_count += 1
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
        # Authoritative state was already committed above. The limiter can
        # only classify the outcome; it never drops a legitimate event or
        # reports a committed state as failed.
        outcome = self._commit_outcome(topic, frozen_fields)
        self._record(outcome)
        return DispatchResult(event, deliveries, failures, outcome)

    def close(self):
        if get_ident() != self._owner_thread:
            raise HostEventError("host event bus used from a different thread")
        if self._dispatching:
            raise HostEventsBusy("host callback cannot close dispatcher")
        if self._closed:
            return
        self._subscriptions.clear()
        self._trusted.clear()
        # Drop bounded diagnostic rings on shutdown; no pending work survives
        # the bus lifecycle because no timer, thread or queue exists.
        self._outcomes.clear()
        self._fingerprints.clear()
        self._refresh_pending = False
        self._closed = True

    @property
    def subscription_count(self):
        return len(self._subscriptions)

    @property
    def closed(self):
        return self._closed

    @property
    def last_outcome(self):
        return self._last_outcome

    @property
    def outcome_history(self):
        """Fixed-token tuple from the bounded 16-entry ring."""
        return tuple(self._outcomes)

    @property
    def refresh_pending(self):
        """One-bit latch; true only between a missed refresh and a flush."""
        return self._refresh_pending

    @property
    def refresh_requests(self):
        return self._refresh_requests

    @property
    def limiter_stats(self):
        """Read-only counters and fixed bounds; no caller text is carried."""
        return MappingProxyType({
            "bucket_capacity": BUCKET_CAPACITY,
            "refill_ms": BUCKET_REFILL_MS,
            "tokens": self._tokens,
            "outcome_max": OUTCOME_HISTORY_MAX,
            "outcome_count": len(self._outcomes),
            "fingerprint_max": REFRESH_FINGERPRINT_MAX,
            "fingerprint_count": len(self._fingerprints),
            "dispatch_count": self._dispatch_count,
            "accepted": self._accepted_count,
            "rejected": self._rejected_count,
            "refresh_requests": self._refresh_requests,
            "refresh_pending": self._refresh_pending,
        })
