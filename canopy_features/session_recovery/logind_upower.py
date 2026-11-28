"""Pure parsers for already-captured read-only logind/UPower/Plasma text.

The project already uses ``loginctl`` and ``UPower`` as read-only host-status
sources. This module does **not** invoke them, subscribe to D-Bus, start a
service, poll, sleep or spawn a process. A trusted caller supplies text that a
host already captured through those existing interfaces; the parsers turn it
into bounded, fail-closed views. Unknown, duplicate or hostile values become
``None``/``unknown`` or a domain error, never a guessed PASS.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.session_recovery.contracts import (
    SessionRecoveryError, SOURCES)
from canopy_features.system.quick_controls_state import STATUS_TOKENS

__all__ = [
    "MAX_TEXT_BYTES", "MAX_LINES", "MAX_LINE_CHARS", "LOGIND_FIELDS",
    "UPOWER_STATES", "PLASMA_STATES", "READ_ONLY_SOURCES",
    "NO_NEW_SERVICE", "POLL_INTERVAL_SECONDS", "DAEMON",
    "LogindView", "PowerView", "PlasmaView",
    "parse_logind_show_session", "parse_upower_info", "parse_plasma_state",
]

MAX_TEXT_BYTES = 16384
MAX_LINES = 128
MAX_LINE_CHARS = 256

LOGIND_FIELDS = MappingProxyType({
    "Active": frozenset({"yes", "no"}),
    "LockedHint": frozenset({"yes", "no"}),
    "State": frozenset({"active", "inactive", "online", "offline"}),
    "Type": frozenset({"x11", "wayland", "tty"}),
})
UPOWER_STATES = frozenset(
    {"charging", "discharging", "empty", "fully-charged", "unknown"})
PLASMA_STATES = frozenset(STATUS_TOKENS["session"])

# Documentation of the existing read-only interfaces. These strings are data,
# never commands executed by this module.
READ_ONLY_SOURCES = MappingProxyType({
    "logind": "loginctl show-session <session-id> -p Active -p LockedHint -p State -p Type",
    "upower": "upower -i <battery-object-path>",
    "plasma": "host-status-file supplied by the trusted host, no new bus client",
})
NO_NEW_SERVICE = True
POLL_INTERVAL_SECONDS = None
DAEMON = False

if not SOURCES:  # pragma: no cover - contract guard at import
    raise RuntimeError("trusted host source contract changed")


def _lines(text):
    if type(text) is not str or len(text) > MAX_TEXT_BYTES:
        raise SessionRecoveryError("host status text is not bounded")
    lines = text.replace("\r\n", "\n").split("\n")
    if len(lines) > MAX_LINES:
        raise SessionRecoveryError("host status has too many lines")
    for line in lines:
        if len(line) > MAX_LINE_CHARS:
            raise SessionRecoveryError("host status line exceeds its bound")
    return lines


def _yes_no(value):
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


@dataclass(frozen=True)
class LogindView:
    """Bounded projection of an existing ``loginctl show-session`` capture."""

    active: object = None
    locked: object = None
    state: object = None
    session_type: object = None

    def __post_init__(self):
        for name in ("active", "locked"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise SessionRecoveryError("invalid logind boolean")
        for name in ("state", "session_type"):
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise SessionRecoveryError("invalid logind token")

    def to_dict(self):
        return {"active": self.active, "locked": self.locked,
                "state": self.state, "session_type": self.session_type}


@dataclass(frozen=True)
class PowerView:
    """Bounded projection of an existing ``upower -i`` capture."""

    state: str = "unknown"
    percentage: object = None

    def __post_init__(self):
        if type(self.state) is not str or self.state not in UPOWER_STATES:
            raise SessionRecoveryError("invalid UPower state")
        if (self.percentage is not None
                and (type(self.percentage) is not int
                     or not 0 <= self.percentage <= 100)):
            raise SessionRecoveryError("invalid UPower percentage")

    def to_dict(self):
        return {"state": self.state, "percentage": self.percentage}


@dataclass(frozen=True)
class PlasmaView:
    """Bounded session token from trusted host-status text."""

    state: str = "unknown"

    def __post_init__(self):
        if type(self.state) is not str or self.state not in PLASMA_STATES:
            raise SessionRecoveryError("invalid Plasma session state")

    def to_dict(self):
        return {"state": self.state}


def parse_logind_show_session(text):
    """Parse captured ``loginctl show-session`` output; fail closed."""
    fields = {}
    for line in _lines(text):
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if key not in LOGIND_FIELDS:
            continue
        if key in fields:
            raise SessionRecoveryError("duplicate logind field")
        value = value.strip().strip('"')
        fields[key] = value if value in LOGIND_FIELDS[key] else None
    return LogindView(active=_yes_no(fields.get("Active")),
                      locked=_yes_no(fields.get("LockedHint")),
                      state=fields.get("State"),
                      session_type=fields.get("Type"))


def parse_upower_info(text):
    """Parse captured ``upower -i`` output; unknown values stay unknown."""
    state = "unknown"
    percentage = None
    for line in _lines(text):
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key == "state":
            state = value if value in UPOWER_STATES else "unknown"
        elif key == "percentage" and percentage is None:
            digits = value[:-1] if value.endswith("%") else value
            if digits.isascii() and digits.isdigit():
                parsed = int(digits)
                if 0 <= parsed <= 100:
                    percentage = parsed
    return PowerView(state=state, percentage=percentage)


def parse_plasma_state(text):
    """Parse a trusted host-status ``state=<session-token>`` capture."""
    state = "unknown"
    for line in _lines(text):
        key, separator, value = line.partition("=")
        if not separator or key.strip().lower() != "state":
            continue
        value = value.strip()
        state = value if value in PLASMA_STATES else "unknown"
        break
    return PlasmaView(state=state)
