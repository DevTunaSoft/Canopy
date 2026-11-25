"""Read-only host-state adapter for Canopy Classic quick controls.

The fail-closed policy in ``canopy_features.system.quick_controls_state`` turns
trusted observations into stable status/availability views but deliberately
does no I/O. This module is the trusted, in-process boundary that converts
observations already produced by *existing* host contracts into that policy's
inputs and into the view contract consumed by ``QuickControlsOverlay.qml``.

Existing contracts reused here (nothing new is invented):

- ``canopy_core.host_events.HostEvent`` / ``TOPICS``: a trusted host publishes a
  bounded payload on an already-defined topic (for example
  ``capabilities.report``). This module only reads the delivered event; it
  never creates a bus, subscribes, opens a network connection or starts a
  service.
- ``canopy_features.reliability.lock_session_events.SessionState``: the
  reconciled, fail-closed session state is accepted directly.
- ``canopy_features.system.quick_controls_state``: the pure model supplies all
  statuses, disclosures and decisions. No domain, status token or disclosure is
  redefined here.

Real desktop facts carried by the bounded payload (when a trusted host supplies
them): ``network_connected`` (network), ``audio_muted`` and ``volume_percent``
(sound), ``brightness_percent`` (display power detail) and
``battery_charging`` (power). A missing, malformed or out-of-range field is
never guessed: its domain stays ``unknown`` with a visible unavailable
disclosure. No field can grant a host change; suspend/lock and direct toggles
remain denied by the pure model.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Optional

from canopy_core.host_events import TOPICS, HostEvent
from canopy_features.reliability.lock_session_events import SessionState
from canopy_features.system.quick_controls_state import (
    DOMAINS,
    HostInterfaces,
    Observation,
    QuickControlsState,
    observation_from_session,
)

__all__ = [
    "ALLOWED_FIELDS",
    "DEFAULT_SOURCE",
    "FIELDS",
    "MAX_SOURCE_BYTES",
    "HostStateError",
    "HostStateSnapshot",
    "HostStateController",
    "empty_snapshot",
]


class HostStateError(ValueError):
    """Invalid, ambiguous or untrusted host-state input."""


DEFAULT_SOURCE = "host-events"
MAX_SOURCE_BYTES = 64
_SOURCE = re.compile(r"[a-z0-9_.:-]{0,64}\Z")

# Field names are legal ``canopy_core.host_events`` field names: lowercase
# ASCII with underscores and no credential-bearing component.
FIELDS = {
    "network_connected": "network_connected",
    "audio_muted": "audio_muted",
    "battery_charging": "battery_charging",
    "volume_percent": "volume_percent",
    "brightness_percent": "brightness_percent",
    "settings_bridge": "settings_bridge",
}
ALLOWED_FIELDS = frozenset(FIELDS)
_BOOL_FIELDS = ("network_connected", "audio_muted", "battery_charging")
_PERCENT_FIELDS = ("volume_percent", "brightness_percent")


def _check_source(source) -> str:
    if type(source) is not str:
        raise HostStateError("host state source must be a string")
    try:
        size = len(source.encode("utf-8", "strict"))
    except UnicodeError:
        raise HostStateError("invalid host state source") from None
    if size > MAX_SOURCE_BYTES or not _SOURCE.fullmatch(source):
        raise HostStateError("invalid host state source")
    return source


@dataclass(frozen=True)
class HostStateSnapshot:
    """Bounded, immutable host observations. Every field is optional.

    ``None`` means "the host did not observe this", which the policy renders as
    ``unknown`` with a visible unavailable disclosure. It never means "false"
    or "zero". Wrong types are refused instead of being coerced into a status.
    """

    network_connected: Optional[bool] = None
    audio_muted: Optional[bool] = None
    battery_charging: Optional[bool] = None
    volume_percent: Optional[int] = None
    brightness_percent: Optional[int] = None
    session: Optional[SessionState] = None
    settings_bridge: bool = False
    source: str = DEFAULT_SOURCE

    def __post_init__(self):
        for name in _BOOL_FIELDS:
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise HostStateError(name + " must be a bool or None")
        for name in _PERCENT_FIELDS:
            value = getattr(self, name)
            if value is not None and (
                    type(value) is not int or not 0 <= value <= 100):
                raise HostStateError(name + " must be an int in 0..100 or None")
        if self.session is not None and type(self.session) is not SessionState:
            raise HostStateError("session must be a SessionState or None")
        if type(self.settings_bridge) is not bool:
            raise HostStateError("settings_bridge must be a bool")
        _check_source(self.source)

    def observations(self):
        """Convert supplied facts into the pure model's bounded observations."""
        observations = []
        if self.network_connected is not None:
            token = "connected" if self.network_connected else "disconnected"
            observations.append(Observation("network", token, self.source))
        if self.audio_muted is not None:
            token = "muted" if self.audio_muted else "unmuted"
            observations.append(Observation("audio", token, self.source))
        if self.battery_charging is not None:
            token = "charging" if self.battery_charging else "discharging"
            observations.append(Observation("power", token, self.source))
        if self.session is not None:
            observations.append(
                observation_from_session(self.session, self.source))
        return tuple(observations)

    def _state(self) -> QuickControlsState:
        return QuickControlsState(
            interfaces=HostInterfaces(settings_bridge=self.settings_bridge),
            observations=self.observations(),
            grants=(),
        )

    @staticmethod
    def _detail(domain, snapshot):
        """Enumerated detail kind plus bounded integer; no caller text."""
        if domain == "audio" and snapshot.volume_percent is not None:
            return "volume", snapshot.volume_percent
        if domain == "power" and snapshot.brightness_percent is not None:
            return "brightness", snapshot.brightness_percent
        return "", -1

    def view(self, domain):
        """One QML-controller view; fail closed for unknown domains."""
        payload = self._state().view(domain).to_dict()
        if type(domain) is str and domain in DOMAINS:
            kind, value = self._detail(domain, self)
            payload["detail_kind"] = kind
            payload["detail_value"] = value
        return payload

    def to_dict(self):
        """All four domain views as a JSON-serializable mapping."""
        state = self._state()
        result = {}
        for domain in DOMAINS:
            payload = state.view(domain).to_dict()
            kind, value = self._detail(domain, self)
            payload["detail_kind"] = kind
            payload["detail_value"] = value
            result[domain] = payload
        return result

    @classmethod
    def from_payload(cls, payload, *, source: str = DEFAULT_SOURCE):
        """Adapt a trusted, bounded host payload (no I/O performed here).

        Unknown keys are ignored: a host event may carry fields for other
        consumers. Values for known keys are type-checked by ``__post_init__``.
        """
        if not isinstance(payload, Mapping):
            raise HostStateError("host state payload must be a mapping")
        try:
            supplied_source = payload.get("source", source)
        except (KeyError, TypeError):
            raise HostStateError("unreadable host state payload") from None
        values = {}
        for field in ALLOWED_FIELDS:
            try:
                present = field in payload
            except (KeyError, TypeError):
                raise HostStateError("unreadable host state payload") from None
            if present:
                try:
                    values[field] = payload[field]
                except (KeyError, TypeError):
                    raise HostStateError("unreadable host state field") from None
        return cls(source=supplied_source, **values)

    @classmethod
    def from_host_event(cls, event):
        """Adapt a delivered event from the existing host event contract.

        Only an already-delivered ``HostEvent`` on an allowlisted topic is
        accepted. This module never emits, subscribes or opens a new bus.
        """
        if not isinstance(event, HostEvent):
            raise HostStateError("host state requires a delivered HostEvent")
        if event.topic not in TOPICS:
            raise HostStateError("unsupported host event topic")
        return cls.from_payload(event.payload)


def empty_snapshot() -> HostStateSnapshot:
    """Honest default: nothing observed, nothing granted, nothing enabled."""
    return HostStateSnapshot()


@dataclass(frozen=True)
class HostStateController:
    """Trusted adapter object whose ``view(domain)`` matches the QML contract.

    A host passes this object as ``hostState`` (or the existing ``controller``)
    on ``QuickControlsOverlay``. It exposes no action method: privileged and
    direct host changes stay the caller's responsibility and stay denied by the
    pure model.
    """

    snapshot: HostStateSnapshot

    def __post_init__(self):
        if type(self.snapshot) is not HostStateSnapshot:
            raise HostStateError("controller requires a HostStateSnapshot")

    @property
    def domains(self):
        return DOMAINS

    def view(self, domain):
        return self.snapshot.view(domain)

    def to_dict(self):
        return self.snapshot.to_dict()

    def with_snapshot(self, snapshot):
        return HostStateController(snapshot)

    @classmethod
    def from_payload(cls, payload, *, source: str = DEFAULT_SOURCE):
        return cls(HostStateSnapshot.from_payload(payload, source=source))

    @classmethod
    def from_host_event(cls, event):
        return cls(HostStateSnapshot.from_host_event(event))

    @classmethod
    def empty(cls):
        return cls(empty_snapshot())
