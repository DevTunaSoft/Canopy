"""Decision-only workspace-switch contract over native window-state records.

A trusted caller supplies one workspace inventory and one already-negotiated
window-state record. This module decides whether a native workspace switch may
be requested, or whether the caller must use the graceful fallback. It never
starts a window manager, activates a window, polls a compositor, sleeps,
launches a process or observes a desktop. The decision is immutable and
contains no callback: the existing host WM bridge owns any later action.

Known backend ids mirror ``window_state_capabilities.KNOWN_BACKENDS``. Native
workspace switching is only recognised for X11, whose core protocol exposes
workspaces; Wayland and headless backends fall back instead of duplicating a
window manager. Unknown backend names fail closed through the same fallback.
"""
from dataclasses import dataclass
from types import MappingProxyType

from canopy_features.windows.window_state_capabilities import (
    KNOWN_BACKENDS, Negotiation, WindowStateAction)
from canopy_features.windows.workspace_inventory import WorkspaceInventory

SCHEMA = 1
MAX_ID_LENGTH = 128
MAX_CHARS = 160

CAPABILITY_ENUMERATE = "enumerate"
CAPABILITY_SWITCH = "switch"
CAPABILITIES = frozenset({CAPABILITY_ENUMERATE, CAPABILITY_SWITCH})

# X11 core exposes workspaces. Wayland intentionally has no core equivalent,
# and a headless session has no WM at all; neither may fabricate one here.
NATIVE_SWITCH_BACKENDS = frozenset({"x11"})

STATUS_NATIVE = "NATIVE"
STATUS_FALLBACK = "FALLBACK"
REASON_NATIVE_READY = "NATIVE_READY"
REASON_BACKEND_UNSUPPORTED = "BACKEND_UNSUPPORTED"
REASON_CAPABILITY_NOT_GRANTED = "CAPABILITY_NOT_GRANTED"
REASON_UNKNOWN_TARGET = "UNKNOWN_TARGET"
REASON_ALREADY_ACTIVE = "ALREADY_ACTIVE"

ACCEPTANCE_NOT_ESTABLISHED = "NOT_ESTABLISHED"
OBSERVATION_NOT_PERFORMED = "NOT_PERFORMED"

# Structural contract: a decision neither starts a WM nor enables polling.
WM_REQUESTS = 0
POLLING_ENABLED = False


class WorkspaceContractError(ValueError):
    """Invalid or contradictory trusted input to ``decide``."""


@dataclass(frozen=True)
class WorkspaceStateDecision:
    """One immutable, deterministic workspace-switch decision."""

    schema: int
    status: str
    reason: str
    backend: str
    active: str
    target: str
    workspace_count: int
    capability: str
    acceptance: str
    observation: str
    wm_requests: int
    polling: bool

    @property
    def native_allowed(self):
        return self.status == STATUS_NATIVE

    def to_dict(self):
        """Fresh read-only view with a fixed key order."""
        return MappingProxyType({
            "schema": self.schema,
            "status": self.status,
            "reason": self.reason,
            "backend": self.backend,
            "active": self.active,
            "target": self.target,
            "workspace_count": self.workspace_count,
            "capability": self.capability,
            "acceptance": self.acceptance,
            "observation": self.observation,
            "wm_requests": self.wm_requests,
            "polling": self.polling,
        })


def _identifier(value, field):
    if (type(value) is not str or not value
            or len(value) > MAX_ID_LENGTH):
        raise WorkspaceContractError(field + " must be a bounded string")
    return value


def _text(value, field):
    return _identifier(value, field)[:MAX_CHARS]


def _capabilities(value):
    if type(value) is not frozenset:
        raise WorkspaceContractError("capabilities must be a frozenset")
    for capability in value:
        if type(capability) is not str or capability not in CAPABILITIES:
            raise WorkspaceContractError("unknown workspace capability")
    return value


def _negotiation(value):
    """Validate one native negotiation record before it can grant anything."""
    if not isinstance(value, Negotiation):
        raise WorkspaceContractError("negotiation must be a Negotiation")
    backend = _text(value.backend, "negotiation backend")
    status = _text(value.status, "negotiation status")
    if status not in ("SUPPORTED", "PARTIAL", "UNSUPPORTED"):
        raise WorkspaceContractError("unknown negotiation status")
    granted = value.granted
    if type(granted) is not frozenset:
        raise WorkspaceContractError("negotiation grants must be a frozenset")
    # allows() applies the validated-grant and status/profile cross-checks of
    # window_state_capabilities. A contrary record cannot grant a switch.
    allows = any(value.allows(action) for action in WindowStateAction)
    if allows != (status != "UNSUPPORTED"):
        raise WorkspaceContractError("negotiation status contradicts its grants")
    # An unknown name is still a valid fail-closed negotiation: it degrades to
    # the fallback below, but it must not manufacture capability grants.
    if backend not in KNOWN_BACKENDS and allows:
        raise WorkspaceContractError("unknown backend cannot advertise grants")
    return backend


def decide(workspace, active, target, *, negotiation, capabilities):
    """Decide native switch vs graceful fallback from trusted records only.

    ``workspace`` is a ``WorkspaceInventory``, ``active`` and ``target`` are
    identifiers, ``negotiation`` is an already-negotiated window-state record
    and ``capabilities`` is the native bridge's ``frozenset`` of workspace
    capabilities. No argument is invoked, mutated or observed at runtime.
    """
    if not isinstance(workspace, WorkspaceInventory):
        raise WorkspaceContractError("workspace must be a WorkspaceInventory")
    active = _identifier(active, "active")
    target = _identifier(target, "target")
    records = workspace.workspaces
    if type(records) is not tuple:
        raise WorkspaceContractError("workspace records must be a tuple")
    identifiers = tuple(record.identifier for record in records)
    backend = _negotiation(negotiation)
    capabilities = _capabilities(capabilities)

    if backend not in NATIVE_SWITCH_BACKENDS:
        status, reason = STATUS_FALLBACK, REASON_BACKEND_UNSUPPORTED
    elif CAPABILITY_SWITCH not in capabilities:
        status, reason = STATUS_FALLBACK, REASON_CAPABILITY_NOT_GRANTED
    elif target not in identifiers:
        status, reason = STATUS_FALLBACK, REASON_UNKNOWN_TARGET
    elif target == active:
        status, reason = STATUS_FALLBACK, REASON_ALREADY_ACTIVE
    else:
        status, reason = STATUS_NATIVE, REASON_NATIVE_READY

    return WorkspaceStateDecision(
        schema=SCHEMA,
        status=status,
        reason=reason,
        backend=backend,
        active=active,
        target=target,
        workspace_count=len(identifiers),
        capability=CAPABILITY_SWITCH if CAPABILITY_SWITCH in capabilities else "",
        acceptance=ACCEPTANCE_NOT_ESTABLISHED,
        observation=OBSERVATION_NOT_PERFORMED,
        wm_requests=WM_REQUESTS,
        polling=POLLING_ENABLED,
    )


__all__ = [
    "SCHEMA", "CAPABILITIES", "CAPABILITY_ENUMERATE", "CAPABILITY_SWITCH",
    "NATIVE_SWITCH_BACKENDS", "STATUS_NATIVE", "STATUS_FALLBACK",
    "REASON_NATIVE_READY", "REASON_BACKEND_UNSUPPORTED",
    "REASON_CAPABILITY_NOT_GRANTED", "REASON_UNKNOWN_TARGET",
    "REASON_ALREADY_ACTIVE", "ACCEPTANCE_NOT_ESTABLISHED",
    "OBSERVATION_NOT_PERFORMED", "WM_REQUESTS", "POLLING_ENABLED",
    "WorkspaceContractError", "WorkspaceStateDecision", "decide",
]
