"""Fail-closed quick-controls state for Canopy Classic.

Pure, in-process policy for the four quick-control domains (network, audio,
power and session). It never probes hardware, opens sockets, starts a service,
calls a compositor, spawns a process or changes the host. A trusted host passes
only bounded observations and explicit interface flags; this module turns them
into stable status/availability views that a presentation can display.

Existing interfaces reused here:
- ``canopy_core.host_events`` topic contract names the session observation
  source; no second event bus is created.
- ``canopy_features.reliability.lock_session_events.SessionState`` is accepted
  directly as a trusted session observation.
- ``canopySystemLauncher``'s "Settings" target is represented by the explicit
  ``settings_bridge`` flag. Only that non-privileged app-bridge action can be
  allowed. Suspend and lock are always refused: they are privileged host
  changes, and this module has no authority to perform them.

Honest limits: no network/audio/power/session control bridge exists in the
Classic preview today. Every ungranted control therefore reports
``UNAVAILABLE`` with a stable reason code and a visible disclosure instead of
pretending to work. Deciding is not executing; the caller owns any action.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional

from canopy_core.host_events import TOPICS as _HOST_EVENT_TOPICS
from canopy_features.reliability.lock_session_events import SessionState

__all__ = [
    "DOMAINS",
    "ACTIONS",
    "SETTINGS_ACTION",
    "DOMAIN_CONTROL",
    "STATUS_TOKENS",
    "STATUS_LABELS",
    "SESSION_TOPIC",
    "AVAILABLE",
    "UNAVAILABLE",
    "REASON_OK",
    "REASON_NO_HOST_OBSERVATION",
    "REASON_NO_HOST_INTERFACE",
    "REASON_BRIDGE_DISABLED",
    "REASON_PRIVILEGED_HOST_CHANGE",
    "REASON_INVALID_DOMAIN",
    "REASON_INVALID_ACTION",
    "REASON_INVALID_GRANT",
    "DISCLOSURES",
    "QuickControlsStateError",
    "Observation",
    "HostInterfaces",
    "Grant",
    "Decision",
    "ControlView",
    "QuickControlsState",
    "observation_from_session",
    "empty_state",
]


DOMAINS = ("network", "audio", "power", "session")
SETTINGS_ACTION = "open_settings"
# One direct control per domain; privileged ones are never executable here.
DOMAIN_CONTROL = MappingProxyType({
    "network": "toggle_wifi",
    "audio": "toggle_mute",
    "power": "suspend",
    "session": "lock",
})
ACTIONS = frozenset({SETTINGS_ACTION, *DOMAIN_CONTROL.values()})

STATUS_TOKENS = MappingProxyType({
    "network": frozenset({"connected", "disconnected", "unknown"}),
    "audio": frozenset({"muted", "unmuted", "unknown"}),
    "power": frozenset({"charging", "discharging", "unknown"}),
    "session": frozenset({"active", "locked", "suspended", "unknown"}),
})
STATUS_LABELS = MappingProxyType({
    "connected": "Connected",
    "disconnected": "Not connected",
    "muted": "Muted",
    "unmuted": "Sound on",
    "charging": "Charging",
    "discharging": "On battery",
    "active": "Active",
    "locked": "Locked",
    "suspended": "Suspended",
    "unknown": "Unknown — no host status",
})

# Bound to the existing host event contract rather than a new private topic.
SESSION_TOPIC = "session.state.changed"
if SESSION_TOPIC not in _HOST_EVENT_TOPICS:  # pragma: no cover - contract guard
    raise RuntimeError("host event contract no longer names session.state.changed")

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"

REASON_OK = "ok"
REASON_NO_HOST_OBSERVATION = "no-host-observation"
REASON_NO_HOST_INTERFACE = "no-host-interface"
REASON_BRIDGE_DISABLED = "bridge-disabled"
REASON_PRIVILEGED_HOST_CHANGE = "privileged-host-change"
REASON_INVALID_DOMAIN = "invalid-domain"
REASON_INVALID_ACTION = "invalid-action"
REASON_INVALID_GRANT = "invalid-grant"

# Stable, caller-independent text. Hostile observation strings can never reach
# the UI: only enumerated status tokens and these fixed disclosures are used.
DISCLOSURES = MappingProxyType({
    REASON_OK: "Available",
    REASON_NO_HOST_OBSERVATION: "Unavailable — no host status observation",
    REASON_NO_HOST_INTERFACE: "Unavailable — no host control interface",
    REASON_BRIDGE_DISABLED: "Unavailable — host control bridge disabled",
    REASON_PRIVILEGED_HOST_CHANGE:
        "Unavailable — privileged host changes are not performed",
    REASON_INVALID_DOMAIN: "Unavailable — unknown control domain",
    REASON_INVALID_ACTION: "Unavailable — unknown control action",
    REASON_INVALID_GRANT: "Unavailable — invalid capability grant",
})

_PRIVILEGED_ACTIONS = frozenset({"suspend", "lock"})
_BRIDGE_FOR_ACTION = MappingProxyType({
    "toggle_wifi": "network_control_bridge",
    "toggle_mute": "audio_control_bridge",
})
_SOURCE = re.compile(r"[a-z0-9_.:-]{0,64}\Z")
MAX_SOURCE_BYTES = 64


class QuickControlsStateError(ValueError):
    """Invalid, ambiguous or untrusted caller input."""


@dataclass(frozen=True)
class Observation:
    """One bounded status token supplied by a trusted host observer."""

    domain: str
    status: str
    source: str = "host"

    def __post_init__(self):
        if type(self.domain) is not str or self.domain not in DOMAINS:
            raise QuickControlsStateError("invalid observation domain")
        if (type(self.status) is not str
                or self.status not in STATUS_TOKENS[self.domain]):
            raise QuickControlsStateError("unsupported observation status")
        if (type(self.source) is not str
                or len(self.source.encode("utf-8", "strict")) > MAX_SOURCE_BYTES
                or not _SOURCE.fullmatch(self.source)):
            raise QuickControlsStateError("invalid observation source")


@dataclass(frozen=True)
class HostInterfaces:
    """Explicit, trusted host bridge flags. All default to unavailable."""

    settings_bridge: bool = False
    network_control_bridge: bool = False
    audio_control_bridge: bool = False

    def __post_init__(self):
        for name in ("settings_bridge", "network_control_bridge",
                     "audio_control_bridge"):
            if type(getattr(self, name)) is not bool:
                raise QuickControlsStateError(name + " must be a bool")


@dataclass(frozen=True)
class Grant:
    """Explicit action grant for one domain. Never inferred from UI text."""

    domain: str
    actions: frozenset

    def __post_init__(self):
        if type(self.domain) is not str or self.domain not in DOMAINS:
            raise QuickControlsStateError("invalid grant domain")
        if type(self.actions) is not frozenset:
            raise QuickControlsStateError("grant actions must be a frozenset")
        for action in self.actions:
            if type(action) is not str or action not in ACTIONS:
                raise QuickControlsStateError("unsupported grant action")


@dataclass(frozen=True)
class Decision:
    """Whether a presentation may offer an action, and why."""

    allowed: bool
    reason: str

    def __post_init__(self):
        if type(self.allowed) is not bool or self.reason not in DISCLOSURES:
            raise QuickControlsStateError("invalid decision")

    @property
    def disclosure(self):
        return DISCLOSURES[self.reason]

    def to_dict(self):
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "disclosure": self.disclosure,
        }


@dataclass(frozen=True)
class ControlView:
    """Renderable, fail-closed view of one quick-control domain."""

    domain: str
    status: str
    status_label: str
    source: str
    observed: bool
    control: Decision
    settings: Decision

    @property
    def availability(self):
        return AVAILABLE if self.control.allowed or self.settings.allowed \
            else UNAVAILABLE

    def to_dict(self):
        return {
            "domain": self.domain,
            "status": self.status,
            "status_label": self.status_label,
            "source": self.source,
            "observed": self.observed,
            "availability": self.availability,
            "control": self.control.to_dict(),
            "settings": self.settings.to_dict(),
        }


def observation_from_session(state, source: str = "host") -> Observation:
    """Convert an existing Reconciler SessionState into a bounded observation.

    Wrong types are rejected rather than guessed from attributes, so a hostile
    or stale object cannot acquire session status in the UI.
    """
    if type(state) is not SessionState:
        raise QuickControlsStateError("session observation requires SessionState")
    return Observation("session", state.label, source)


class QuickControlsState:
    """Immutable policy snapshot builder; no I/O, caching or background work."""

    def __init__(self, *, interfaces: Optional[HostInterfaces] = None,
                 observations=(), grants=()):
        if interfaces is None:
            interfaces = HostInterfaces()
        elif type(interfaces) is not HostInterfaces:
            raise QuickControlsStateError("interfaces must be HostInterfaces")
        if type(observations) not in (tuple, list):
            raise QuickControlsStateError("observations must be a tuple or list")
        if type(grants) not in (tuple, list):
            raise QuickControlsStateError("grants must be a tuple or list")
        observed = {}
        for observation in observations:
            if type(observation) is not Observation:
                raise QuickControlsStateError("observation has wrong type")
            if observation.domain in observed:
                raise QuickControlsStateError("duplicate domain observation")
            observed[observation.domain] = observation
        granted = {}
        for grant in grants:
            if type(grant) is not Grant:
                raise QuickControlsStateError("grant has wrong type")
            if grant.domain in granted:
                raise QuickControlsStateError("duplicate domain grant")
            granted[grant.domain] = grant
        self._interfaces = interfaces
        self._observations = MappingProxyType(observed)
        self._grants = MappingProxyType(granted)

    def observe(self, observation):
        """Return a new state with one observation added; never mutate self."""
        if type(observation) is not Observation:
            raise QuickControlsStateError("observation has wrong type")
        records = list(self._observations.values())
        if observation.domain in self._observations:
            records = [item for item in records
                       if item.domain != observation.domain]
        records.append(observation)
        return QuickControlsState(interfaces=self._interfaces,
                                  observations=tuple(records),
                                  grants=tuple(self._grants.values()))

    def _decision(self, domain: str, action: str) -> Decision:
        if domain not in DOMAINS:
            return Decision(False, REASON_INVALID_DOMAIN)
        if action not in ACTIONS:
            return Decision(False, REASON_INVALID_ACTION)
        if action == SETTINGS_ACTION:
            # The existing GIO app bridge is the only non-privileged interface
            # Classic can honestly offer today. The host declares it enabled
            # after canLaunch("Settings"); this module never guesses.
            if self._interfaces.settings_bridge:
                return Decision(True, REASON_OK)
            return Decision(False, REASON_BRIDGE_DISABLED)
        if action in _PRIVILEGED_ACTIONS:
            # Suspend/lock/logout change the host session. No grant here can
            # authorize this module to perform them.
            return Decision(False, REASON_PRIVILEGED_HOST_CHANGE)
        grant = self._grants.get(domain)
        if grant is None or action not in grant.actions:
            return Decision(False, REASON_NO_HOST_INTERFACE)
        if not getattr(self._interfaces, _BRIDGE_FOR_ACTION[action]):
            return Decision(False, REASON_BRIDGE_DISABLED)
        return Decision(True, REASON_OK)

    def decide(self, domain, action) -> Decision:
        """Fail-closed decision for one domain/action pair; never executes."""
        safe_domain = domain if type(domain) is str and domain in DOMAINS else ""
        safe_action = action if type(action) is str and action in ACTIONS else ""
        return self._decision(safe_domain, safe_action)

    def view(self, domain) -> ControlView:
        if type(domain) is not str or domain not in DOMAINS:
            denied = Decision(False, REASON_INVALID_DOMAIN)
            return ControlView("unknown", "unknown", STATUS_LABELS["unknown"],
                               "none", False, denied, denied)
        observation = self._observations.get(domain)
        status = observation.status if observation is not None else "unknown"
        source = observation.source if observation is not None else "none"
        return ControlView(
            domain=domain,
            status=status,
            status_label=STATUS_LABELS[status],
            source=source,
            observed=observation is not None,
            control=self._decision(domain, DOMAIN_CONTROL[domain]),
            settings=self._decision(domain, SETTINGS_ACTION),
        )

    def snapshot(self):
        """Point-in-time immutable mapping of all four domain views."""
        return MappingProxyType({domain: self.view(domain) for domain in DOMAINS})

    def to_dict(self):
        return {domain: self.view(domain).to_dict() for domain in DOMAINS}


def empty_state() -> QuickControlsState:
    """The honest default: nothing observed, nothing granted, nothing enabled."""
    return QuickControlsState()
