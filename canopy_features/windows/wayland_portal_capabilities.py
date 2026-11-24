"""Offline, read-only description of Wayland desktop-portal capabilities.

Answers one narrow host question: which XDG desktop-portal affordances may a
shell offer on a Wayland session, given observed portal presence and an
explicit user permission decision?

Pure descriptor. It never opens D-Bus, spawns processes, reads the
environment, polls, starts a service, grants a permission or enumerates
windows. Callers supply bounded facts; the result is immutable. Window
enumeration is recorded as NOT_PERFORMED in every report.

Reuses existing Canopy contracts rather than duplicating system services:
the pure-probe shape (``schema_version``, ``NOT_*`` sentinel, fail-closed
validation) from ``tools.mint_guest_preflight`` and the "capabilities are
UI affordances, never privileges" rule from ``canopy_core.registry``.
``PortalCapabilityReport.usable`` is a frozenset shaped like the host
capability set consumed by ``PackScan.compatible``.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import FrozenSet, Mapping, Tuple

SCHEMA_VERSION = 1

WINDOW_ENUMERATION = "NOT_PERFORMED"

# Fixed allowlist: capability id -> well-known XDG portal interface name.
# Not discovered at runtime; no D-Bus name ownership check is performed.
PORTAL_INTERFACES = MappingProxyType({
    "remote_desktop": "org.freedesktop.portal.RemoteDesktop",
    "screen_cast": "org.freedesktop.portal.ScreenCast",
})

_PERMISSION_STATES = frozenset({"granted", "denied", "unknown"})


class PortalCapabilityError(ValueError):
    """Caller supplied an unknown, malformed or unbounded observation."""


@dataclass(frozen=True)
class PortalCapability:
    """One portal's described state. ``usable`` is True only if available."""

    capability: str
    interface: str
    status: str
    permission: str
    present: bool
    usable: bool


@dataclass(frozen=True)
class PortalCapabilityReport:
    """Immutable, bounded capability facts. Not a permission grant."""

    schema_version: int
    session_type: str
    wayland: bool
    window_enumeration: str
    capabilities: Tuple[PortalCapability, ...]
    usable: FrozenSet[str]
    denied: FrozenSet[str]
    missing: FrozenSet[str]
    unknown_permission: FrozenSet[str]

    @property
    def any_usable(self):
        return bool(self.usable)


def _session_type(value):
    """Normalize to wayland/x11/unknown; never echo raw caller values."""
    if type(value) is not str:
        raise PortalCapabilityError("session type must be a string")
    normalized = value.strip().casefold()
    if normalized in ("wayland", "x11"):
        return normalized
    return "unknown"


def _present_ids(present_portals):
    if type(present_portals) not in (frozenset, set, tuple, list):
        raise PortalCapabilityError("present portals must be a bounded collection")
    if len(present_portals) > len(PORTAL_INTERFACES):
        raise PortalCapabilityError("too many observed portals")
    ids = set()
    for item in present_portals:
        if type(item) is not str or item not in PORTAL_INTERFACES:
            raise PortalCapabilityError("unknown portal capability id")
        ids.add(item)
    return frozenset(ids)


def _grants(permissions):
    if not isinstance(permissions, Mapping):
        raise PortalCapabilityError("permissions must be a mapping")
    if len(permissions) > len(PORTAL_INTERFACES):
        raise PortalCapabilityError("too many permission entries")
    result = {}
    for key, value in permissions.items():
        if type(key) is not str or key not in PORTAL_INTERFACES:
            raise PortalCapabilityError("unknown portal capability id in permissions")
        if type(value) is not str or value not in _PERMISSION_STATES:
            raise PortalCapabilityError("unsupported permission state")
        result[key] = value
    return result


def describe(session_type, present_portals, permissions):
    """Describe portal affordances from supplied facts; fail closed.

    ``status`` values: ``available``, ``permission-denied``,
    ``permission-unknown``, ``portal-missing`` or ``not-wayland``.
    """
    session = _session_type(session_type)
    wayland = session == "wayland"
    present = _present_ids(present_portals)
    grants = _grants(permissions)

    capabilities = []
    usable, denied, missing, unknown = set(), set(), set(), set()
    for capability, interface in sorted(PORTAL_INTERFACES.items()):
        is_present = capability in present
        permission = grants.get(capability, "unknown")
        if not is_present:
            permission = "absent"
            status = "portal-missing"
            missing.add(capability)
        elif not wayland:
            status = "not-wayland"
        elif permission == "denied":
            status = "permission-denied"
            denied.add(capability)
        elif permission == "granted":
            status = "available"
            usable.add(capability)
        else:
            status = "permission-unknown"
            unknown.add(capability)
        capabilities.append(PortalCapability(
            capability=capability,
            interface=interface,
            status=status,
            permission=permission,
            present=is_present,
            usable=status == "available",
        ))

    return PortalCapabilityReport(
        schema_version=SCHEMA_VERSION,
        session_type=session,
        wayland=wayland,
        window_enumeration=WINDOW_ENUMERATION,
        capabilities=tuple(capabilities),
        usable=frozenset(usable),
        denied=frozenset(denied),
        missing=frozenset(missing),
        unknown_permission=frozenset(unknown),
    )
