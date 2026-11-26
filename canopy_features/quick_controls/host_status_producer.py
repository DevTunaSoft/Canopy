"""Bounded, read-only producer of a trusted quick-controls status file.

The Classic shell already has a fail-closed controller
(``QuickControlsHostStateController::applyHostEvent``) and the pure Python
adapter ``HostStateSnapshot``. What it lacks is a trusted producer for the
three host facts this module owns: network connectivity, audio volume and
battery charging. This module composes those *already supplied* facts into the
exact bounded wire object that controller accepts, on the existing
``capabilities.report`` topic, with explicit provenance.

Safety boundary:

- No I/O, clock, randomness, threads, sockets, D-Bus, Qt, environment reads,
  process spawn or privileged operation. The returned bytes are for a trusted
  host to place at an explicit path; this module never opens a file.
- No live host probing and no invented value: a missing fact is omitted, never
  turned into ``False``, ``0``, ``"unknown"`` or a previous reading. When a
  trusted host has no status facts at all, ``unavailable()`` emits the same
  bounded topic with provenance only. The compiled controller treats that
  event as a full revocation, so an earlier reading cannot linger in the UI.
  Accidental empty ``compose()`` calls stay refused.
- ``source`` must be an explicit, allowlisted provenance token. Everything
  else (wrong types, out-of-range percentages, unlisted topics, contradictory
  provenance, oversized output) raises ``ProducerError`` before any bytes are
  returned.

This is a pure producer contract only. It does not wire the compiled shell,
does not read a real status file and is not Linux Mint, screen-reader,
accessibility or owner-visual acceptance.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from types import MappingProxyType
from typing import Optional

from canopy_core.host_events import CAPABILITIES_TOPIC

__all__ = [
    "BOOLEAN_FIELDS",
    "MAX_FILE_BYTES",
    "MAX_SOURCE_BYTES",
    "STATUS_FIELDS",
    "TOPIC",
    "TRUSTED_SOURCES",
    "WIRE_KEYS",
    "HostStatusSnapshot",
    "ProducerError",
    "HostStatusProducerError",
    "compose",
    "unavailable",
    "from_payload",
]


class ProducerError(ValueError):
    """Malformed, unbounded or untrusted status input."""


# Alias with a module-specific name for callers importing several producers.
HostStatusProducerError = ProducerError

# Reuse the existing v2 topic verbatim: no new topic, transport or field name.
TOPIC = CAPABILITIES_TOPIC

# Mirrors the compiled controller and HostStateSnapshot: percentages are exact
# ints in 0..100, booleans are exact bools, source is a bounded ASCII token.
BOOLEAN_FIELDS = ("network_connected", "battery_charging")
VOLUME_FIELD = "volume_percent"
STATUS_FIELDS = BOOLEAN_FIELDS + (VOLUME_FIELD,)
WIRE_KEYS = ("topic", "source") + STATUS_FIELDS
MAX_SOURCE_BYTES = 64
MAX_FILE_BYTES = 16 * 1024

# Provenance is explicit. "host-events" is the existing trusted delivery
# source; "host-status-file" identifies a trusted host-produced status file.
# Any other token is refused instead of being published as a host fact.
TRUSTED_SOURCES = frozenset({"host-events", "host-status-file"})


def _source(value) -> str:
    if type(value) is not str or value not in TRUSTED_SOURCES:
        raise ProducerError("status source is not a trusted provenance token")
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError:
        raise ProducerError("invalid status source encoding") from None
    if not 1 <= size <= MAX_SOURCE_BYTES:
        raise ProducerError("status source exceeds its byte bound")
    return value


@dataclass(frozen=True)
class HostStatusSnapshot:
    """Immutable projection of the three trusted facts the shell can display.

    ``None`` means "this fact was not supplied". It is never serialized and
    never interpreted as a negative observation. All fields are revalidated
    here so direct construction is as fail-closed as ``compose``. ``_absent``
    is an internal marker for the explicit ``unavailable()`` revocation event;
    it never appears on the wire and can never coexist with a fact.
    """

    source: str
    network_connected: Optional[bool] = None
    battery_charging: Optional[bool] = None
    volume_percent: Optional[int] = None
    _absent: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self):
        _source(self.source)
        if type(self._absent) is not bool:
            raise ProducerError("absence marker must be an exact bool")
        for name in BOOLEAN_FIELDS:
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise ProducerError(name + " must be an exact bool or None")
        value = self.volume_percent
        if value is not None and (
                type(value) is not int or not 0 <= value <= 100):
            raise ProducerError("volume_percent must be an int in 0..100 or None")
        facts = tuple(getattr(self, name) for name in STATUS_FIELDS)
        if self._absent and any(fact is not None for fact in facts):
            raise ProducerError("an absence event cannot carry status facts")
        if not self._absent and all(fact is None for fact in facts):
            raise ProducerError("no trusted status fact was supplied")

    @property
    def is_unavailable(self) -> bool:
        """True only for an explicit revocation of all native status facts."""
        return self._absent

    def to_dict(self):
        """Fresh read-only wire mapping; omitted facts are absent, not null."""
        payload = {"topic": TOPIC, "source": self.source}
        for name in STATUS_FIELDS:
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        return MappingProxyType({key: payload[key] for key in sorted(payload)})

    def to_json_bytes(self):
        """Serialize deterministically, enforcing the file byte cap atomically.

        No path is opened here; the caller decides where the bytes belong.
        """
        data = json.dumps(dict(self.to_dict()), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=True)
        encoded = data.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            raise ProducerError("status file exceeds its byte bound")
        return encoded


def compose(*, source, network_connected=None, battery_charging=None,
            volume_percent=None):
    """Compose explicitly supplied facts into a trusted status snapshot.

    Every argument is keyword-only and ``source`` has no default: provenance
    cannot be inferred or silently inherited. Unlike a host probe, this reads
    nothing outside the arguments; equal inputs always produce equal bytes.
    """
    return HostStatusSnapshot(
        source=source,
        network_connected=network_connected,
        battery_charging=battery_charging,
        volume_percent=volume_percent,
    )


def unavailable(*, source):
    """Explicitly revoke all native status facts on the existing topic.

    A trusted host that has no network/audio/power status to report calls this
    instead of inventing a value or leaving an old reading on screen. The wire
    object carries only the allowlisted topic and provenance; the compiled
    controller's per-event commit clears every previously supplied observation
    and detail. Provenance is required, so a hostile caller cannot silently
    turn an untrusted empty payload into a host status revocation.
    """
    return HostStatusSnapshot(source=source, _absent=True)


def from_payload(payload, *, source):
    """Project a trusted mapping of facts without inventing or echoing data.

    Only the three owned fields are read. A supplied ``topic`` must be the
    existing allowed topic and a supplied ``source`` must agree with the
    explicit argument; contradictory provenance is refused. Unreadable custom
    mappings, unhashable values and wrong container types fail closed.
    """
    if not isinstance(payload, Mapping):
        raise ProducerError("status payload must be a mapping")
    try:
        if "topic" in payload and payload["topic"] != TOPIC:
            raise ProducerError("unsupported status topic")
        if "source" in payload and payload["source"] != source:
            raise ProducerError("contradictory status provenance")
    except (KeyError, TypeError):
        raise ProducerError("unreadable status payload") from None
    values = {}
    for name in STATUS_FIELDS:
        try:
            present = name in payload
        except (KeyError, TypeError):
            raise ProducerError("unreadable status payload") from None
        if present:
            try:
                values[name] = payload[name]
            except (KeyError, TypeError):
                raise ProducerError("unreadable status field") from None
    if values:
        return compose(source=source, **values)
    # A trusted host with no facts publishes an explicit revocation rather
    # than leaving an earlier reading visible. All validation above still ran.
    return unavailable(source=source)
