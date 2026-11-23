"""Bounded, immutable, host-facing window/topology recovery snapshot.

Composes three already-tested value objects produced by independent state
models into one deterministic record:

* ``reliability/screen_topology_change.py`` -- the frozen ``RecoveryResult``
  of one observed display topology (changes, advisory actions, safe topology);
* ``windows/window_state_capabilities.py`` -- the immutable ``Negotiation``
  and the ``TransitionResult`` of one requested window-state change;
* ``windows/window_close_intents.py`` -- immutable ``IntentResult`` decisions
  for non-destructive close/reopen requests.

The snapshot is a pure composition layer: no I/O, clock, randomness, threads,
locks, OS or Qt observation. The caller hands it value objects it already
owns. Embedded collections are bounded (monitor connectors, close decisions,
text fields), every public view is immutable, and two compositions of equal
inputs are byte-for-byte identical. No caller input can make an acceptance
claim: Mint, Qt and visual acceptance stay ``NOT_ESTABLISHED`` and display
observation is always ``NOT_PERFORMED``.
"""

from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.reliability.screen_topology_change import (
    RecoveryResult, RecoveryAction, Topology,
    ACTION_NO_OP, ACTION_RELAYOUT, ACTION_REANCHOR_PRIMARY,
    ACTION_CLAMP_RESOLUTION, ACTION_SUSPEND, ACTION_RESUME,
)
from canopy_features.windows.window_state_capabilities import (
    Negotiation, TransitionResult, WindowState, WindowStateFeature,
)
from canopy_features.windows.window_close_intents import (
    IntentResult, STATUSES as CLOSE_STATUSES,
    UNKNOWN_WINDOW, OWNERSHIP_DENIED, GUARDED,
    ALREADY_CLOSED, ALREADY_OPEN,
)

SCHEMA = 1
MAX_MONITORS = 16
MAX_CLOSE_DECISIONS = 16
MAX_CHARS = 160

ACTION_KINDS = frozenset({
    ACTION_NO_OP, ACTION_RELAYOUT, ACTION_REANCHOR_PRIMARY,
    ACTION_CLAMP_RESOLUTION, ACTION_SUSPEND, ACTION_RESUME,
})
NEGOTIATION_STATUSES = frozenset({"SUPPORTED", "PARTIAL", "UNSUPPORTED"})
TRANSITION_STATUSES = frozenset({"OK", "REJECTED"})
WINDOW_STATES = frozenset(state.value for state in WindowState)
FEATURE_VALUES = frozenset(feature.value for feature in WindowStateFeature)

BLOCKING_CLOSE = frozenset({UNKNOWN_WINDOW, OWNERSHIP_DENIED, GUARDED})
SOFT_CLOSE = frozenset({ALREADY_CLOSED, ALREADY_OPEN})
BLOCKING_REJECTION = frozenset({"FEATURE_NOT_GRANTED", "INVALID_TRANSITION"})

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"


class SnapshotError(ValueError):
    """Invalid component, field or bound passed to ``compose``."""


@dataclass(frozen=True)
class DisplayView:
    """Bounded projection of one frozen ``RecoveryResult``."""

    sequence: int
    monitor_count: int
    connectors: tuple
    action_kinds: tuple
    suspended: bool


@dataclass(frozen=True)
class StateView:
    """Bounded projection of a ``Negotiation`` and ``TransitionResult``."""

    backend: str
    negotiation_status: str
    granted: tuple
    window_state: str
    transition_status: str
    transition_reason: str


@dataclass(frozen=True)
class CloseView:
    """Bounded projection of immutable close/reopen ``IntentResult`` values."""

    decision_count: int
    window_ids: tuple
    statuses: tuple
    visible_flags: tuple
    notes: tuple


@dataclass(frozen=True)
class WindowTopologySnapshot:
    """One deterministic, immutable record of host window/topology state."""

    schema: int
    status: str
    acceptance: str
    observation: str
    display: DisplayView
    state: StateView
    close: CloseView

    @property
    def is_blocked(self) -> bool:
        return self.status == STATUS_BLOCKED

    def to_dict(self):
        """Return a fresh read-only view with a fixed, stable key order."""
        return MappingProxyType({
            "schema": self.schema,
            "status": self.status,
            "acceptance": self.acceptance,
            "observation": self.observation,
            "display": MappingProxyType({
                "sequence": self.display.sequence,
                "monitor_count": self.display.monitor_count,
                "connectors": self.display.connectors,
                "action_kinds": self.display.action_kinds,
                "suspended": self.display.suspended,
            }),
            "state": MappingProxyType({
                "backend": self.state.backend,
                "negotiation_status": self.state.negotiation_status,
                "granted": self.state.granted,
                "window_state": self.state.window_state,
                "transition_status": self.state.transition_status,
                "transition_reason": self.state.transition_reason,
            }),
            "close": MappingProxyType({
                "decision_count": self.close.decision_count,
                "window_ids": self.close.window_ids,
                "statuses": self.close.statuses,
                "visible_flags": self.close.visible_flags,
                "notes": self.close.notes,
            }),
        })


def _text(value, field):
    if type(value) is not str:
        raise SnapshotError(field + " must be a string")
    return value


def _bounded_text(value, field):
    return _text(value, field)[:MAX_CHARS]


def _display_view(recovery):
    if not isinstance(recovery, RecoveryResult):
        raise SnapshotError("display must be a RecoveryResult")
    sequence = recovery.sequence
    if type(sequence) is not int or sequence < 0:
        raise SnapshotError("invalid recovery sequence")
    actions = recovery.actions
    if type(actions) is not tuple:
        raise SnapshotError("recovery actions must be a tuple")
    kinds = []
    for action in actions:
        if not isinstance(action, RecoveryAction):
            raise SnapshotError("actions must hold RecoveryAction values")
        kind = _text(action.kind, "action kind")
        if kind not in ACTION_KINDS:
            raise SnapshotError("unknown recovery action kind")
        kinds.append(kind)
    safe = recovery.safe_topology
    if not isinstance(safe, Topology):
        raise SnapshotError("safe topology must be a Topology")
    monitors = safe.monitors
    if type(monitors) is not tuple or len(monitors) > MAX_MONITORS:
        raise SnapshotError("invalid or oversized safe topology")
    connectors = sorted(safe.connectors)
    for connector in connectors:
        _bounded_text(connector, "monitor connector")
    suspended = ACTION_SUSPEND in kinds
    if suspended and monitors:
        raise SnapshotError("suspended display cannot carry monitors")
    if not suspended and not monitors:
        raise SnapshotError("non-suspended display must carry monitors")
    return DisplayView(
        sequence=sequence,
        monitor_count=len(monitors),
        connectors=tuple(connectors[:MAX_MONITORS]),
        action_kinds=tuple(kinds),
        suspended=suspended,
    )


def _state_view(negotiation, transition):
    if not isinstance(negotiation, Negotiation):
        raise SnapshotError("negotiation must be a Negotiation")
    if not isinstance(transition, TransitionResult):
        raise SnapshotError("transition must be a TransitionResult")
    backend = _bounded_text(negotiation.backend, "negotiation backend")
    if not backend:
        raise SnapshotError("negotiation backend must not be empty")
    neg_status = _text(negotiation.status, "negotiation status")
    if neg_status not in NEGOTIATION_STATUSES:
        raise SnapshotError("unsupported negotiation status")
    granted = negotiation.granted
    if type(granted) is not frozenset:
        raise SnapshotError("negotiation granted must be a frozenset")
    features = []
    for feature in granted:
        if not isinstance(feature, WindowStateFeature):
            raise SnapshotError("granted must hold WindowStateFeature values")
        features.append(feature.value)
    if neg_status == "SUPPORTED" and not features:
        raise SnapshotError("SUPPORTED negotiation must grant a feature")
    trans_status = _text(transition.status, "transition status")
    if trans_status not in TRANSITION_STATUSES:
        raise SnapshotError("unsupported transition status")
    if not isinstance(transition.state, WindowState):
        raise SnapshotError("transition state must be a WindowState")
    window_state = transition.state.value
    if window_state not in WINDOW_STATES:
        raise SnapshotError("unsupported window state")
    reason = _bounded_text(transition.reason, "transition reason")
    if neg_status == "UNSUPPORTED" and trans_status == "OK":
        raise SnapshotError("OK transition cannot follow UNSUPPORTED negotiation")
    return StateView(
        backend=backend,
        negotiation_status=neg_status,
        granted=tuple(sorted(features)),
        window_state=window_state,
        transition_status=trans_status,
        transition_reason=reason,
    )


def _close_view(decisions):
    if type(decisions) not in (tuple, list):
        raise SnapshotError("close decisions must be a sequence")
    window_ids, statuses, visible_flags, notes = [], [], [], []
    for decision in decisions[:MAX_CLOSE_DECISIONS]:
        if not isinstance(decision, IntentResult):
            raise SnapshotError("close decisions must hold IntentResult values")
        window_ids.append(_bounded_text(decision.window_id, "window id"))
        status = _text(decision.status, "close decision status")
        if status not in CLOSE_STATUSES:
            raise SnapshotError("unknown close decision status")
        statuses.append(status)
        if decision.visible is not None and type(decision.visible) is not bool:
            raise SnapshotError("close visible flag must be bool or None")
        visible_flags.append(decision.visible)
        notes.append(_bounded_text(decision.note, "close decision note"))
    return CloseView(
        decision_count=len(decisions),
        window_ids=tuple(window_ids),
        statuses=tuple(statuses),
        visible_flags=tuple(visible_flags),
        notes=tuple(notes),
    )


def _derive_status(display, state, close):
    # A suspended display, an unsupported negotiation, a hard close refusal or
    # a rejected transition for a missing/invalid action blocks the record.
    # A clamped resolution, partial negotiation, soft close no-op or any other
    # rejection is attention-worthy but still a usable snapshot. This status
    # describes only the supplied state, never a running desktop (there is no
    # acceptance field to flip).
    if (display.suspended
            or state.negotiation_status == "UNSUPPORTED"
            or any(status in BLOCKING_CLOSE for status in close.statuses)
            or (state.transition_status == "REJECTED"
                and state.transition_reason in BLOCKING_REJECTION)):
        return STATUS_BLOCKED
    if (ACTION_CLAMP_RESOLUTION in display.action_kinds
            or state.negotiation_status == "PARTIAL"
            or state.transition_status == "REJECTED"
            or any(status in SOFT_CLOSE for status in close.statuses)):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(recovery, negotiation, transition, close_decisions=()):
    """Compose three already-tested value objects into one immutable record.

    Every rejected input raises ``SnapshotError`` before any record is built,
    so no partial snapshot escapes. Embedded collections are capped; the
    original value objects are never copied wholesale or mutated.
    """
    display = _display_view(recovery)
    state = _state_view(negotiation, transition)
    close = _close_view(close_decisions)
    return WindowTopologySnapshot(
        schema=SCHEMA,
        status=_derive_status(display, state, close),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        observation=OBSERVATION_NOT_PERFORMED,
        display=display,
        state=state,
        close=close,
    )
