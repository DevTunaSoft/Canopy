"""Read-only capability catalog for validated pure Canopy feature modules.

Shell Host and presentations can discover trusted, already-tested behaviour
without importing visual code or duplicating a service. The catalog is static:
callers cannot add modules, paths or attributes at runtime. Loading is lazy
and limited to entries in this allowlist; no capability executes anything
until the caller invokes the returned object.

This is metadata and lookup only. It does not launch an application, change a
session, or alter any approved visual element.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import re

MAX_CAPABILITIES = 64
CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$")
MODULE_NAME = re.compile(r"^canopy_features\.[a-z_]+(\.[a-z0-9_]+){1,2}$")
ATTRIBUTE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Static, owner-reviewed registry. Every entry is an already-tested pure
# function in canopy_features/; no QML, C++, artwork or presentation module.
_ENTRIES = {
    "launcher.focus.grid": (
        "canopy_features.launcher.launcher_keyboard_navigation", "make_grid", "launcher"),
    "launcher.focus.move": (
        "canopy_features.launcher.launcher_keyboard_navigation", "move", "launcher"),
    "launcher.focus.selection": (
        "canopy_features.launcher.launcher_keyboard_navigation", "make_selection", "launcher"),
    "launcher.search.rank": (
        "canopy_features.launcher.app_search_ranking", "rank_applications", "launcher"),
    "dock.pins.state": (
        "canopy_features.dock.dock_pinned_items", "empty", "dock"),
    "dock.running.state": (
        "canopy_features.dock.dock_running_indicators", "empty_state", "dock"),
    "security.uri.validate": (
        "canopy_features.security.untrusted_uri_schemes", "validate_uri_intent", "security"),
    "accessibility.contrast.ratio": (
        "canopy_features.accessibility.contrast_audit", "contrast_ratio", "accessibility"),
    "installer.plan.output": (
        "canopy_features.installer.preview_install_plan", "authorize_output", "installer"),
}


class CapabilityError(ValueError):
    """Unknown, malformed or unusable capability request."""


@dataclass(frozen=True)
class Capability:
    """Immutable descriptor; ``visual`` must stay false for this catalog."""

    name: str
    module: str
    attribute: str
    area: str
    visual: bool = False


def _validate_entries() -> None:
    if len(_ENTRIES) > MAX_CAPABILITIES:
        raise CapabilityError("capability catalog exceeds bound")
    for name, (module, attribute, area) in _ENTRIES.items():
        if not CAPABILITY_NAME.fullmatch(name):
            raise CapabilityError("invalid capability name: " + str(name))
        if not MODULE_NAME.fullmatch(module) or not ATTRIBUTE_NAME.fullmatch(attribute):
            raise CapabilityError("invalid capability target: " + str(name))
        if not re.fullmatch(r"[a-z]+", area):
            raise CapabilityError("invalid capability area: " + str(name))


_validate_entries()


def names() -> tuple[str, ...]:
    """Return sorted capability names without importing any feature module."""
    return tuple(sorted(_ENTRIES))


def describe(name: str) -> Capability:
    """Return the immutable descriptor for one allowlisted capability."""
    if not isinstance(name, str) or name not in _ENTRIES:
        raise CapabilityError("unknown capability")
    module, attribute, area = _ENTRIES[name]
    return Capability(name=name, module=module, attribute=attribute, area=area)


def load(name: str):
    """Lazily import an allowlisted module and return its trusted callable."""
    capability = describe(name)
    if capability.visual:
        raise CapabilityError("visual capabilities are not loadable here")
    try:
        module = importlib.import_module(capability.module)
    except (ImportError, OSError, ValueError) as exc:
        raise CapabilityError("capability module unavailable") from exc
    target = getattr(module, capability.attribute, None)
    if not callable(target):
        raise CapabilityError("capability target is not callable")
    return target
