"""Bounded, immutable, host-facing close/reopen lifecycle snapshot.

Composes three already-tested value objects produced by independent windows
state models into one deterministic record:

* ``windows/window_close_intents.py`` -- the owner/check/park/reopen decisions
  and the count of registered host-owned windows;
* ``windows/switcher_state.py`` -- the frozen ``SwitchState`` view of keyboard
  window selection;
* ``windows/focus_intents.py`` -- the deny-by-default focus broker's bounded
  decision history and an optional explicit ``PermissionPolicy``.

This is a pure composition layer: no I/O, clock, randomness, threads, locks,
polling, OS or Qt observation. The caller hands it value objects it already
owns. Embedded collections are bounded (recent decisions, switcher order,
text), every public view is immutable, and two compositions of equal inputs
are byte-for-byte identical. No caller input can make an acceptance or event-
observation claim: acceptance is always ``NOT_ESTABLISHED`` and observation
always ``NOT_PERFORMED``.

The status describes only the supplied state, never a running desktop.
"""
from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.windows.focus_intents import (
    ACTIVATION_FAILED, DENIED, STALE_TARGET, UNKNOWN_TARGET,
    FocusBroker, FocusDecision, PermissionPolicy)
from canopy_features.windows.switcher_state import SwitchState
from canopy_features.windows.window_close_intents import (
    ALREADY_CLOSED, ALREADY_OPEN, GUARDED, OWNERSHIP_DENIED, UNKNOWN_WINDOW,
    STATUSES as CLOSE_STATUSES, CloseIntentModel, IntentResult)

SCHEMA = 1
MAX_DECISIONS = 16
MAX_WINDOWS = 64
MAX_CHARS = 160
MAX_ID_LENGTH = 128
MAX_WINDOW_ID = 1_000_000_000_000

BLOCKING_CLOSE = frozenset({UNKNOWN_WINDOW, OWNERSHIP_DENIED, GUARDED})
SOFT_CLOSE = frozenset({ALREADY_CLOSED, ALREADY_OPEN})
FOCUS_FAILURE = frozenset({
    DENIED, STALE_TARGET, UNKNOWN_TARGET, ACTIVATION_FAILED})
FOCUS_STATUSES = frozenset({
    "GRANTED", DENIED, STALE_TARGET, UNKNOWN_TARGET, ACTIVATION_FAILED})

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"


class SnapshotError(ValueError):
    """Invalid component, field or bound passed to ``compose``."""


@dataclass(frozen=True)
class CloseView:
    """Bounded projection of close/reopen decisions and registered windows."""

    registered_count: int
    decision_count: int
    window_ids: tuple
    statuses: tuple
    visible_flags: tuple
    notes: tuple


@dataclass(frozen=True)
class SwitcherView:
    """Bounded projection of a frozen ``SwitchState`` view."""

    active: bool
    current: object
    selected: object
    window_count: int
    order: tuple


@dataclass(frozen=True)
class FocusView:
    """Bounded projection of a focus broker and optional permission policy."""

    live_windows: int
    grant_count: object
    recent_statuses: tuple


@dataclass(frozen=True)
class CloseLifecycleSnapshot:
    """One deterministic, immutable record of close/reopen lifecycle state."""

    schema: int
    status: str
    acceptance: str
    observation: str
    close: CloseView
    switcher: SwitcherView
    focus: FocusView

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
            "close": MappingProxyType({
                "registered_count": self.close.registered_count,
                "decision_count": self.close.decision_count,
                "window_ids": self.close.window_ids,
                "statuses": self.close.statuses,
                "visible_flags": self.close.visible_flags,
                "notes": self.close.notes,
            }),
            "switcher": MappingProxyType({
                "active": self.switcher.active,
                "current": self.switcher.current,
                "selected": self.switcher.selected,
                "window_count": self.switcher.window_count,
                "order": self.switcher.order,
            }),
            "focus": MappingProxyType({
                "live_windows": self.focus.live_windows,
                "grant_count": self.focus.grant_count,
                "recent_statuses": self.focus.recent_statuses,
            }),
        })


def _count(value, field):
    if type(value) is not int or value < 0:
        raise SnapshotError(field + " must be a non-negative int")
    return value


def _flag(value, field):
    if type(value) is not bool:
        raise SnapshotError(field + " must be a bool")
    return value


def _text(value, field):
    if type(value) is not str:
        raise SnapshotError(field + " must be a string")
    return value


def _bounded_text(value, field):
    return _text(value, field)[:MAX_CHARS]


def _close_view(model, decisions):
    if not isinstance(model, CloseIntentModel):
        raise SnapshotError("close must be a CloseIntentModel")
    if type(decisions) not in (tuple, list):
        raise SnapshotError("close decisions must be a sequence")
    window_ids, statuses, visible_flags, notes = [], [], [], []
    for decision in decisions[-MAX_DECISIONS:]:
        if not isinstance(decision, IntentResult):
            raise SnapshotError("close decisions must hold IntentResult values")
        window_id = _bounded_text(decision.window_id, "close window id")
        if not window_id or len(window_id) > MAX_ID_LENGTH:
            raise SnapshotError("close window id is empty or too long")
        status = _text(decision.status, "close decision status")
        if status not in CLOSE_STATUSES:
            raise SnapshotError("unknown close decision status")
        visible = decision.visible
        if visible is not None and type(visible) is not bool:
            raise SnapshotError("close visible flag must be bool or None")
        window_ids.append(window_id)
        statuses.append(status)
        visible_flags.append(visible)
        notes.append(_bounded_text(decision.note, "close decision note"))
    return CloseView(
        registered_count=_count(model.window_count, "registered window count"),
        decision_count=len(decisions),
        window_ids=tuple(window_ids),
        statuses=tuple(statuses),
        visible_flags=tuple(visible_flags),
        notes=tuple(notes),
    )


def _switcher_view(state):
    if not isinstance(state, SwitchState):
        raise SnapshotError("switcher must be a SwitchState")
    order = state.order
    if type(order) is not tuple:
        raise SnapshotError("switcher order must be a tuple")
    for item in order:
        _window_id(item)
    return SwitcherView(
        active=_flag(state.active, "switcher active"),
        current=_window_id(state.current),
        selected=_window_id(state.selected),
        window_count=len(order),
        order=order[:MAX_WINDOWS],
    )


def _window_id(value):
    if value is None:
        return None
    if type(value) is bool:
        raise SnapshotError("invalid window id in switcher view")
    if type(value) is int and 0 < value <= MAX_WINDOW_ID:
        return value
    if type(value) is str and 0 < len(value) <= MAX_ID_LENGTH:
        return value
    raise SnapshotError("invalid window id in switcher view")


def _focus_view(broker, policy):
    if not isinstance(broker, FocusBroker):
        raise SnapshotError("focus must be a FocusBroker")
    if policy is not None and not isinstance(policy, PermissionPolicy):
        raise SnapshotError("policy must be a PermissionPolicy or None")
    history = broker.history
    if type(history) is not tuple:
        raise SnapshotError("focus history must be a tuple")
    statuses = []
    for decision in history[-MAX_DECISIONS:]:
        if not isinstance(decision, FocusDecision):
            raise SnapshotError("focus history must hold FocusDecision values")
        status = _text(decision.status, "focus decision status")
        if status not in FOCUS_STATUSES:
            raise SnapshotError("unsupported focus decision status")
        statuses.append(status)
    return FocusView(
        live_windows=_count(broker.live_window_count, "focus live window count"),
        grant_count=(None if policy is None
                     else _count(policy.grant_count, "focus grant count")),
        recent_statuses=tuple(statuses),
    )


def _derive_status(close, switcher, focus):
    # A hard close refusal (unknown window, ownership denial or owner guard)
    # or a failed focus decision blocks the record. A parked/reopened window,
    # soft no-ops, cross-app grants, any decision history or no tracked window
    # is attention-worthy but still a usable snapshot. This status describes
    # only the supplied state; there is no acceptance field to flip.
    if (any(status in BLOCKING_CLOSE for status in close.statuses)
            or any(status in FOCUS_FAILURE for status in focus.recent_statuses)):
        return STATUS_BLOCKED
    if (close.statuses or focus.recent_statuses
            or switcher.window_count == 0 or focus.grant_count):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(close_model, switcher, focus, decisions=(), policy=None):
    """Compose three already-tested value objects into one immutable record.

    ``decisions`` is the bounded tuple/list of ``IntentResult`` values emitted
    by the close model; only the most recent ``MAX_DECISIONS`` entries are
    embedded. ``policy`` is optional. Every component is validated before any
    record is built, so a rejected input raises ``SnapshotError`` without a
    partial result. The source objects are never mutated.
    """
    close_view = _close_view(close_model, decisions)
    switcher_view = _switcher_view(switcher)
    focus_view = _focus_view(focus, policy)
    return CloseLifecycleSnapshot(
        schema=SCHEMA,
        status=_derive_status(close_view, switcher_view, focus_view),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        observation=OBSERVATION_NOT_PERFORMED,
        close=close_view,
        switcher=switcher_view,
        focus=focus_view,
    )
