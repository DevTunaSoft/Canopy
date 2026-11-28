"""Read-only host-state wiring for Canopy Classic quick controls.

This package adapts already-existing, bounded host contracts to the fail-closed
view model in :mod:`canopy_features.system.quick_controls_state`. It performs no
I/O, starts nothing and changes no host state.
"""
from .host_state import (
    ALLOWED_FIELDS,
    DEFAULT_SOURCE,
    HostStateController,
    HostStateError,
    HostStateSnapshot,
    empty_snapshot,
)
from .native_controls import (
    ACTIONS as NATIVE_ACTIONS,
    EXECUTION_BLOCKED,
    EXECUTION_LABELS,
    EXECUTION_NOT_RUN,
    EXECUTION_PASS,
    NATIVE_DOMAINS,
    PRIVILEGED_TRANSITIONS,
    CommandPlan,
    ControlVerdict,
    NativeControls,
    NativeControlsError,
    ProbeFacts,
)

__all__ = [
    "ALLOWED_FIELDS",
    "DEFAULT_SOURCE",
    "HostStateController",
    "HostStateError",
    "HostStateSnapshot",
    "empty_snapshot",
    "NATIVE_ACTIONS",
    "NATIVE_DOMAINS",
    "PRIVILEGED_TRANSITIONS",
    "EXECUTION_PASS",
    "EXECUTION_NOT_RUN",
    "EXECUTION_BLOCKED",
    "EXECUTION_LABELS",
    "CommandPlan",
    "ControlVerdict",
    "NativeControls",
    "NativeControlsError",
    "ProbeFacts",
]
