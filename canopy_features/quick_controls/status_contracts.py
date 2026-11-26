"""Bounded audio/network/power quick-controls status contracts.

This module is a narrow, fail-closed projection at the *existing* trusted
source boundary. It consumes only an already-validated
:class:`canopy_features.quick_controls.host_status_producer.HostStatusSnapshot`
(a trusted host's network/volume/battery facts on the existing
``capabilities.report`` contract) and trusted
:class:`canopy_features.system.quick_controls_state.Observation` records for
the audio mute state. It produces immutable, bounded per-domain status records
using the existing ``STATUS_TOKENS`` and ``STATUS_LABELS`` vocabulary.

No new event topic, wire field, UI token, disclosure, transport or control
action is introduced. No topic/field is sent anywhere; the returned records
are values for a trusted caller to display or re-emit on the existing bus.

Safety boundary:

- No I/O, clock, randomness, threads, sockets, D-Bus, Qt, VM, environment
  reads, process spawn or privileged operation. No real device, audio server,
  NetworkManager, UPower or guest is probed. Missing facts stay ``unknown``;
  they are never turned into ``False``, ``0`` or a previous reading.
- Provenance is explicit: the aggregate source must be an allowlisted
  ``host-status-producer`` token and every trusted observation must agree with
  it. An explicit absence event cannot coexist with an observation.
- Volume detail is bounded (exact ``int`` in ``0..100``) and never used to
  infer a mute status: volume zero is not a mute fact.
- Wrong types, duplicate/non-audio observations, contradictory provenance,
  unreadable inputs and oversized output raise :class:`StatusContractError`
  before any snapshot is returned.

This is a pure contract only. It does not wire the compiled shell, change a
control, read a host service or claim Linux Mint, screen-reader, accessibility
or owner-visual acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Optional

from canopy_features.quick_controls import host_status_producer as producer
from canopy_features.system.quick_controls_state import (
    Observation,
    STATUS_LABELS,
    STATUS_TOKENS,
)

__all__ = [
    "DOMAINS",
    "KNOWN_STATUSES",
    "MAX_JSON_BYTES",
    "MAX_OBSERVATIONS",
    "TRUSTED_SOURCES",
    "UNKNOWN",
    "VOLUME_DETAIL",
    "StatusContractError",
    "StatusRecord",
    "StatusSnapshot",
    "from_payload",
    "from_snapshot",
    "unavailable",
]


class StatusContractError(ValueError):
    """Invalid, unbounded, contradictory or untrusted status input."""


# Fixed display order; session is deliberately out of scope for PE-099.
DOMAINS = ("audio", "network", "power")
UNKNOWN = "unknown"
VOLUME_DETAIL = "volume"
KNOWN_STATUSES = MappingProxyType({
    "audio": frozenset({"muted", "unmuted"}),
    "network": frozenset({"connected", "disconnected"}),
    "power": frozenset({"charging", "discharging"}),
})
MAX_OBSERVATIONS = 8
MAX_JSON_BYTES = 4096

# Reuse the producer's provenance allowlist; do not invent a second boundary.
TRUSTED_SOURCES = producer.TRUSTED_SOURCES

# Contract guards: the vocabulary and labels must remain those of the existing
# quick-controls state model. A drift fails loudly instead of inventing UI text.
def _check_vocabulary() -> None:
    for domain in DOMAINS:
        allowed = KNOWN_STATUSES[domain] | {UNKNOWN}
        if not allowed <= STATUS_TOKENS[domain]:
            raise RuntimeError("quick-controls status vocabulary changed")
        if any(label not in STATUS_LABELS for label in allowed):
            raise RuntimeError("quick-controls status labels changed")


_check_vocabulary()


def _source(value) -> str:
    if type(value) is not str or value not in TRUSTED_SOURCES:
        raise StatusContractError("status source is not a trusted token")
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError:
        raise StatusContractError("invalid status source encoding") from None
    if not 1 <= size <= producer.MAX_SOURCE_BYTES:
        raise StatusContractError("status source exceeds its byte bound")
    return value


@dataclass(frozen=True)
class StatusRecord:
    """One bounded domain status; ``observed`` is derived, never supplied."""

    domain: str
    status: str
    detail_kind: Optional[str] = None
    detail_value: Optional[int] = None

    def __post_init__(self):
        if type(self.domain) is not str or self.domain not in DOMAINS:
            raise StatusContractError("invalid status domain")
        allowed = KNOWN_STATUSES[self.domain] | {UNKNOWN}
        if type(self.status) is not str or self.status not in allowed:
            raise StatusContractError("unsupported status token")
        if self.detail_kind is None:
            if self.detail_value is not None:
                raise StatusContractError("detail value without a detail kind")
            return
        if (self.domain != "audio" or type(self.detail_kind) is not str
                or self.detail_kind != VOLUME_DETAIL):
            raise StatusContractError("unsupported status detail kind")
        if (type(self.detail_value) is not int
                or not 0 <= self.detail_value <= 100):
            raise StatusContractError("status detail exceeds its bound")

    @property
    def observed(self) -> bool:
        """True only when a trusted status token was actually supplied."""
        return self.status != UNKNOWN

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    def to_dict(self):
        return MappingProxyType({
            "domain": self.domain,
            "status": self.status,
            "status_label": self.status_label,
            "observed": self.observed,
            "detail_kind": self.detail_kind,
            "detail_value": self.detail_value,
        })


@dataclass(frozen=True)
class StatusSnapshot:
    """Immutable, exactly-three-domain snapshot of trusted status facts."""

    source: str
    records: tuple

    def __post_init__(self):
        _source(self.source)
        if (type(self.records) is not tuple
                or len(self.records) != len(DOMAINS)):
            raise StatusContractError("status records must be an exact tuple")
        domains = []
        for record in self.records:
            if type(record) is not StatusRecord:
                raise StatusContractError("status record has wrong type")
            domains.append(record.domain)
        if tuple(domains) != DOMAINS:
            raise StatusContractError("status records must be unique and ordered")

    def record(self, domain):
        if type(domain) is not str or domain not in DOMAINS:
            raise StatusContractError("invalid status domain")
        for record in self.records:
            if record.domain == domain:
                return record
        raise StatusContractError("status domain is absent")  # pragma: no cover

    def to_dict(self):
        return MappingProxyType({
            "source": self.source,
            "domains": MappingProxyType({
                record.domain: record.to_dict() for record in self.records
            }),
        })

    def to_json_bytes(self):
        """Deterministic compact ASCII JSON with an enforced byte cap."""
        payload = {
            "source": self.source,
            "domains": {record.domain: dict(record.to_dict())
                        for record in self.records},
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode("utf-8")
        if len(encoded) > MAX_JSON_BYTES:
            raise StatusContractError("status snapshot exceeds its byte bound")
        return encoded

    def as_observations(self):
        """Reuse the existing Observation model for domains with a real token."""
        return tuple(Observation(record.domain, record.status, self.source)
                     for record in self.records if record.observed)


def from_snapshot(snapshot, *, observations=()):
    """Project a trusted producer snapshot plus trusted audio observations."""
    if type(snapshot) is not producer.HostStatusSnapshot:
        raise StatusContractError("snapshot must be a trusted producer snapshot")
    if type(observations) not in (tuple, list):
        raise StatusContractError("observations must be a tuple or list")
    if len(observations) > MAX_OBSERVATIONS:
        raise StatusContractError("too many status observations")

    audio_status = UNKNOWN
    audio_supplied = False
    for observation in observations:
        if type(observation) is not Observation:
            raise StatusContractError("observation has wrong type")
        if observation.domain != "audio":
            raise StatusContractError("only audio status observations are owned")
        if observation.status not in KNOWN_STATUSES["audio"]:
            raise StatusContractError("unsupported audio status observation")
        if observation.source != snapshot.source:
            raise StatusContractError("contradictory status provenance")
        if audio_supplied:
            raise StatusContractError("duplicate audio status observation")
        audio_supplied = True
        audio_status = observation.status

    if snapshot.is_unavailable:
        if audio_supplied:
            raise StatusContractError("an absence event cannot carry a status")
        records = tuple(StatusRecord(domain, UNKNOWN) for domain in DOMAINS)
        return StatusSnapshot(snapshot.source, records)

    connected = snapshot.network_connected
    network_status = (UNKNOWN if connected is None else
                      "connected" if connected else "disconnected")
    charging = snapshot.battery_charging
    power_status = (UNKNOWN if charging is None else
                    "charging" if charging else "discharging")
    volume = snapshot.volume_percent
    detail_kind = VOLUME_DETAIL if volume is not None else None

    records = (
        StatusRecord("audio", audio_status, detail_kind, volume),
        StatusRecord("network", network_status),
        StatusRecord("power", power_status),
    )
    return StatusSnapshot(snapshot.source, records)


def from_payload(payload, *, source, observations=()):
    """Project a trusted source mapping through the existing producer gate."""
    try:
        snapshot = producer.from_payload(payload, source=source)
    except producer.ProducerError as exc:
        raise StatusContractError(str(exc)) from None
    return from_snapshot(snapshot, observations=observations)


def unavailable(*, source):
    """Explicitly report that no audio/network/power status was supplied."""
    try:
        snapshot = producer.unavailable(source=source)
    except producer.ProducerError as exc:
        raise StatusContractError(str(exc)) from None
    return from_snapshot(snapshot)
