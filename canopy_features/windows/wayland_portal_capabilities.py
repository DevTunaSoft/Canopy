"""Offline, read-only description of Wayland portal capabilities.

This module *describes* which xdg-desktop-portal interfaces appear present and
permitted. It is metadata, NOT proof that a portal works and NOT a permission
grant. It never enumerates windows: the Wayland protocol provides no global
window list, so no window listing is attempted or implied.

No D-Bus calls, child processes, threads, polling, privileged actions, secrets
or unbounded buffers are used. Every fact is supplied by the caller, so the
component stays pure, deterministic and testable offline. Callers can feed it
session facts already normalized by tools.mint_guest_preflight.assess() via
describe_from_preflight() instead of re-probing the host.
"""

from dataclasses import dataclass
from typing import FrozenSet, Mapping, Tuple


# Fixed, bounded allowlist. Capability name -> well-known portal interface.
# Interface names are inert metadata strings; no D-Bus name is ever contacted.
PORTAL_INTERFACES: Mapping[str, str] = {
    "open-uri": "org.freedesktop.portal.OpenURI",
    "file-chooser": "org.freedesktop.portal.FileChooser",
    "settings": "org.freedesktop.portal.Settings",
    "documents": "org.freedesktop.portal.Documents",
    "screen-cast": "org.freedesktop.portal.ScreenCast",
    "remote-desktop": "org.freedesktop.portal.RemoteDesktop",
}

PORTAL_CAPABILITIES: FrozenSet[str] = frozenset(PORTAL_INTERFACES)

# Fixed status codes, safe for logging and evidence.
STATUS_AVAILABLE = "AVAILABLE"
STATUS_PORTAL_MISSING = "PORTAL_MISSING"
STATUS_PERMISSION_DENIED = "PERMISSION_DENIED"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

WINDOW_ENUMERATION = "NOT_PERFORMED"


def _is_granted(value) -> bool:
    """Only an explicit grant counts; missing, false or unknown values deny."""
    if value is True:
        return True
    return isinstance(value, str) and value.lower() in ("granted", "allow")


@dataclass(frozen=True)
class PortalCapability:
    """One described portal capability. Never an approval to use it."""

    name: str
    interface: str
    status: str
    portal_present: bool
    permitted: bool

    @property
    def available(self) -> bool:
        return self.status == STATUS_AVAILABLE


@dataclass(frozen=True)
class PortalCapabilityReport:
    """Bounded, immutable capability description for one session snapshot."""

    schema_version: int
    probe_only: bool
    session_type: str
    wayland_display_present: bool
    window_enumeration: str
    capabilities: Tuple[PortalCapability, ...]

    @property
    def granted(self) -> FrozenSet[str]:
        return frozenset(c.name for c in self.capabilities if c.available)

    def to_dict(self) -> dict:
        """JSON-safe form for logs and evidence; contains no host data."""
        return {
            "schema_version": self.schema_version,
            "probe_only": self.probe_only,
            "session_type": self.session_type,
            "wayland_display_present": self.wayland_display_present,
            "window_enumeration": self.window_enumeration,
            "capabilities": [
                {
                    "name": cap.name,
                    "interface": cap.interface,
                    "status": cap.status,
                    "portal_present": cap.portal_present,
                    "permitted": cap.permitted,
                }
                for cap in self.capabilities
            ],
        }


def describe(
    session_type: str,
    wayland_display_present: bool,
    available_interfaces,
    permissions: Mapping,
    requested=None,
) -> PortalCapabilityReport:
    """Describe portal capabilities from caller-supplied facts only.

    available_interfaces: well-known portal interface names seen by the caller.
    permissions: mapping of capability name -> explicit grant; missing denies.
    requested: optional subset of PORTAL_CAPABILITIES; unknown names rejected.
    """
    if not isinstance(session_type, str):
        raise TypeError("session_type must be a string")
    normalized = session_type.strip().lower()
    if normalized not in ("wayland", "x11"):
        normalized = "other-or-unknown"
    if type(wayland_display_present) is not bool:
        raise TypeError("wayland_display_present must be a bool")
    if isinstance(available_interfaces, (str, bytes)):
        raise TypeError("available_interfaces must be an iterable of interface names")
    if not isinstance(permissions, Mapping):
        raise TypeError("permissions must be a mapping")

    present = frozenset(name for name in available_interfaces if isinstance(name, str))

    if requested is None:
        names = tuple(sorted(PORTAL_CAPABILITIES))
    else:
        if isinstance(requested, (str, bytes)):
            raise TypeError("requested must be an iterable of capability names")
        chosen = list(requested)
        if any(name not in PORTAL_CAPABILITIES for name in chosen):
            raise ValueError("requested contains an unknown portal capability")
        names = tuple(sorted(set(chosen)))

    applicable = normalized == "wayland" and wayland_display_present
    capabilities = []
    for name in names:
        interface = PORTAL_INTERFACES[name]
        if not applicable:
            capabilities.append(PortalCapability(
                name, interface, STATUS_NOT_APPLICABLE, False, False))
            continue
        portal_present = interface in present
        permitted = _is_granted(permissions.get(name)) if portal_present else False
        if not portal_present:
            status = STATUS_PORTAL_MISSING
        elif not permitted:
            status = STATUS_PERMISSION_DENIED
        else:
            status = STATUS_AVAILABLE
        capabilities.append(PortalCapability(
            name, interface, status, portal_present, permitted))

    return PortalCapabilityReport(
        schema_version=1,
        probe_only=True,
        session_type=normalized,
        wayland_display_present=wayland_display_present,
        window_enumeration=WINDOW_ENUMERATION,
        capabilities=tuple(capabilities),
    )


def describe_from_preflight(
    preflight: Mapping,
    available_interfaces,
    permissions: Mapping,
    requested=None,
) -> PortalCapabilityReport:
    """Reuse session facts from an existing read-only readiness report.

    Consumes the normalized session_type and graphical_display_present fields
    from tools.mint_guest_preflight.assess(). Does not re-probe the host or
    grant any permission.
    """
    if not isinstance(preflight, Mapping):
        raise TypeError("preflight must be a mapping")
    session = preflight.get("session_type", "other-or-unknown")
    if not isinstance(session, str):
        session = "other-or-unknown"
    return describe(
        session,
        bool(preflight.get("graphical_display_present", False)),
        available_interfaces,
        permissions,
        requested,
    )
