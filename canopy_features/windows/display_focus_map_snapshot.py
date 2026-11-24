"""Bounded, immutable, host-facing display/workspace/focus map snapshot.

Composes three already-tested value objects produced by independent models
into one deterministic record:

* ``reliability/screen_topology_change.py`` -- the frozen ``RecoveryResult`` of
  one observed display topology;
* ``windows/workspace_inventory.py`` -- canonical workspace identifiers and
  skipped-record notes;
* ``windows/focus_intents.py`` -- the deny-by-default focus broker's bounded
  decision history and live window count.

Pure composition layer: no I/O, clock, randomness, threads, locks, polling,
OS or Qt observation. The caller hands it value objects it already owns.
Embedded collections are bounded, every public view is immutable, and two
compositions of equal inputs are byte-for-byte identical. No caller input can
make an acceptance or real-observation claim: acceptance is always
``NOT_ESTABLISHED`` and observation always ``NOT_PERFORMED``.
"""
from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.reliability.screen_topology_change import (
    ACTION_CLAMP_RESOLUTION, ACTION_SUSPEND, RecoveryAction, RecoveryResult,
    Topology)
from canopy_features.windows.focus_intents import (
    ACTIVATION_FAILED, DENIED, STALE_TARGET, UNKNOWN_TARGET,
    FocusBroker, FocusDecision)
from canopy_features.windows.workspace_inventory import (
    Workspace, WorkspaceInventory, WorkspaceProblem)

SCHEMA = 1
MAX_CONNECTORS = 16
MAX_WORKSPACES = 64
MAX_PROBLEMS = 32
MAX_DECISIONS = 16
MAX_ACTIONS = 16
MAX_CHARS = 160

ACTION_KINDS = frozenset({
    "no_op", "relayout", "reanchor_primary", "clamp_resolution",
    "suspend", "resume"})
FOCUS_FAILURE = frozenset({
    DENIED, STALE_TARGET, UNKNOWN_TARGET, ACTIVATION_FAILED})
FOCUS_STATUSES = frozenset({"GRANTED"} | FOCUS_FAILURE)

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"


class SnapshotError(ValueError):
    """Invalid component, field or bound passed to ``compose``."""


@dataclass(frozen=True)
class DisplayView:
    sequence: int
    monitor_count: int
    connectors: tuple
    action_kinds: tuple
    suspended: bool


@dataclass(frozen=True)
class WorkspaceView:
    workspace_count: int
    identifiers: tuple
    problem_count: int
    problem_reasons: tuple


@dataclass(frozen=True)
class FocusView:
    live_windows: int
    decision_count: int
    statuses: tuple
    target_apps: tuple


@dataclass(frozen=True)
class DisplayFocusMapSnapshot:
    schema: int
    status: str
    acceptance: str
    observation: str
    display: DisplayView
    workspace: WorkspaceView
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
            "display": MappingProxyType({
                "sequence": self.display.sequence,
                "monitor_count": self.display.monitor_count,
                "connectors": self.display.connectors,
                "action_kinds": self.display.action_kinds,
                "suspended": self.display.suspended,
            }),
            "workspace": MappingProxyType({
                "workspace_count": self.workspace.workspace_count,
                "identifiers": self.workspace.identifiers,
                "problem_count": self.workspace.problem_count,
                "problem_reasons": self.workspace.problem_reasons,
            }),
            "focus": MappingProxyType({
                "live_windows": self.focus.live_windows,
                "decision_count": self.focus.decision_count,
                "statuses": self.focus.statuses,
                "target_apps": self.focus.target_apps,
            }),
        })


def _text(value, field):
    if type(value) is not str:
        raise SnapshotError(field + " must be a string")
    return value


def _bounded_text(value, field):
    return _text(value, field)[:MAX_CHARS]


def _count(value, field):
    if type(value) is not int or value < 0:
        raise SnapshotError(field + " must be a non-negative int")
    return value


def _display_view(recovery):
    if not isinstance(recovery, RecoveryResult):
        raise SnapshotError("display must be a RecoveryResult")
    sequence = _count(recovery.sequence, "recovery sequence")
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
    if type(monitors) is not tuple:
        raise SnapshotError("safe topology monitors must be a tuple")
    connectors = tuple(sorted(_bounded_text(c, "monitor connector")
                              for c in safe.connectors))[:MAX_CONNECTORS]
    suspended = ACTION_SUSPEND in kinds
    if suspended and monitors:
        raise SnapshotError("suspended display cannot carry monitors")
    if not suspended and not monitors:
        raise SnapshotError("non-suspended display must carry monitors")
    return DisplayView(
        sequence=sequence,
        monitor_count=len(monitors),
        connectors=connectors,
        action_kinds=tuple(kinds[:MAX_ACTIONS]),
        suspended=suspended,
    )


def _workspace_view(inventory):
    if not isinstance(inventory, WorkspaceInventory):
        raise SnapshotError("workspace must be a WorkspaceInventory")
    workspaces, problems = inventory.workspaces, inventory.problems
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


def _focus_view(broker):
    if not isinstance(broker, FocusBroker):
        raise SnapshotError("focus must be a FocusBroker")
    history = broker.history
    if type(history) is not tuple:
        raise SnapshotError("focus history must be a tuple")
    statuses, target_apps = [], []
    for decision in history[-MAX_DECISIONS:]:
        if not isinstance(decision, FocusDecision):
            raise SnapshotError("focus history must hold FocusDecision values")
        status = _text(decision.status, "focus decision status")
        if status not in FOCUS_STATUSES:
            raise SnapshotError("unsupported focus decision status")
        target = decision.target_app
        statuses.append(status)
        target_apps.append(None if target is None
                           else _bounded_text(target, "focus target app"))
    return FocusView(
        live_windows=_count(broker.live_window_count, "focus live window count"),
        decision_count=len(history),
        statuses=tuple(statuses),
        target_apps=tuple(target_apps),
    )


def _derive_status(display, workspace, focus):
    if display.suspended or any(s in FOCUS_FAILURE for s in focus.statuses):
        return STATUS_BLOCKED
    if (workspace.problem_count or display.monitor_count == 0
            or focus.statuses
            or ACTION_CLAMP_RESOLUTION in display.action_kinds):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(display, workspace, focus):
    """Compose three already-tested value objects into one immutable record.

    Every component is validated before any record is built, so a rejected
    input raises ``SnapshotError`` without a partial result. The source
    objects are never mutated.
    """
    display_view = _display_view(display)
    workspace_view = _workspace_view(workspace)
    focus_view = _focus_view(focus)
    return DisplayFocusMapSnapshot(
        schema=SCHEMA,
        status=_derive_status(display_view, workspace_view, focus_view),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        observation=OBSERVATION_NOT_PERFORMED,
        display=display_view,
        workspace=workspace_view,
        focus=focus_view,
    )
