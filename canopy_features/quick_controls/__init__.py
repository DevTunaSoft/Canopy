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

__all__ = [
    "ALLOWED_FIELDS",
    "DEFAULT_SOURCE",
    "HostStateController",
    "HostStateError",
    "HostStateSnapshot",
    "empty_snapshot",
]
