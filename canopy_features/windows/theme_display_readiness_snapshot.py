"""Bounded, immutable, host-facing theme/portal/display readiness snapshot.

Composes three already-tested value objects produced by independent models
into one deterministic record:

* ``reliability/theme_transition_rollback.py`` -- the offline ownership ledger
  for presentation resources during a theme switch, through its frozen
  ``Snapshot`` projection;
* ``windows/wayland_portal_capabilities.py`` -- the immutable
  ``PortalCapabilityReport`` describing portal affordances;
* ``reliability/screen_topology_change.py`` -- the frozen ``RecoveryResult`` of
  one observed display topology.

This is a pure composition layer: no I/O, clock, randomness, threads, locks,
polling, OS or Qt observation. The caller hands it value objects it already
owns. Embedded collections are bounded (resource names, portal capability ids,
action kinds, connectors, text), every public view is immutable, and two
compositions of equal inputs are byte-for-byte identical. No caller input can
make an acceptance, permission-grant or real-observation claim: acceptance is
always ``NOT_ESTABLISHED`` and observation always ``NOT_PERFORMED``.

The status describes only the supplied state, never a running desktop or an
approved visual presentation.
"""
from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.reliability.screen_topology_change import (
    ACTION_CLAMP_RESOLUTION, ACTION_SUSPEND, RecoveryAction, RecoveryResult,
    Topology)
from canopy_features.reliability.theme_transition_rollback import (
    IDLE, PREPARED, Snapshot, ThemeTransitionRollback)
from canopy_features.windows.wayland_portal_capabilities import (
    PORTAL_INTERFACES, SCHEMA_VERSION, WINDOW_ENUMERATION,
    PortalCapability, PortalCapabilityReport)

SCHEMA = 1
MAX_RESOURCES = 16
MAX_PORTAL_IDS = 8
MAX_ACTIONS = 16
MAX_MONITORS = 16
MAX_CHARS = 160

THEME_STATES = frozenset({IDLE, PREPARED})
SESSION_TYPES = frozenset({"wayland", "x11", "unknown"})
ACTION_KINDS = frozenset({
    "no_op", "relayout", "reanchor_primary", "clamp_resolution",
    "suspend", "resume"})
PORTAL_IDS = frozenset(PORTAL_INTERFACES)

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"


class SnapshotError(ValueError):
    """Invalid component, field or bound passed to ``compose``."""


@dataclass(frozen=True)
class ThemeView:
    """Bounded projection of a frozen theme-ledger snapshot."""

    state: str
    active: object
    candidate: object
    single_owner: bool
    live_resource_count: int
    abandoned: tuple


@dataclass(frozen=True)
class PortalView:
    """Bounded projection of an immutable portal capability report."""

    session_type: str
    wayland: bool
    window_enumeration: str
    usable: tuple
    denied: tuple
    missing: tuple
    unknown_permission: tuple


@dataclass(frozen=True)
class DisplayView:
    """Bounded projection of one frozen display ``RecoveryResult``."""

    sequence: int
    monitor_count: int
    connectors: tuple
    action_kinds: tuple
    suspended: bool


@dataclass(frozen=True)
class ThemeDisplayReadinessSnapshot:
    """One deterministic, immutable record of theme/portal/display state."""

    schema: int
    status: str
    acceptance: str
    observation: str
    theme: ThemeView
    portal: PortalView
    display: DisplayView

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
            "theme": MappingProxyType({
                "state": self.theme.state,
                "active": self.theme.active,
                "candidate": self.theme.candidate,
                "single_owner": self.theme.single_owner,
                "live_resource_count": self.theme.live_resource_count,
                "abandoned": self.theme.abandoned,
            }),
            "portal": MappingProxyType({
                "session_type": self.portal.session_type,
                "wayland": self.portal.wayland,
                "window_enumeration": self.portal.window_enumeration,
                "usable": self.portal.usable,
                "denied": self.portal.denied,
                "missing": self.portal.missing,
                "unknown_permission": self.portal.unknown_permission,
            }),
            "display": MappingProxyType({
                "sequence": self.display.sequence,
                "monitor_count": self.display.monitor_count,
                "connectors": self.display.connectors,
                "action_kinds": self.display.action_kinds,
                "suspended": self.display.suspended,
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


def _optional_name(value, field):
    if value is None:
        return None
    return _bounded_text(value, field)


def _name_set(value, field):
    if type(value) is not frozenset:
        raise SnapshotError(field + " must be a frozenset")
    names = []
    for name in value:
        text = _bounded_text(name, field + " name")
        if not text:
            raise SnapshotError(field + " name must not be empty")
        names.append(text)
    if len(names) > MAX_RESOURCES:
        raise SnapshotError(field + " exceeds snapshot bound")
    return tuple(sorted(names))


def _theme_view(ledger):
    if not isinstance(ledger, ThemeTransitionRollback):
        raise SnapshotError("theme must be a ThemeTransitionRollback")
    projected = ledger.snapshot()
    if not isinstance(projected, Snapshot):
        raise SnapshotError("theme projection must be a Snapshot")
    state = _text(projected.state, "theme state")
    if state not in THEME_STATES:
        raise SnapshotError("unsupported theme state")
    single_owner = _flag(projected.single_owner, "theme single-owner flag")
    live = _name_set(projected.live_resources, "live resource")
    abandoned = _name_set(projected.abandoned_resources, "abandoned resource")
    if single_owner != (not (frozenset(live) & frozenset(abandoned))):
        raise SnapshotError("single-owner flag disagrees with resource sets")
    return ThemeView(
        state=state,
        active=_optional_name(projected.active, "theme active"),
        candidate=_optional_name(projected.candidate, "theme candidate"),
        single_owner=single_owner,
        live_resource_count=len(live),
        abandoned=abandoned,
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
        usable=_portal_ids(report.usable, "usable"),
        denied=_portal_ids(report.denied, "denied"),
        missing=_portal_ids(report.missing, "missing"),
        unknown_permission=_portal_ids(report.unknown_permission,
                                        "unknown_permission"),
    )


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
    connectors = tuple(sorted(_bounded_text(c, "monitor connector")
                              for c in safe.connectors))
    suspended = ACTION_SUSPEND in kinds
    if suspended and monitors:
        raise SnapshotError("suspended display cannot carry monitors")
    if not suspended and not monitors:
        raise SnapshotError("non-suspended display must carry monitors")
    return DisplayView(
        sequence=sequence,
        monitor_count=len(monitors),
        connectors=connectors[:MAX_MONITORS],
        action_kinds=tuple(kinds[:MAX_ACTIONS]),
        suspended=suspended,
    )


def _derive_status(theme, portal, display):
    # An uncommitted or double-owned theme, an explicit portal denial, or a
    # suspended display blocks readiness; these outrank softer conditions.
    # Abandoned handles awaiting disposal, missing/unknown portals, a
    # non-Wayland session, a clamped resolution and recorded churn are
    # attention-worthy but still a usable snapshot. This status describes only
    # the supplied state, never an approved visual presentation.
    if (theme.state == PREPARED or not theme.single_owner
            or portal.denied or display.suspended):
        return STATUS_BLOCKED
    if (theme.abandoned or portal.missing or portal.unknown_permission
            or not portal.wayland
            or ACTION_CLAMP_RESOLUTION in display.action_kinds):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(theme, portal, display):
    """Compose three already-tested value objects into one immutable record.

    Every component is validated before any record is built, so a rejected
    input raises ``SnapshotError`` without a partial result. The source
    objects are never mutated.
    """
    theme_view = _theme_view(theme)
    portal_view = _portal_view(portal)
    display_view = _display_view(display)
    return ThemeDisplayReadinessSnapshot(
        schema=SCHEMA,
        status=_derive_status(theme_view, portal_view, display_view),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        observation=OBSERVATION_NOT_PERFORMED,
        theme=theme_view,
        portal=portal_view,
        display=display_view,
    )
