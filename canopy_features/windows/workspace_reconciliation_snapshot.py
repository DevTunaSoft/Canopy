"""Bounded, immutable, host-facing workspace-reconciliation snapshot.

Composes three already-tested value objects produced by independent models
into one deterministic record:

* ``windows/workspace_inventory.py`` -- one ``Reconciliation`` of two canonical
  workspace inventories (added/removed/renamed/reordered identifiers plus the
  current inventory and its skipped-record notes);
* ``reliability/screen_topology_change.py`` -- the frozen ``RecoveryResult`` of
  one observed display topology (sequence, advisory actions, safe topology);
* ``windows/window_close_intents.py`` -- immutable close/reopen ``IntentResult``
  decisions for non-destructive window lifecycle requests.

This is a pure composition layer: no I/O, clock, randomness, threads, locks,
polling, OS or Qt observation. The caller hands it value objects it already
owns. Embedded collections are bounded (identifiers, decisions, action kinds,
text), every public view is immutable, and two compositions of equal inputs
are byte-for-byte identical. No caller input can make an acceptance or
event-observation claim: acceptance is always ``NOT_ESTABLISHED`` and
observation always ``NOT_PERFORMED``.

The status describes only the supplied state, never a running desktop.
"""
from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.reliability.screen_topology_change import (
    ACTION_CLAMP_RESOLUTION, ACTION_NO_OP, ACTION_REANCHOR_PRIMARY,
    ACTION_RELAYOUT, ACTION_RESUME, ACTION_SUSPEND,
    RecoveryAction, RecoveryResult, Topology)
from canopy_features.windows.window_close_intents import (
    ALREADY_CLOSED, ALREADY_OPEN, GUARDED, OWNERSHIP_DENIED, UNKNOWN_WINDOW,
    STATUSES as CLOSE_STATUSES, IntentResult)
from canopy_features.windows.workspace_inventory import (
    Reconciliation, Workspace, WorkspaceInventory, WorkspaceProblem)

SCHEMA = 1
MAX_IDS = 64
MAX_DECISIONS = 16
MAX_ACTIONS = 16
MAX_MONITORS = 16
MAX_CHARS = 160
MAX_ID_LENGTH = 128

ACTION_KINDS = frozenset({
    ACTION_NO_OP, ACTION_RELAYOUT, ACTION_REANCHOR_PRIMARY,
    ACTION_CLAMP_RESOLUTION, ACTION_SUSPEND, ACTION_RESUME})
BLOCKING_CLOSE = frozenset({UNKNOWN_WINDOW, OWNERSHIP_DENIED, GUARDED})
SOFT_CLOSE = frozenset({ALREADY_CLOSED, ALREADY_OPEN})

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"


class SnapshotError(ValueError):
    """Invalid component, field or bound passed to ``compose``."""


@dataclass(frozen=True)
class WorkspaceReconciliationView:
    """Bounded projection of one workspace ``Reconciliation``."""

    workspace_count: int
    identifiers: tuple
    problem_count: int
    problem_reasons: tuple
    added: tuple
    removed: tuple
    renamed: tuple
    reordered: tuple


@dataclass(frozen=True)
class DisplayRecoveryView:
    """Bounded projection of one frozen display ``RecoveryResult``."""

    sequence: int
    monitor_count: int
    action_kinds: tuple
    suspended: bool


@dataclass(frozen=True)
class CloseDecisionView:
    """Bounded projection of immutable close/reopen decisions."""

    decision_count: int
    window_ids: tuple
    statuses: tuple
    notes: tuple


@dataclass(frozen=True)
class WorkspaceReconciliationSnapshot:
    """One deterministic, immutable record of workspace reconciliation state."""

    schema: int
    status: str
    acceptance: str
    observation: str
    workspace: WorkspaceReconciliationView
    display: DisplayRecoveryView
    close: CloseDecisionView

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
            "workspace": MappingProxyType({
                "workspace_count": self.workspace.workspace_count,
                "identifiers": self.workspace.identifiers,
                "problem_count": self.workspace.problem_count,
                "problem_reasons": self.workspace.problem_reasons,
                "added": self.workspace.added,
                "removed": self.workspace.removed,
                "renamed": self.workspace.renamed,
                "reordered": self.workspace.reordered,
            }),
            "display": MappingProxyType({
                "sequence": self.display.sequence,
                "monitor_count": self.display.monitor_count,
                "action_kinds": self.display.action_kinds,
                "suspended": self.display.suspended,
            }),
            "close": MappingProxyType({
                "decision_count": self.close.decision_count,
                "window_ids": self.close.window_ids,
                "statuses": self.close.statuses,
                "notes": self.close.notes,
            }),
        })


def _count(value, field):
    if type(value) is not int or value < 0:
        raise SnapshotError(field + " must be a non-negative int")
    return value


def _text(value, field):
    if type(value) is not str:
        raise SnapshotError(field + " must be a string")
    return value


def _bounded_text(value, field):
    return _text(value, field)[:MAX_CHARS]


def _id_tuple(value, field):
    if type(value) is not tuple:
        raise SnapshotError(field + " must be a tuple")
    result = []
    for item in value[:MAX_IDS]:
        identifier = _bounded_text(item, field + " identifier")
        if not identifier or len(identifier) > MAX_ID_LENGTH:
            raise SnapshotError(field + " identifier is empty or too long")
        result.append(identifier)
    return tuple(result)


def _workspace_view(reconciliation):
    if not isinstance(reconciliation, Reconciliation):
        raise SnapshotError("workspace must be a Reconciliation")
    inventory = reconciliation.inventory
    if not isinstance(inventory, WorkspaceInventory):
        raise SnapshotError("reconciliation inventory must be a WorkspaceInventory")
    workspaces = inventory.workspaces
    problems = inventory.problems
    if type(workspaces) is not tuple or type(problems) is not tuple:
        raise SnapshotError("workspace records and problems must be tuples")
    identifiers = []
    for workspace in workspaces[:MAX_IDS]:
        if not isinstance(workspace, Workspace):
            raise SnapshotError("workspace records must be Workspace values")
        identifier = _bounded_text(workspace.identifier, "workspace identifier")
        if not identifier:
            raise SnapshotError("workspace identifier must not be empty")
        _bounded_text(workspace.name, "workspace name")
        _bounded_text(workspace.source, "workspace source")
        identifiers.append(identifier)
    reasons = []
    for problem in problems[:MAX_IDS]:
        if not isinstance(problem, WorkspaceProblem):
            raise SnapshotError("problems must hold WorkspaceProblem entries")
        _bounded_text(problem.location, "problem location")
        reasons.append(_bounded_text(problem.reason, "problem reason"))
    return WorkspaceReconciliationView(
        workspace_count=len(workspaces),
        identifiers=tuple(identifiers),
        problem_count=len(problems),
        problem_reasons=tuple(reasons),
        added=_id_tuple(reconciliation.added, "added"),
        removed=_id_tuple(reconciliation.removed, "removed"),
        renamed=_id_tuple(reconciliation.renamed, "renamed"),
        reordered=_id_tuple(reconciliation.reordered, "reordered"),
    )


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
    if type(monitors) is not tuple or len(monitors) > MAX_MONITORS:
        raise SnapshotError("invalid or oversized safe topology")
    suspended = ACTION_SUSPEND in kinds
    if suspended and monitors:
        raise SnapshotError("suspended display cannot carry monitors")
    if not suspended and not monitors:
        raise SnapshotError("non-suspended display must carry monitors")
    return DisplayRecoveryView(
        sequence=sequence,
        monitor_count=len(monitors),
        action_kinds=tuple(kinds[:MAX_ACTIONS]),
        suspended=suspended,
    )


def _close_view(decisions):
    if type(decisions) not in (tuple, list):
        raise SnapshotError("close decisions must be a sequence")
    window_ids, statuses, notes = [], [], []
    for decision in decisions[-MAX_DECISIONS:]:
        if not isinstance(decision, IntentResult):
            raise SnapshotError("close decisions must hold IntentResult values")
        window_id = _bounded_text(decision.window_id, "close window id")
        if not window_id or len(window_id) > MAX_ID_LENGTH:
            raise SnapshotError("close window id is empty or too long")
        status = _text(decision.status, "close decision status")
        if status not in CLOSE_STATUSES:
            raise SnapshotError("unknown close decision status")
        window_ids.append(window_id)
        statuses.append(status)
        notes.append(_bounded_text(decision.note, "close decision note"))
    return CloseDecisionView(
        decision_count=len(decisions),
        window_ids=tuple(window_ids),
        statuses=tuple(statuses),
        notes=tuple(notes),
    )


def _derive_status(workspace, display, close):
    # A suspended display, hard close refusal or an invalid/oversized display
    # topology blocks the record. Workspace diffs, skipped records, parked or
    # reopened windows and a clamped resolution are attention-worthy but leave
    # a usable snapshot. This status describes only the supplied state; there
    # is no acceptance field to flip.
    if (display.suspended
            or any(status in BLOCKING_CLOSE for status in close.statuses)):
        return STATUS_BLOCKED
    if (workspace.added or workspace.removed or workspace.renamed
            or workspace.reordered or workspace.problem_count
            or close.statuses
            or ACTION_CLAMP_RESOLUTION in display.action_kinds):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(reconciliation, recovery, decisions=()):
    """Compose three already-tested value objects into one immutable record.

    Every component is validated before any record is built, so a rejected
    input raises ``SnapshotError`` without a partial result. Embedded
    collections are bounded; the source objects are never mutated.
    """
    workspace_view = _workspace_view(reconciliation)
    display_view = _display_view(recovery)
    close_view = _close_view(decisions)
    return WorkspaceReconciliationSnapshot(
        schema=SCHEMA,
        status=_derive_status(workspace_view, display_view, close_view),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        observation=OBSERVATION_NOT_PERFORMED,
        workspace=workspace_view,
        display=display_view,
        close=close_view,
    )
