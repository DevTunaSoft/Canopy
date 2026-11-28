"""Bounded system-tray interaction observation contract (pure Python).

The Plasma tray is an upstream facility; this module never clicks it, opens
a popup, sends an action, speaks D-Bus, creates a Qt object or starts a
process. It only validates a bounded, host-supplied observation that names an
exact facility, an exact allowlisted action, an exact acknowledgement and a
well-formed unique bus name. Every rejection returns a fixed token and never
echoes the rejected value or an exception message.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass
import unicodedata

__all__ = [
    "ACCEPT", "ACCEPTED", "ACTION_INVOKED", "ACTIVATE", "BUS_NAME",
    "CLOSED", "DISMISS", "INVALID_TRAY_OBSERVATION", "MAX_ACTION_BYTES",
    "MAX_OBSERVATION_FIELDS", "OBJECT_PATH", "OPEN_CENTER", "REFUSED",
    "UNAVAILABLE",
    "TrayState", "TrayInteraction", "TrayInteractionError",
]

BUS_NAME = "org.kde.plasmashell"
OBJECT_PATH = "/org/kde/plasmashell"
OPEN_CENTER = "OPEN_CENTER"
DISMISS = "DISMISS"
ACTIVATE = "ACTIVATE"
ACTION_INVOKED = "ACTION_INVOKED"
ALLOWED_ACTIONS = frozenset({OPEN_CENTER, DISMISS, ACTIVATE, ACTION_INVOKED})

OBSERVATION_KEYS = frozenset({"facility", "action", "acknowledged",
                              "unique_name"})
MAX_OBSERVATION_FIELDS = 8
MAX_ACTION_BYTES = 64

ACCEPT = "accept"
ACCEPTED = "accepted"
REFUSED = "refused"
UNAVAILABLE = "unavailable"
CLOSED = "closed"
NO_OBSERVATION = "no_observation"
INVALID_TRAY_OBSERVATION = "INVALID_TRAY_OBSERVATION"

_UNIQUE_NAME = re.compile(r":1\.[0-9]{1,9}(?:\.[0-9]{1,9})?\Z")
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


class TrayInteractionError(ValueError):
    """Invalid bound or an operation after explicit shutdown."""


@dataclass(frozen=True)
class TrayState:
    """Fixed-token view with bounded counters; no caller data retained."""

    status: str
    reason: str
    refusal: object
    accepted_count: int
    refused_count: int
    last_action: object

    def as_dict(self):
        return {"status": self.status, "reason": self.reason,
                "refusal": self.refusal,
                "accepted_count": self.accepted_count,
                "refused_count": self.refused_count,
                "last_action": self.last_action}


class TrayInteraction:
    """Validate host observations of upstream tray interaction.

    ``observe()`` never performs the action; it records only that a trusted
    host reported one. ``state()`` is a pure read. The bounded counters and
    the last allowlisted action token are the entire retained surface.
    """

    def __init__(self, *, max_observations=64):
        if type(max_observations) is not int or not 1 <= max_observations <= 256:
            raise TrayInteractionError("invalid observation bound")
        self._max = max_observations
        self._accepted = 0
        self._refused = 0
        self._last_action = None
        self._refusal = None
        self._closed = False

    @staticmethod
    def _safe_text(value, limit, expected=None):
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
        if not 1 <= len(items) <= MAX_OBSERVATION_FIELDS:
            return None
        seen = {}
        for key, value in items:
            if type(key) is not str or key not in OBSERVATION_KEYS or key in seen:
                return None
            seen[key] = value
        if frozenset(seen) != OBSERVATION_KEYS:
            return None
        if cls._safe_text(seen["facility"], MAX_ACTION_BYTES, BUS_NAME) is None:
            return None
        action = cls._safe_text(seen["action"], MAX_ACTION_BYTES)
        if action is None or action not in ALLOWED_ACTIONS:
            return None
        if seen["acknowledged"] is not True:
            return None
        name = cls._safe_text(seen["unique_name"], MAX_ACTION_BYTES)
        if name is None or _UNIQUE_NAME.fullmatch(name) is None:
            return None
        return action

    def observe(self, observation):
        """Validate one host report; return a fixed accept/refuse token."""
        if self._closed:
            raise TrayInteractionError("tray interaction is closed")
        if self._accepted + self._refused >= self._max:
            self._refusal = INVALID_TRAY_OBSERVATION
            self._refused += 1
            return REFUSED
        try:
            action = self._validate(observation)
        except Exception:
            action = None
        if action is None:
            self._refusal = INVALID_TRAY_OBSERVATION
            self._refused += 1
            return REFUSED
        self._accepted += 1
        self._last_action = action
        self._refusal = None
        return ACCEPT

    def state(self):
        """Pure bounded view of accepted observations."""
        if self._closed:
            return TrayState(UNAVAILABLE, CLOSED, None, self._accepted,
                             self._refused, None)
        if self._refusal is not None:
            return TrayState(UNAVAILABLE, INVALID_TRAY_OBSERVATION,
                             self._refusal, self._accepted, self._refused,
                             self._last_action)
        if self._last_action is None:
            return TrayState(UNAVAILABLE, NO_OBSERVATION, None,
                             self._accepted, self._refused, None)
        return TrayState(ACCEPTED, "none", None, self._accepted,
                         self._refused, self._last_action)

    def close(self):
        """Idempotent shutdown; no external facility is touched."""
        if self._closed:
            return
        self._closed = True
        self._last_action = None
        self._refusal = None
