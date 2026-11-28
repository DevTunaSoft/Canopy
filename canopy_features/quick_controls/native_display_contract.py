"""Bounded wire contract for native Plasma display host wiring.

This is the authoritative Python side of the contract implemented by
``NativeDisplayHostBridge`` in ``prototype/classic/main.cpp``. A trusted host
that already owns a real Qt/KWin screen signal delivers one bounded snapshot
or one logical-DPI signal; this module adapts it to the existing pure
contracts (``ScreenTopologyModel``, ``DisplayChangeResponse``) and returns one
JSON-serializable plan. It never observes hardware, imports Qt, opens a file,
starts a service, polls or guesses a value.

The compiled host consumes the same wire shape directly from Qt screen signals
without a Python process: both sides are checked against the canonical vectors
in ``scratch/native_host_wiring/`` (SYNTHETIC parity gate, never a runtime
claim).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re

from canopy_core.host_events import TOPICS
from canopy_features.dock.display_change_response import (
    EVENT_DPI_CHANGED,
    KIND_HOLD,
    KIND_NO_OP,
    KIND_RELAYOUT,
    KIND_SUSPEND,
    MAX_HISTORY,
    ROOT_HEIGHT,
    ROOT_WIDTH,
    DisplayChangeResponse,
)
from canopy_features.dock.display_scaling_contract import (
    MAX_SCALE,
    REASON_LOGICAL_DPI_CHANGED,
    REASON_LOGICAL_SIZE_UNCHANGED,
)
from canopy_features.reliability.screen_topology_change import (
    MAX_CONNECTOR_LEN,
    MAX_MONITORS,
    Monitor,
    ScreenTopologyModel,
    Topology,
)

__all__ = [
    "ALLOWED_ENTRY_POINTS",
    "ALLOWED_PLAN_KINDS",
    "CONNECTOR",
    "MAX_CONNECTORS",
    "MAX_SOURCE_BYTES",
    "REASONS",
    "SOURCE_QT_SCREEN",
    "WIRE_VERSION",
    "NativeDisplayContractError",
    "ScreenObservation",
    "NativeDisplayProducer",
    "plan_from_wire",
    "plan_to_wire",
]

WIRE_VERSION = 1
SOURCE_QT_SCREEN = "qt.screen"
MAX_SOURCE_BYTES = 64
MAX_CONNECTORS = MAX_MONITORS
CONNECTOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,%d}\Z" % (MAX_CONNECTOR_LEN - 1))
ALLOWED_ENTRY_POINTS = frozenset({"recovery", "dpi"})
ALLOWED_PLAN_KINDS = frozenset({
    KIND_RELAYOUT, KIND_HOLD, KIND_SUSPEND, KIND_NO_OP,
})
REASONS = frozenset({
    "resolution_changed", "primary_changed", "connect", "disconnect",
    "no_display", "below_minimum", "unsafe_geometry", "invalid_event",
    "unchanged", REASON_LOGICAL_DPI_CHANGED, REASON_LOGICAL_SIZE_UNCHANGED,
})


class NativeDisplayContractError(ValueError):
    """Malformed or untrusted native host input; refused before any commit."""


def _source(value):
    if type(value) is not str or not 1 <= len(value) <= MAX_SOURCE_BYTES:
        raise NativeDisplayContractError("invalid display source")
    if not re.fullmatch(r"[a-z0-9_.:-]+", value):
        raise NativeDisplayContractError("invalid display source token")
    return value


def _connector(value):
    if type(value) is not str or not CONNECTOR.fullmatch(value):
        raise NativeDisplayContractError("invalid monitor connector")
    return value


@dataclass(frozen=True)
class ScreenObservation:
    """One trusted, bounded Qt screen snapshot.

    ``connectors`` are the names of all present screens; ``primary`` is one of
    them (or ``None`` when no screen is present). ``width``/``height`` are
    *logical* pixels of the primary screen. Nothing here is observed by this
    module: the caller supplies values it already received from Qt/KWin.
    """

    connectors: tuple
    primary: str | None
    width: int | None
    height: int | None
    source: str = SOURCE_QT_SCREEN

    def __post_init__(self):
        if type(self.connectors) not in (tuple, list):
            raise NativeDisplayContractError("connectors must be a sequence")
        if len(self.connectors) > MAX_CONNECTORS:
            raise NativeDisplayContractError("too many monitors")
        checked = tuple(_connector(name) for name in self.connectors)
        if len(set(checked)) != len(checked):
            raise NativeDisplayContractError("duplicate monitor connector")
        object.__setattr__(self, "connectors", tuple(sorted(checked)))
        if self.primary is not None:
            _connector(self.primary)
            if self.primary not in self.connectors:
                raise NativeDisplayContractError("primary is not present")
        elif checked:
            raise NativeDisplayContractError("nonempty topology needs a primary")
        for name, limit in (("width", 7680), ("height", 4320)):
            value = getattr(self, name)
            if checked and (type(value) is not int
                            or not 1 <= value <= limit):
                raise NativeDisplayContractError("invalid primary geometry")
            if not checked and value is not None:
                raise NativeDisplayContractError("empty topology cannot carry size")
        _source(self.source)

    @classmethod
    def from_payload(cls, payload):
        """Adapt a trusted mapping without inventing or echoing any field."""
        if not isinstance(payload, Mapping):
            raise NativeDisplayContractError("screen payload must be a mapping")
        try:
            names = payload.get("connectors", ())
            primary = payload.get("primary")
            width = payload.get("width")
            height = payload.get("height")
            source = payload.get("source", SOURCE_QT_SCREEN)
        except (KeyError, TypeError):
            raise NativeDisplayContractError("unreadable screen payload") from None
        return cls(tuple(names), primary, width, height, source)

    def topology(self):
        if not self.connectors:
            return Topology(())
        monitors = []
        for name in self.connectors:
            if name == self.primary:
                monitors.append(Monitor(name, self.width, self.height, True))
            else:
                # Secondary geometry is not needed for the Classic primary
                # relayout decision; use a supported bounded placeholder.
                monitors.append(Monitor(name, 1920, 1080, False))
        return Topology(monitors)


def plan_to_wire(plan, source=SOURCE_QT_SCREEN):
    """One bounded, JSON-serializable plan on the shared wire shape."""
    _source(source)
    if plan.kind not in ALLOWED_PLAN_KINDS or plan.reason not in REASONS:
        raise NativeDisplayContractError("plan outside the shared contract")
    return {
        "version": WIRE_VERSION,
        "sequence": int(plan.sequence),
        "kind": plan.kind,
        "width": int(plan.size[0]),
        "height": int(plan.size[1]),
        "reason": plan.reason,
        "source": source,
    }


def plan_from_wire(payload):
    """Decode a wire plan without trusting extra caller fields."""
    if not isinstance(payload, Mapping):
        raise NativeDisplayContractError("wire plan must be a mapping")
    if payload.get("version") != WIRE_VERSION:
        raise NativeDisplayContractError("unsupported wire version")
    kind = payload.get("kind")
    reason = payload.get("reason")
    if kind not in ALLOWED_PLAN_KINDS or reason not in REASONS:
        raise NativeDisplayContractError("wire plan outside the shared contract")
    sequence = payload.get("sequence")
    size = (payload.get("width"), payload.get("height"))
    if (type(sequence) is not int or sequence < 1
            or any(type(v) is not int or v <= 0 for v in size)):
        raise NativeDisplayContractError("invalid wire plan bounds")
    if max(size) > 7680 or size[1] > 4320:
        raise NativeDisplayContractError("wire plan exceeds display bounds")
    return {
        "version": WIRE_VERSION,
        "sequence": sequence,
        "kind": kind,
        "width": size[0],
        "height": size[1],
        "reason": reason,
        "source": _source(payload.get("source")),
    }


class NativeDisplayProducer:
    """Single-owner, event-driven adapter for one trusted display host.

    Holds one bounded ``ScreenTopologyModel`` and one ``DisplayChangeResponse``.
    No bus, timer, process, socket or service is created: the host calls one
    entry point only when a real screen signal has been delivered.
    """

    def __init__(self):
        self._topology = ScreenTopologyModel()
        self._response = DisplayChangeResponse()

    @property
    def topics(self):
        """Read-only alias: no new host-event topic is introduced."""
        return TOPICS

    def apply_recovery(self, observation):
        """Adapt one frozen Qt screen snapshot through the recovery contract.

        Hostile observed data fails closed as an ``invalid_event`` hold; it is
        never allowed to escape and kill the shell's signal handler.
        """
        try:
            if not isinstance(observation, ScreenObservation):
                observation = ScreenObservation.from_payload(observation)
            result = self._topology.apply(observation.topology())
            plan = self._response.handle_recovery_result(result)
            source = observation.source
        except Exception:
            plan = self._response.handle(None)
            source = SOURCE_QT_SCREEN
        return plan_to_wire(plan, source)

    def apply_logical_dpi(self, physical_width, physical_height, scale,
                          connector=None, source=SOURCE_QT_SCREEN):
        """Adapt one real logical-DPI signal through the scaling contract."""
        try:
            if connector is not None:
                _connector(connector)
            plan = self._response.handle_logical_dpi_change(
                physical_width, physical_height, scale, connector=connector)
            return plan_to_wire(plan, source)
        except Exception:
            return plan_to_wire(self._response.handle(None), source)

    @property
    def last_safe_size(self):
        return self._response.last_safe_size

    @property
    def history(self):
        return self._response.history[:MAX_HISTORY]
