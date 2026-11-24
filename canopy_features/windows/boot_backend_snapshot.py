"""Bounded, immutable, host-facing boot/backend capability snapshot.

Composes three already-tested integration-tree value objects: the durable
``RecoveryDecision`` from startup checkpoints, the immutable
``PortalCapabilityReport`` and the window-state ``Negotiation``. Non-duplicative
with host_reliability (startup+delivery+switcher) and window_session
(switcher+workspace+portal+negotiation).

Pure composition: no I/O, clock, randomness, threads, polling or OS/Qt
observation. Bounded collections, immutable views, deterministic bytes.
Acceptance is always NOT_ESTABLISHED and observation always NOT_PERFORMED.
"""
from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.reliability.startup_checkpoints import (
    FAIL_CLOSED, READY, ROLLBACK, START_FRESH, RecoveryDecision)
from canopy_features.windows.wayland_portal_capabilities import (
    PORTAL_INTERFACES, SCHEMA_VERSION, WINDOW_ENUMERATION,
    PortalCapability, PortalCapabilityReport)
from canopy_features.windows.window_state_capabilities import (
    Negotiation, WindowStateFeature)

SCHEMA = 1
MAX_IDS = 8
MAX_GRANTS = 8
MAX_CHARS = 160

RECOVERY_ACTIONS = frozenset({START_FRESH, READY, ROLLBACK, FAIL_CLOSED})
SESSION_TYPES = frozenset({"wayland", "x11", "unknown"})
NEGOTIATION_STATUSES = frozenset({"SUPPORTED", "PARTIAL", "UNSUPPORTED"})
PORTAL_IDS = frozenset(PORTAL_INTERFACES)

STATUS_OK = "OK"
STATUS_ATTENTION = "ATTENTION"
STATUS_BLOCKED = "BLOCKED"
ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"


class SnapshotError(ValueError):
    """Invalid component, field or bound passed to ``compose``."""


@dataclass(frozen=True)
class StartupView:
    action: str
    safe_to_start: bool
    needs_rollback: bool
    completed_count: int
    unwind_count: int
    reason: str


@dataclass(frozen=True)
class PortalView:
    session_type: str
    wayland: bool
    window_enumeration: str
    usable: tuple
    denied: tuple
    missing: tuple
    unknown_permission: tuple


@dataclass(frozen=True)
class NegotiationView:
    backend: str
    status: str
    granted: tuple
    supported: bool


@dataclass(frozen=True)
class BootBackendSnapshot:
    schema: int
    status: str
    acceptance: str
    observation: str
    startup: StartupView
    portal: PortalView
    negotiation: NegotiationView

    @property
    def is_blocked(self) -> bool:
        return self.status == STATUS_BLOCKED

    def to_dict(self):
        return MappingProxyType({
            "schema": self.schema,
            "status": self.status,
            "acceptance": self.acceptance,
            "observation": self.observation,
            "startup": MappingProxyType({
                "action": self.startup.action,
                "safe_to_start": self.startup.safe_to_start,
                "needs_rollback": self.startup.needs_rollback,
                "completed_count": self.startup.completed_count,
                "unwind_count": self.startup.unwind_count,
                "reason": self.startup.reason,
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


def _startup_view(decision):
    if not isinstance(decision, RecoveryDecision):
        raise SnapshotError("startup must be a RecoveryDecision")
    action = _text(decision.action, "recovery action")
    if action not in RECOVERY_ACTIONS:
        raise SnapshotError("unsupported recovery action")
    if type(decision.completed) is not tuple or type(decision.unwind) is not tuple:
        raise SnapshotError("completed and unwind steps must be tuples")
    safe = _flag(decision.safe_to_start, "safe_to_start")
    rollback = _flag(decision.needs_rollback, "needs_rollback")
    # A RecoveryDecision subclass may override these properties. Derive the
    # expected values from the durable action/unwind fields so a forged flag
    # cannot turn ROLLBACK into a boot-ready STATUS_OK.
    if (safe != (action in (START_FRESH, READY))
            or rollback != bool(decision.unwind)):
        raise SnapshotError("startup flags contradict recovery decision")
    return StartupView(
        action=action,
        safe_to_start=safe,
        needs_rollback=rollback,
        completed_count=len(decision.completed),
        unwind_count=len(decision.unwind),
        reason=_bounded_text(decision.reason, "recovery reason"),
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
    if type(report.capabilities) is not tuple:
        raise SnapshotError("portal capabilities must be a tuple")
    # The summary sets drive status derivation, but the per-capability entries
    # are the only evidence for them. A bounded report whose summary claims a
    # granted portal while its details record a denial/missing portal would
    # otherwise compose as boot-ready; cross-check before any record is built.
    detail = {"usable": set(), "denied": set(), "missing": set(),
              "unknown_permission": set()}
    seen = set()
    for capability in report.capabilities:
        if not isinstance(capability, PortalCapability):
            raise SnapshotError("capabilities must hold PortalCapability entries")
        capability_id = capability.capability
        if type(capability_id) is not str or capability_id not in PORTAL_IDS:
            raise SnapshotError("unknown portal capability id in capabilities")
        if capability_id in seen:
            raise SnapshotError("duplicate portal capability entry")
        seen.add(capability_id)
        if capability.interface != PORTAL_INTERFACES[capability_id]:
            raise SnapshotError("portal capability interface disagrees with id")
        status = capability.status
        if type(status) is not str:
            raise SnapshotError("portal capability status must be a string")
        usable = _flag(capability.usable, "portal capability usable flag")
        if status == "available":
            if not usable:
                raise SnapshotError("usable flag disagrees with available status")
            detail["usable"].add(capability_id)
        elif status in ("permission-denied", "portal-missing",
                        "permission-unknown", "not-wayland"):
            if usable:
                raise SnapshotError("usable flag disagrees with capability status")
            if status != "not-wayland":
                detail[{"permission-denied": "denied",
                        "portal-missing": "missing",
                        "permission-unknown": "unknown_permission"}[status]
                       ].add(capability_id)
        else:
            raise SnapshotError("unsupported portal capability status")
    usable = _portal_ids(report.usable, "usable")
    denied = _portal_ids(report.denied, "denied")
    missing = _portal_ids(report.missing, "missing")
    unknown = _portal_ids(report.unknown_permission, "unknown_permission")
    if (usable != tuple(sorted(detail["usable"]))
            or denied != tuple(sorted(detail["denied"]))
            or missing != tuple(sorted(detail["missing"]))
            or unknown != tuple(sorted(detail["unknown_permission"]))):
        raise SnapshotError("portal summary sets disagree with capability details")
    return PortalView(
        session_type=session,
        wayland=wayland,
        window_enumeration=WINDOW_ENUMERATION,
        usable=usable,
        denied=denied,
        missing=missing,
        unknown_permission=unknown,
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
    supported = bool(granted)
    # The status and the granted set must tell the same story: a bounded
    # negotiation that claims SUPPORTED/PARTIAL with no granted features (or
    # claims UNSUPPORTED while granting features) would compose as a false
    # boot-ready/blocked claim. Cross-check before any record is built.
    if supported != (status in ("SUPPORTED", "PARTIAL")):
        raise SnapshotError("negotiation status disagrees with granted feature set")
    return NegotiationView(
        backend=backend,
        status=status,
        granted=tuple(sorted(features))[:MAX_GRANTS],
        supported=supported,
    )


def _derive_status(startup, portal, negotiation):
    if (not startup.safe_to_start or startup.action == FAIL_CLOSED
            or negotiation.status == "UNSUPPORTED" or portal.denied):
        return STATUS_BLOCKED
    if (startup.needs_rollback or negotiation.status == "PARTIAL"
            or portal.missing or portal.unknown_permission
            or not portal.wayland):
        return STATUS_ATTENTION
    return STATUS_OK


def compose(startup, portal, negotiation):
    """Compose three value objects into one immutable record.

    Every component is validated before any record is built, so a rejected
    input raises ``SnapshotError`` without a partial result. Source objects
    are never mutated.
    """
    startup_view = _startup_view(startup)
    portal_view = _portal_view(portal)
    negotiation_view = _negotiation_view(negotiation)
    return BootBackendSnapshot(
        schema=SCHEMA,
        status=_derive_status(startup_view, portal_view, negotiation_view),
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        observation=OBSERVATION_NOT_PERFORMED,
        startup=startup_view,
        portal=portal_view,
        negotiation=negotiation_view,
    )
