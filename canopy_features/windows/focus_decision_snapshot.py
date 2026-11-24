"""Bounded, immutable, host-facing focus-decision snapshot.

Composes three already-tested value objects produced by independent windows
state models into one deterministic record:

* ``windows/focus_intents.py`` -- the deny-by-default focus broker's bounded
  decision history, live window count and optional explicit ``PermissionPolicy``;
* ``windows/workspace_inventory.py`` -- the canonical workspace identifiers and
  skipped-record notes from one permitted-source snapshot;
* ``windows/switcher_state.py`` -- the frozen ``SwitchState`` view of keyboard
  window selection.

This is a pure composition layer: no I/O, clock, randomness, threads, locks,
polling, OS or Qt observation. The caller hands it value objects it already
owns. Embedded collections are bounded (recent decisions, workspace
identifiers and problem notes, switcher order, text), every public view is
immutable, and two compositions of equal inputs are byte-for-byte identical.
No caller input can make an acceptance or event-observation claim: acceptance
is always ``NOT_ESTABLISHED`` and observation always ``NOT_PERFORMED``.

The status describes only the supplied state, never a running desktop.
"""
from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.windows.focus_intents import (
    ACTIVATION_FAILED, DENIED, GRANTED, STALE_TARGET, UNKNOWN_TARGET,
    FocusBroker, FocusDecision, PermissionPolicy)
from canopy_features.windows.switcher_state import SwitchState
from canopy_features.windows.workspace_inventory import (
    Workspace, WorkspaceInventory, WorkspaceProblem)

SCHEMA = 1
MAX_DECISIONS = 16
MAX_WORKSPACES = 64
MAX_PROBLEMS = 32
MAX_WINDOWS = 64
MAX_CHARS = 160
MAX_ID_LENGTH = 128
MAX_WINDOW_ID = 1_000_000_000_000

FOCUS_FAILURE = frozenset({
    DENIED, STALE_TARGET, UNKNOWN_TARGET, ACTIVATION_FAILED})
FOCUS_STATUSES = frozenset({GRANTED} | FOCUS_FAILURE)

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"


class SnapshotError(ValueError):
    """Invalid component, field or bound passed to ``compose``."""


@dataclass(frozen=True)
class FocusView:
    """Bounded projection of a focus broker and optional permission policy."""

    live_windows: int
    grant_count: object
    decision_count: int
    statuses: tuple
    target_apps: tuple
    reasons: tuple


@dataclass(frozen=True)
class WorkspaceView:
    """Bounded projection of a canonical ``WorkspaceInventory``."""

    workspace_count: int
    identifiers: tuple
    problem_count: int
    problem_reasons: tuple


@dataclass(frozen=True)
class SwitcherView:
    """Bounded projection of a frozen ``SwitchState`` view."""

    active: bool
    current: object
    selected: object
    window_count: int
    order: tuple


@dataclass(frozen=True)
class FocusDecisionSnapshot:
    """One deterministic, immutable record of host focus-decision state."""

    schema: int
    status: str
    acceptance: str
    observation: str
    focus: FocusView
    workspace: WorkspaceView
    switcher: SwitcherView

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
            "focus": MappingProxyType({
                "live_windows": self.focus.live_windows,
                "grant_count": self.focus.grant_count,
                "decision_count": self.focus.decision_count,
                "statuses": self.focus.statuses,
                "target_apps": self.focus.target_apps,
                "reasons": self.focus.reasons,
            }),
            "workspace": MappingProxyType({
                "workspace_count": self.workspace.workspace_count,
                "identifiers": self.workspace.identifiers,
                "problem_count": self.workspace.problem_count,
                "problem_reasons": self.workspace.problem_reasons,
            }),
            "switcher": MappingProxyType({
                "active": self.switcher.active,
                "current": self.switcher.current,
                "selected": self.switcher.selected,
                "window_count": self.switcher.window_count,
                "order": self.switcher.order,
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
    statuses, target_apps, reasons = [], [], []
    for decision in history[-MAX_DECISIONS:]:
        if not isinstance(decision, FocusDecision):
            raise SnapshotError("focus history must hold FocusDecision values")
        status = _text(decision.status, "focus decision status")
        if status not in FOCUS_STATUSES:
            raise SnapshotError("unsupported focus decision status")
        target = decision.target_app
        if target is not None:
            target = _bounded_text(target, "focus target app")
        statuses.append(status)
        target_apps.append(target)
        reasons.append(_bounded_text(decision.reason, "focus decision reason"))
    return FocusView(
        live_windows=_count(broker.live_window_count, "focus live window count"),
        grant_count=(None if policy is None
                     else _count(policy.grant_count, "focus grant count")),
        decision_count=len(history),
        statuses=tuple(statuses),
        target_apps=tuple(target_apps),
        reasons=tuple(reasons),
    )


def _workspace_view(inventory):
    if not isinstance(inventory, WorkspaceInventory):
        raise SnapshotError("workspace must be a WorkspaceInventory")
    workspaces = inventory.workspaces
    problems = inventory.problems
    if type(workspaces) is not tuple or type(problems) is not tuple:
        raise SnapshotError("workspace records and problems must be tuples")
    identifiers = []
    for workspace in workspaces[:MAX_WORKSPACES]:
        if not isinstance(workspace, Workspace):
            raise SnapshotError("workspace records must be Workspace values")
        identifier = _bounded_text(workspace.identifier, "workspace identifier")
        if not identifier:
            raise SnapshotError("workspace identifier must not be empty")
        _bounded_text(workspace.name, "workspace name")
        _bounded_text(workspace.source, "workspace source")
        identifiers.append(identifier)
    reasons = []
    for problem in problems[:MAX_PROBLEMS]:
        if not isinstance(problem, WorkspaceProblem):
            raise SnapshotError("problems must hold WorkspaceProblem entries")
        _bounded_text(problem.location, "problem location")
        reasons.append(_bounded_text(problem.reason, "problem reason"))
    return WorkspaceView(
        workspace_count=len(workspaces),
        identifiers=tuple(identifiers),
        problem_count=len(problems),
        problem_reasons=tuple(reasons),
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


def _derive_status(focus, workspace, switcher):
    # Any failed focus decision blocks the record; it outranks the softer
    # attention conditions. Recorded decisions, skipped workspace records,
    # cross-app grants and no tracked window are attention-worthy but leave a
    # usable snapshot. This status describes only the supplied state; there is
    # no acceptance field to flip.
    if any(status in FOCUS_FAILURE for status in focus.statuses):
        return STATUS_BLOCKED
    if (focus.statuses or workspace.problem_count
            or switcher.window_count == 0 or focus.grant_count):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(focus, workspace, switcher, policy=None):
    """Compose three already-tested value objects into one immutable record.

    Every component is validated before any record is built, so a rejected
    input raises ``SnapshotError`` without a partial result. Embedded
    collections are bounded; the source objects are never mutated. ``policy``
    is optional and is recorded as ``grant_count=None`` when omitted.
    """
    focus_view = _focus_view(focus, policy)
    workspace_view = _workspace_view(workspace)
    switcher_view = _switcher_view(switcher)
    return FocusDecisionSnapshot(
        schema=SCHEMA,
        status=_derive_status(focus_view, workspace_view, switcher_view),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        observation=OBSERVATION_NOT_PERFORMED,
        focus=focus_view,
        workspace=workspace_view,
        switcher=switcher_view,
    )
