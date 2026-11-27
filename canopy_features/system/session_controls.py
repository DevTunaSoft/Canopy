"""Fail-closed native-path contracts for Classic session logout and shutdown.

This module is an inert decision surface. It never starts a process, opens a
socket, touches D-Bus, reads the environment, observes a real session, waits,
polls, grants a privilege or changes the host. A trusted host adapter owns any
later action; the object returned here is a bounded description, not a command
and not permission to execute one.

Existing contracts reused (nothing is redefined here):

- ``canopy_core.host_events.TOPICS`` / ``PROTOCOL_VERSION``: the existing
  ``session.state.changed`` topic is referenced only as an observation topic;
  no event is created, published or subscribed to, and no field or fifth topic
  is added to that protocol.
- ``canopy_features.system.quick_controls_state``: its stable reason codes and
  disclosures are reused verbatim. That module already classifies suspend and
  lock as privileged host changes; logout and shutdown are in the same class,
  so a grant here never implies an in-process action.
- ``canopy_features.security.privilege_boundary``: any caller-supplied
  command-shaped candidate is checked against the existing deny gate and is
  then refused unconditionally. This contract accepts no raw command at all.

Native interface tokens describe where a trusted host adapter may hand off.
They are abstract names, not executables, D-Bus calls or shell fragments. A
path is produced only when an explicit host capability report, an explicit
matching confirmation and the adapter's allowlist all agree. Anything absent,
unavailable, mismatched or malformed fails closed with a stable reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional

from canopy_core.host_events import PROTOCOL_VERSION, TOPICS
from canopy_features.security import privilege_boundary
from canopy_features.system import quick_controls_state as qcs

ACTION_LOGOUT = "logout"
ACTION_SHUTDOWN = "shutdown"
ACTIONS = frozenset({ACTION_LOGOUT, ACTION_SHUTDOWN})

# Abstract handoff interfaces. No executable, method name, service call or
# shell fragment is stored: the trusted native adapter owns that mapping.
NATIVE_INTERFACES = MappingProxyType({
    "logind": frozenset({ACTION_LOGOUT, ACTION_SHUTDOWN}),
    "session-manager": frozenset({ACTION_LOGOUT}),
})

SESSION_TOPIC = "session.state.changed"
NO_COMMAND = object()
if SESSION_TOPIC not in TOPICS:  # pragma: no cover - contract guard
    raise RuntimeError("host event contract no longer names session.state.changed")

REASON_OK = qcs.REASON_OK
REASON_INVALID_ACTION = qcs.REASON_INVALID_ACTION
REASON_NO_HOST_INTERFACE = qcs.REASON_NO_HOST_INTERFACE
REASON_BRIDGE_DISABLED = qcs.REASON_BRIDGE_DISABLED
REASON_INVALID_GRANT = qcs.REASON_INVALID_GRANT
REASON_UNCONFIRMED = "unconfirmed"
REASON_RAW_COMMAND_REFUSED = "raw-command-refused"

DISCLOSURES = MappingProxyType({
    REASON_OK: qcs.DISCLOSURES[qcs.REASON_OK],
    REASON_INVALID_ACTION: qcs.DISCLOSURES[qcs.REASON_INVALID_ACTION],
    REASON_NO_HOST_INTERFACE: qcs.DISCLOSURES[qcs.REASON_NO_HOST_INTERFACE],
    REASON_BRIDGE_DISABLED: qcs.DISCLOSURES[qcs.REASON_BRIDGE_DISABLED],
    REASON_INVALID_GRANT: qcs.DISCLOSURES[qcs.REASON_INVALID_GRANT],
    REASON_UNCONFIRMED: "Unavailable - no explicit user confirmation",
    REASON_RAW_COMMAND_REFUSED: "Unavailable - raw commands are not accepted",
})

MAX_SOURCE_BYTES = 64
SOURCE = re.compile(r"[a-z0-9_.:-]{0,64}\Z")

__all__ = [
    "ACTION_LOGOUT", "ACTION_SHUTDOWN", "ACTIONS", "DISCLOSURES",
    "MAX_SOURCE_BYTES", "NATIVE_INTERFACES", "NO_COMMAND", "PROTOCOL_VERSION",
    "REASON_BRIDGE_DISABLED", "REASON_INVALID_ACTION", "REASON_INVALID_GRANT",
    "REASON_NO_HOST_INTERFACE", "REASON_OK", "REASON_RAW_COMMAND_REFUSED",
    "REASON_UNCONFIRMED", "SESSION_TOPIC", "SOURCE", "TOPICS",
    "Confirmation", "Decision", "NativeCapability", "NativePath",
    "SessionControlsError", "evaluate_native_path", "refuse_command_candidate",
]


class SessionControlsError(ValueError):
    """Invalid, unbounded or untrusted input to a session-control contract."""


def _source(value, label):
    if type(value) is not str:
        raise SessionControlsError(label + " must be a string")
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError:
        raise SessionControlsError(label + " has invalid encoding") from None
    if size > MAX_SOURCE_BYTES or SOURCE.fullmatch(value) is None:
        raise SessionControlsError(label + " is not a bounded source token")
    return value


@dataclass(frozen=True)
class NativeCapability:
    """Explicit host assertion that one native interface handles one action.

    ``available`` is a fact supplied by a trusted host, never a probe or a
    guess performed here. ``source`` records bounded provenance only.
    """

    interface: str
    action: str
    available: bool
    source: str = "host"

    def __post_init__(self):
        if type(self.interface) is not str or self.interface not in NATIVE_INTERFACES:
            raise SessionControlsError("capability interface is not allowlisted")
        if type(self.action) is not str or self.action not in ACTIONS:
            raise SessionControlsError("capability action is not supported")
        if type(self.available) is not bool:
            raise SessionControlsError("capability availability must be a bool")
        _source(self.source, "capability source")


@dataclass(frozen=True)
class Confirmation:
    """Explicit, bounded confirmation for one action on one interface.

    A bare boolean cannot become an approval: the action and interface must
    match the capability before any path is described.
    """

    action: str
    interface: str
    confirmed: bool
    source: str = "user"

    def __post_init__(self):
        if type(self.action) is not str or self.action not in ACTIONS:
            raise SessionControlsError("confirmation action is not supported")
        if type(self.interface) is not str or self.interface not in NATIVE_INTERFACES:
            raise SessionControlsError("confirmation interface is not allowlisted")
        if type(self.confirmed) is not bool:
            raise SessionControlsError("confirmation flag must be a bool")
        _source(self.source, "confirmation source")


@dataclass(frozen=True)
class NativePath:
    """Inert handoff description. It contains no command, path or method."""

    action: str
    interface: str
    capability_source: str
    confirmation_source: str

    def __post_init__(self):
        if type(self.action) is not str or self.action not in ACTIONS:
            raise SessionControlsError("path action is not supported")
        if type(self.interface) is not str or self.interface not in NATIVE_INTERFACES:
            raise SessionControlsError("path interface is not allowlisted")
        if self.action not in NATIVE_INTERFACES[self.interface]:
            raise SessionControlsError("interface does not support the action")
        _source(self.capability_source, "path capability source")
        _source(self.confirmation_source, "path confirmation source")

    def to_dict(self):
        """Fresh bounded mapping; no caller object or executable text escapes."""
        return {
            "kind": "native-path",
            "action": self.action,
            "interface": self.interface,
            "capability_source": self.capability_source,
            "confirmation_source": self.confirmation_source,
        }


@dataclass(frozen=True)
class Decision:
    """Fail-closed decision with a stable reason and an optional inert path."""

    allowed: bool
    reason: str
    action: str = ""
    interface: str = ""
    boundary_reason: str = ""
    path: Optional[NativePath] = None

    def __post_init__(self):
        if type(self.allowed) is not bool:
            raise SessionControlsError("decision flag must be a bool")
        if type(self.reason) is not str or self.reason not in DISCLOSURES:
            raise SessionControlsError("decision reason is not a known code")
        if type(self.action) is not str or (
                self.action and self.action not in ACTIONS):
            raise SessionControlsError("decision action is not supported")
        if type(self.interface) is not str or (
                self.interface and self.interface not in NATIVE_INTERFACES):
            raise SessionControlsError("decision interface is not allowlisted")
        if type(self.boundary_reason) is not str:
            raise SessionControlsError("boundary reason must be a string")
        if self.path is not None and type(self.path) is not NativePath:
            raise SessionControlsError("decision path has the wrong type")
        if self.allowed != (self.path is not None):
            raise SessionControlsError("decision and path disagree")

    @property
    def disclosure(self):
        return DISCLOSURES[self.reason]

    def to_dict(self):
        """JSON-serializable snapshot; it never contains a process command."""
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "disclosure": self.disclosure,
            "action": self.action,
            "interface": self.interface,
            "boundary_reason": self.boundary_reason,
            "execution": "host-only-not-performed" if self.allowed
                         else "not-performed",
            "executed": False,
            "path": self.path.to_dict() if self.path is not None else None,
        }


def refuse_command_candidate(argv):
    """Return a denial for any command-shaped candidate; never authorize it.

    The existing privilege boundary supplies a stable secondary reason for
    diagnostics. Its ALLOWED answer is deliberately not sufficient here: this
    session-control contract accepts no executable vector at all.
    """
    try:
        boundary = privilege_boundary.evaluate(argv, euid=None)
        boundary_reason = boundary.reason if type(
            boundary) is privilege_boundary.Decision else ""
    except Exception:
        boundary_reason = ""
    return Decision(False, REASON_RAW_COMMAND_REFUSED,
                    boundary_reason=boundary_reason)


def evaluate_native_path(action, *, capability, confirmation,
                         command_candidate=NO_COMMAND):
    """Decide whether a trusted host may be given an inert native path.

    Nothing here executes, mutates state or observes the host. Any supplied
    command-shaped candidate (including an explicit ``None``) is refused
    before any other check, and every denial has no path.
    """
    if command_candidate is not NO_COMMAND:
        return refuse_command_candidate(command_candidate)

    if type(action) is not str or action not in ACTIONS:
        return Decision(False, REASON_INVALID_ACTION)

    if type(capability) is not NativeCapability:
        raise SessionControlsError("capability must be a NativeCapability")
    if type(confirmation) is not Confirmation:
        raise SessionControlsError("confirmation must be a Confirmation")

    if not confirmation.confirmed:
        return Decision(False, REASON_UNCONFIRMED, action)

    if (capability.action != action or confirmation.action != action
            or capability.interface != confirmation.interface):
        return Decision(False, REASON_INVALID_GRANT, action)

    interface = capability.interface
    if action not in NATIVE_INTERFACES[interface]:
        return Decision(False, REASON_NO_HOST_INTERFACE, action)

    if not capability.available:
        return Decision(False, REASON_BRIDGE_DISABLED, action, interface)

    path = NativePath(
        action=action,
        interface=interface,
        capability_source=capability.source,
        confirmation_source=confirmation.source,
    )
    return Decision(True, REASON_OK, action, interface, path=path)
