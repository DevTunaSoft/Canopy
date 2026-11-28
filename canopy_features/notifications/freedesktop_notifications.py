"""Bounded, read-only org.freedesktop.Notifications contract adapter.

This module validates *host-supplied observations* of the upstream D-Bus
notification service. It opens no bus connection, requests no bus name,
launches no daemon or process, creates no socket, Qt object, timer, poll or
thread, reads no file or environment, and announces nothing. It never claims
that a notification was delivered by itself: availability is reported only
when a complete, bounded observation set for one notification id and one
stable upstream owner is supplied by trusted host code.

No host-event topic, payload field or protocol version is added or changed.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass
import unicodedata

__all__ = [
    "ACCEPT", "ACCEPTED", "AVAILABLE", "BUS_NAME", "CAPABILITIES_CALL", "CLOSED",
    "CLOSED_SIGNAL", "CLOSE_CALL", "INCOMPLETE_ROUNDTRIP",
    "INVALID_NOTIFICATION_OBSERVATION", "INTERFACE", "MAX_EVENTS", "MAX_ID",
    "MAX_OWNER_BYTES", "MEMBERS", "NO_OBSERVATION", "NOTIFY_CALL",
    "NOTIFY_RETURN", "OBJECT_PATH", "OBSERVATION_KEYS", "OWNER_CHANGED",
    "REFUSED", "SERVER_INFO_CALL", "UNAVAILABLE", "ACTION_SIGNAL",
    "DeliveryEvidence", "FreedesktopNotifications",
    "NotificationContractError",
]

BUS_NAME = "org.freedesktop.Notifications"
OBJECT_PATH = "/org/freedesktop/Notifications"
INTERFACE = BUS_NAME

NOTIFY_CALL = "Notify.call"
NOTIFY_RETURN = "Notify.return"
CLOSE_CALL = "CloseNotification.call"
CLOSED_SIGNAL = "NotificationClosed.signal"
CAPABILITIES_CALL = "GetCapabilities.call"
SERVER_INFO_CALL = "GetServerInformation.call"
ACTION_SIGNAL = "ActionInvoked.signal"
MEMBERS = frozenset({NOTIFY_CALL, NOTIFY_RETURN, CLOSE_CALL, CLOSED_SIGNAL,
                     CAPABILITIES_CALL, SERVER_INFO_CALL, ACTION_SIGNAL})
_ID_MEMBERS = frozenset({NOTIFY_RETURN, CLOSE_CALL, CLOSED_SIGNAL,
                         ACTION_SIGNAL})

OBSERVATION_KEYS = frozenset({"bus_name", "object_path", "interface",
                              "member", "owner", "notification_id"})
MAX_EVENTS = 32
MAX_ID = (1 << 32) - 1
MAX_OWNER_BYTES = 64

ACCEPT = "accept"
ACCEPTED = "accepted"
REFUSED = "refused"
AVAILABLE = "available"
UNAVAILABLE = "unavailable"
DELIVERED = "delivered"
CLOSED = "closed"
NO_OBSERVATION = "no_observation"
INCOMPLETE_ROUNDTRIP = "incomplete_roundtrip"

# Fixed refusal tokens; no rejected value or exception text is ever echoed.
INVALID_NOTIFICATION_OBSERVATION = "INVALID_NOTIFICATION_OBSERVATION"
OWNER_CHANGED = "NOTIFICATION_OWNER_CHANGED"

_UNIQUE_NAME = re.compile(r":1\.[0-9]{1,9}(?:\.[0-9]{1,9})?\Z")
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


class NotificationContractError(ValueError):
    """Invalid bound or an operation after explicit shutdown."""


@dataclass(frozen=True)
class ObservedEvent:
    """One accepted, bounded observation; never carries caller text."""

    member: str
    notification_id: object
    owner: str

    def as_dict(self):
        return {"member": self.member,
                "notification_id": self.notification_id,
                "owner": self.owner}


@dataclass(frozen=True)
class DeliveryEvidence:
    """Fixed-token view of one bounded notification round trip."""

    status: str
    reason: str
    refusal: object
    owner_stable: bool
    call_count: int
    return_count: int
    close_count: int
    closed_count: int
    matched_id: object

    def as_dict(self):
        return {
            "status": self.status,
            "reason": self.reason,
            "refusal": self.refusal,
            "owner_stable": self.owner_stable,
            "call_count": self.call_count,
            "return_count": self.return_count,
            "close_count": self.close_count,
            "closed_count": self.closed_count,
            "matched_id": self.matched_id,
        }


class FreedesktopNotifications:
    """Host-owned, bounded observation view of the upstream service.

    ``observe()`` consumes one host mapping, returns a fixed token and keeps
    at most ``max_events`` validated rows. ``evidence()`` is a pure read that
    does no work. A second owner, any malformed observation, or an explicit
    close stays unavailable until a fresh lifecycle is constructed.
    """

    def __init__(self, *, max_events=MAX_EVENTS):
        if type(max_events) is not int or not 1 <= max_events <= MAX_EVENTS:
            raise NotificationContractError("invalid event bound")
        self._max_events = max_events
        self._events = []
        self._owner = None
        self._owner_changed = False
        self._refusal = None
        self._rejected = 0
        self._dropped = 0
        self._closed = False

    @staticmethod
    def _text(value, limit, expected=None):
        if type(value) is not str or not value:
            return None
        if len(value) > limit or len(value.encode("utf-8", "strict")) > limit:
            return None
        if any(unicodedata.category(char) in _UNSAFE_CATEGORIES
               for char in value):
            return None
        if expected is not None and value != expected:
            return None
        return value

    @classmethod
    def _validate(cls, observation):
        if not isinstance(observation, Mapping):
            return None
        try:
            items = tuple(observation.items())
        except Exception:
            return None
        if len(items) != len(OBSERVATION_KEYS):
            return None
        seen = {}
        for key, value in items:
            if type(key) is not str or key not in OBSERVATION_KEYS or key in seen:
                return None
            seen[key] = value
        if frozenset(seen) != OBSERVATION_KEYS:
            return None
        if cls._text(seen["bus_name"], MAX_OWNER_BYTES, BUS_NAME) is None:
            return None
        if cls._text(seen["object_path"], MAX_OWNER_BYTES, OBJECT_PATH) is None:
            return None
        if cls._text(seen["interface"], MAX_OWNER_BYTES, INTERFACE) is None:
            return None
        member = seen["member"]
        if type(member) is not str or member not in MEMBERS:
            return None
        owner = cls._text(seen["owner"], MAX_OWNER_BYTES)
        if owner is None or _UNIQUE_NAME.fullmatch(owner) is None:
            return None
        identifier = seen["notification_id"]
        if member in _ID_MEMBERS:
            if type(identifier) is not int or not 1 <= identifier <= MAX_ID:
                return None
        elif identifier is not None:
            return None
        return {"member": member, "notification_id": identifier,
                "owner": owner}

    def _ready(self):
        if self._closed:
            raise NotificationContractError("notification contract is closed")

    def observe(self, observation):
        """Validate one host observation; return ``accepted`` or ``refused``."""
        self._ready()
        if self._owner_changed:
            self._refusal = OWNER_CHANGED
            self._rejected += 1
            return REFUSED
        try:
            row = self._validate(observation)
        except Exception:
            row = None
        if row is None:
            self._refusal = INVALID_NOTIFICATION_OBSERVATION
            self._rejected += 1
            return REFUSED
        if self._owner is not None and row["owner"] != self._owner:
            self._owner_changed = True
            self._refusal = OWNER_CHANGED
            self._rejected += 1
            return REFUSED
        if self._owner is None:
            self._owner = row["owner"]
        if len(self._events) >= self._max_events:
            self._events.pop(0)
            self._dropped += 1
        self._events.append(ObservedEvent(row["member"],
                                          row["notification_id"],
                                          row["owner"]))
        self._refusal = None
        return ACCEPT

    def evidence(self):
        """Pure bounded view; no I/O, no observation and no mutation."""
        counts = {member: 0 for member in MEMBERS}
        ids = {member: set() for member in _ID_MEMBERS}
        for event in self._events:
            counts[event.member] += 1
            if event.member in _ID_MEMBERS:
                ids[event.member].add(event.notification_id)
        matched = sorted(ids[NOTIFY_RETURN] & ids[CLOSE_CALL]
                         & ids[CLOSED_SIGNAL])
        matched_id = matched[0] if matched else None
        complete = (counts[NOTIFY_CALL] > 0 and bool(matched)
                    and counts[CLOSED_SIGNAL] > 0)
        if self._closed:
            status, reason = UNAVAILABLE, CLOSED
        elif self._refusal is not None:
            status, reason = UNAVAILABLE, self._refusal
        elif self._owner is None:
            status, reason = UNAVAILABLE, NO_OBSERVATION
        elif not complete:
            status, reason = UNAVAILABLE, INCOMPLETE_ROUNDTRIP
        else:
            status, reason = AVAILABLE, "none"
        return DeliveryEvidence(
            status=status, reason=reason, refusal=self._refusal,
            owner_stable=self._owner is not None and self._refusal is None,
            call_count=counts[NOTIFY_CALL],
            return_count=counts[NOTIFY_RETURN],
            close_count=counts[CLOSE_CALL],
            closed_count=counts[CLOSED_SIGNAL],
            matched_id=matched_id)

    def close(self):
        """Idempotent, fail-closed cleanup of the bounded view."""
        if self._closed:
            return
        self._events.clear()
        self._owner = None
        self._refusal = CLOSED
        self._closed = True
