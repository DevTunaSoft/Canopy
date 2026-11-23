"""Bounded, immutable, host-facing window/session state snapshot.

Composes four already-tested value objects produced by independent windows
state models into one deterministic record:

* ``windows/switcher_state.py`` -- the frozen ``SwitchState`` view of keyboard
  window selection;
* ``windows/workspace_inventory.py`` -- the frozen ``WorkspaceInventory``
  canonical workspace list and its skipped-record notes;
* ``windows/wayland_portal_capabilities.py`` -- the immutable
  ``PortalCapabilityReport`` describing portal affordances;
* ``windows/window_state_capabilities.py`` -- the immutable ``Negotiation``
  of backend window-state features.

The snapshot is a pure composition layer. It performs no I/O, clock or
randomness, spawns no threads and observes no OS or Qt state; the caller hands
it the value objects it already owns. Embedded collections are bounded
(switcher order, workspace identifiers/problem notes, capability ids and
negotiated features), every public view is immutable, and two compositions of
equal inputs are byte-for-byte identical.

This is evidence-shaped bookkeeping, not proof of a running desktop. Mint,
Qt and visual acceptance are deliberately reported as ``NOT_ESTABLISHED``;
window enumeration is always recorded as ``NOT_PERFORMED``. No caller input
can turn this record into an acceptance claim.
"""

from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.windows.switcher_state import SwitchState
from canopy_features.windows.workspace_inventory import (
    Workspace, WorkspaceInventory, WorkspaceProblem)
from canopy_features.windows.wayland_portal_capabilities import (
    PORTAL_INTERFACES, SCHEMA_VERSION, WINDOW_ENUMERATION,
    PortalCapability, PortalCapabilityReport)
from canopy_features.windows.window_state_capabilities import (
    Negotiation, WindowStateFeature)

SCHEMA = 1
MAX_WINDOWS = 64
MAX_WORKSPACES = 64
MAX_PROBLEMS = 32
MAX_CHARS = 160
MAX_ID_LENGTH = 128
MAX_WINDOW_ID = 1_000_000_000_000

SESSION_TYPES = frozenset({"wayland", "x11", "unknown"})
NEGOTIATION_STATUSES = frozenset({"SUPPORTED", "PARTIAL", "UNSUPPORTED"})
PORTAL_IDS = frozenset(PORTAL_INTERFACES)

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"


class SnapshotError(ValueError):
    """Invalid component, field or bound passed to ``compose``."""


@dataclass(frozen=True)
class SwitcherView:
    """Bounded projection of a frozen ``SwitchState`` view."""

    active: bool
    current: object
    selected: object
    window_count: int
    order: tuple


@dataclass(frozen=True)
class WorkspaceView:
    """Bounded projection of a frozen ``WorkspaceInventory``."""

    workspace_count: int
    identifiers: tuple
    problem_count: int
    problem_reasons: tuple


@dataclass(frozen=True)
class PortalView:
    """Bounded projection of a frozen ``PortalCapabilityReport``."""

    session_type: str
    wayland: bool
    window_enumeration: str
    capability_count: int
    usable: tuple
    denied: tuple
    missing: tuple
    unknown_permission: tuple


@dataclass(frozen=True)
class NegotiationView:
    """Bounded projection of a frozen ``Negotiation``."""

    backend: str
    status: str
    granted: tuple
    supported: bool


@dataclass(frozen=True)
class WindowSessionSnapshot:
    """One deterministic, immutable record of host window/session state."""

    schema: int
    status: str
    acceptance: str
    switcher: SwitcherView
    workspace: WorkspaceView
    portal: PortalView
    negotiation: NegotiationView

    @property
    def is_blocked(self) -> bool:
        return self.status == STATUS_BLOCKED

    def to_dict(self):
        """Return a fresh read-only view with a fixed, stable key order."""
        return MappingProxyType({
            "schema": self.schema,
            "status": self.status,
            "acceptance": self.acceptance,
            "switcher": MappingProxyType({
                "active": self.switcher.active,
                "current": self.switcher.current,
                "selected": self.switcher.selected,
                "window_count": self.switcher.window_count,
                "order": self.switcher.order,
            }),
            "workspace": MappingProxyType({
                "workspace_count": self.workspace.workspace_count,
                "identifiers": self.workspace.identifiers,
                "problem_count": self.workspace.problem_count,
                "problem_reasons": self.workspace.problem_reasons,
            }),
            "portal": MappingProxyType({
                "session_type": self.portal.session_type,
                "wayland": self.portal.wayland,
                "window_enumeration": self.portal.window_enumeration,
                "capability_count": self.portal.capability_count,
                "usable": self.portal.usable,
                "denied": self.portal.denied,
                "missing": self.portal.missing,
                "unknown_permission": self.portal.unknown_permission,
            }),
            "negotiation": MappingProxyType({
                "backend": self.negotiation.backend,
                "status": self.negotiation.status,
                "granted": self.negotiation.granted,
                "supported": self.negotiation.supported,
            }),
        })


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
    if type(value) is int and 0 < value <= MAX_WINDOW_ID:
        return value
    if type(value) is str and 0 < len(value) <= MAX_ID_LENGTH:
        return value
    raise SnapshotError("invalid window id in switcher view")


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
        _bounded_text(workspace.identifier, "workspace identifier")
        _bounded_text(workspace.name, "workspace name")
        _bounded_text(workspace.source, "workspace source")
        identifiers.append(workspace.identifier)
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


def _portal_ids(value, field):
    if type(value) is not frozenset:
        raise SnapshotError(field + " must be a frozenset")
    for item in value:
        if type(item) is not str or item not in PORTAL_IDS:
            raise SnapshotError("unknown portal capability id in " + field)
    return tuple(sorted(value))


def _portal_view(report):
    if not isinstance(report, PortalCapabilityReport):
        raise SnapshotError("portal must be a PortalCapabilityReport")
    if type(report.schema_version) is not int or report.schema_version != SCHEMA_VERSION:
        raise SnapshotError("unsupported portal report schema")
    session = _text(report.session_type, "portal session type")
    if session not in SESSION_TYPES:
        raise SnapshotError("unsupported portal session type")
    wayland = _flag(report.wayland, "portal wayland flag")
    if wayland != (session == "wayland"):
        raise SnapshotError("portal session/wayland fields disagree")
    if report.window_enumeration != WINDOW_ENUMERATION:
        raise SnapshotError("portal report must not claim window enumeration")
    capabilities = report.capabilities
    if type(capabilities) is not tuple:
        raise SnapshotError("portal capabilities must be a tuple")
    for capability in capabilities:
        if not isinstance(capability, PortalCapability):
            raise SnapshotError("capabilities must hold PortalCapability entries")
    return PortalView(
        session_type=session,
        wayland=wayland,
        window_enumeration=WINDOW_ENUMERATION,
        capability_count=len(capabilities),
        usable=_portal_ids(report.usable, "usable"),
        denied=_portal_ids(report.denied, "denied"),
        missing=_portal_ids(report.missing, "missing"),
        unknown_permission=_portal_ids(report.unknown_permission, "unknown_permission"),
    )


def _negotiation_view(negotiation):
    if not isinstance(negotiation, Negotiation):
        raise SnapshotError("negotiation must be a Negotiation")
    backend = _bounded_text(negotiation.backend, "negotiation backend")
    if not backend:
        raise SnapshotError("negotiation backend must not be empty")
    status = _text(negotiation.status, "negotiation status")
    if status not in NEGOTIATION_STATUSES:
        raise SnapshotError("unsupported negotiation status")
    granted = negotiation.granted
    if type(granted) is not frozenset:
        raise SnapshotError("negotiation granted must be a frozenset")
    features = []
    for feature in granted:
        if not isinstance(feature, WindowStateFeature):
            raise SnapshotError("granted must hold WindowStateFeature values")
        features.append(feature.value)
    return NegotiationView(
        backend=backend,
        status=status,
        granted=tuple(sorted(features)),
        supported=bool(granted),
    )


def _derive_status(switcher, workspace, portal, negotiation):
    # An unsupported window-state negotiation or an explicit portal denial
    # blocks the record; both outrank softer attention conditions. Missing or
    # unknown portals, a partial negotiation, skipped workspace records, no
    # tracked window and a non-Wayland session are attention-worthy but still
    # a usable snapshot. This status describes only the supplied state, never
    # a running desktop (there is no acceptance field to flip).
    if negotiation.status == "UNSUPPORTED" or portal.denied:
        return STATUS_BLOCKED
    if (negotiation.status == "PARTIAL" or portal.missing
            or portal.unknown_permission or workspace.problem_count
            or switcher.window_count == 0 or not portal.wayland):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(switcher, workspace, portal, negotiation):
    """Compose four already-tested value objects into one immutable record.

    Every rejected input raises ``SnapshotError`` before any record is built,
    so no partial snapshot escapes. Embedded collections are capped; the
    original value objects are never copied wholesale or mutated.
    """
    switcher_view = _switcher_view(switcher)
    workspace_view = _workspace_view(workspace)
    portal_view = _portal_view(portal)
    negotiation_view = _negotiation_view(negotiation)
    return WindowSessionSnapshot(
        schema=SCHEMA,
        status=_derive_status(switcher_view, workspace_view,
                              portal_view, negotiation_view),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        switcher=switcher_view,
        workspace=workspace_view,
        portal=portal_view,
        negotiation=negotiation_view,
    )
