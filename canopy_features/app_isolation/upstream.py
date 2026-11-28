"""Declarative catalog of upstream isolation surfaces (no implementation).

LacOS reuses the distribution's Flatpak/bubblewrap sandbox, xdg portals and
systemd user scopes/unit sandboxing. It does not ship a second sandbox,
compositor, session daemon or always-on service. The catalog below is bounded
plain data used to validate and describe a request; it never binds a namespace,
opens a portal, starts a unit or launches an application.
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, Tuple

from .contract import AppIsolationError, valid_permission

# Keys are mechanism ids, not binaries or commands. "surface" is the upstream
# project that owns the mechanism; "note" is an inert read-first description.
MECHANISMS: Dict[str, Dict[str, Any]] = {
    "flatpak_sandbox": {
        "upstream": "Flatpak with distribution bubblewrap",
        "surface": "per_app_sandbox",
        "note": "per-app namespace owned by upstream Flatpak/bubblewrap",
    },
    "flatpak_portal": {
        "upstream": "xdg-desktop-portal document portal",
        "surface": "filtered_document_access",
        "note": "file access mediated by the upstream portal, read first",
    },
    "xdg_dbus_proxy": {
        "upstream": "Flatpak xdg-dbus-proxy",
        "surface": "filtered_session_bus",
        "note": "session bus filtered by upstream proxy, no raw host socket",
    },
    "systemd_user_scope": {
        "upstream": "systemd user manager transient scope",
        "surface": "per_app_cgroup",
        "note": "transient scope in the existing user manager, no new service",
    },
    "systemd_unit_sandboxing": {
        "upstream": "systemd unit sandboxing directives",
        "surface": "unit_level_restrictions",
        "note": "ProtectSystem strict, ProtectHome read-only, PrivateTmp",
    },
    "rootless_oci": {
        "upstream": "rootless Podman/OCI runtime",
        "surface": "on_demand_container",
        "note": "rootless is not a complete sandbox; no privileged defaults",
    },
}

MECHANISMS_BY_ECOSYSTEM: Dict[str, FrozenSet[str]] = {
    "flatpak_flathub": frozenset((
        "flatpak_sandbox", "flatpak_portal", "xdg_dbus_proxy",
        "systemd_user_scope", "systemd_unit_sandboxing")),
    "apt_deb": frozenset((
        "systemd_user_scope", "systemd_unit_sandboxing")),
    "pacman": frozenset((
        "systemd_user_scope", "systemd_unit_sandboxing")),
    "dnf_rpm": frozenset((
        "systemd_user_scope", "systemd_unit_sandboxing")),
    "rootless_podman_oci": frozenset((
        "rootless_oci", "systemd_user_scope", "systemd_unit_sandboxing")),
}

# Permissions that can be described for each ecosystem. Everything else is
# either unknown or in FORBIDDEN_PERMISSIONS.
PERMISSIONS_BY_ECOSYSTEM: Dict[str, FrozenSet[str]] = {
    "flatpak_flathub": frozenset((
        "documents_read", "screenshot_read", "audio_output",
        "network_filtered", "printing", "dbus_filtered",
        "downloads_write", "config_write")),
    "apt_deb": frozenset((
        "documents_read", "audio_output", "network_filtered", "config_write")),
    "pacman": frozenset((
        "documents_read", "audio_output", "network_filtered", "config_write")),
    "dnf_rpm": frozenset((
        "documents_read", "audio_output", "network_filtered", "config_write")),
    "rootless_podman_oci": frozenset((
        "documents_read", "network_filtered", "dbus_filtered",
        "downloads_write", "config_write")),
}

_PERMISSION_SURFACE = {
    "documents_read": "flatpak_portal",
    "screenshot_read": "flatpak_portal",
    "audio_output": "flatpak_sandbox",
    "network_filtered": "flatpak_sandbox",
    "printing": "flatpak_portal",
    "dbus_filtered": "xdg_dbus_proxy",
    "downloads_write": "flatpak_portal",
    "config_write": "systemd_unit_sandboxing",
}


def valid_mechanism(ecosystem: Any, mechanism_id: Any) -> bool:
    """True when the mechanism is an upstream surface for this ecosystem."""
    if type(ecosystem) is not str or type(mechanism_id) is not str:
        return False
    allowed = MECHANISMS_BY_ECOSYSTEM.get(ecosystem)
    return allowed is not None and mechanism_id in allowed


def upstream_surface(mechanism_id: Any) -> str:
    """Return the owning upstream project name, or an empty string."""
    if type(mechanism_id) is not str:
        return ""
    record = MECHANISMS.get(mechanism_id)
    return record["upstream"] if record is not None else ""


def describe(ecosystem: Any, permissions: Any,
             mechanisms: Any) -> Tuple[str, ...]:
    """Build an inert, bounded description from validated identifiers only.

    No path, binary, command, argument vector or D-Bus message is produced.
    The last step is always a review gate; nothing here can start an app.
    """
    if type(ecosystem) is not str or ecosystem not in MECHANISMS_BY_ECOSYSTEM:
        raise AppIsolationError("unknown ecosystem for description")
    if type(permissions) not in (tuple, list) or type(mechanisms) not in (tuple, list):
        raise AppIsolationError("description inputs must be finite sequences")
    if len(permissions) > 16 or len(mechanisms) > 8:
        raise AppIsolationError("description inputs exceed bounds")
    steps: list = []
    for mechanism in sorted(set(mechanisms)):
        if not valid_mechanism(ecosystem, mechanism):
            raise AppIsolationError("mechanism is not an upstream surface")
        steps.append("UPSTREAM {}: {}".format(
            mechanism, MECHANISMS[mechanism]["note"]))
    for permission in sorted(set(permissions)):
        if not valid_permission(permission):
            raise AppIsolationError("invalid permission label")
        surface = _PERMISSION_SURFACE.get(permission, ecosystem)
        allowed = MECHANISMS_BY_ECOSYSTEM[ecosystem]
        if surface not in allowed:
            surface = ("systemd_unit_sandboxing"
                       if "systemd_unit_sandboxing" in allowed
                       else sorted(allowed)[0])
        steps.append("UPSTREAM {}: {} stays least-privilege".format(
            surface, permission))
    steps.append("REVIEW_REQUIRED before any real-guest launch or write grant")
    return tuple(steps)
