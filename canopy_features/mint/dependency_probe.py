"""Report Qt packages required by Canopy Classic Qt. Read-only; never installs.

Facts come from prototype/classic/CMakeLists.txt and prototype/classic/README.md:
CMake 3.21+, C++17, Qt6 6.4+ (Quick and QuickControls2), the Qt SVG image-format
plugin at runtime, and an optional gio-unix-2.0 development package. Tool names
are reused from the existing read-only Mint preflight. No package manager is
called, no command is executed to install, and no system setting is changed.
"""
import re
from collections.abc import Mapping

from tools.mint_guest_preflight import NEEDED as REQUIRED_TOOLS
from tools.mint_guest_preflight import collect as _preflight_collect


class DependencyProbeError(ValueError):
    """Caller supplied a wrong-type dependency-probe input; fail closed."""


MINIMUM_QT = (6, 4)
MINIMUM_QT_TEXT = ".".join(str(part) for part in MINIMUM_QT)

# Derived from the compiled Classic Qt source, not guessed from distro defaults.
QT_PACKAGES = (
    {
        "name": "qt6-base-dev",
        "category": "build",
        "required": True,
        "reason": "Qt6Core CMake config and pkg-config metadata (find_package Qt6 6.4)",
    },
    {
        "name": "qt6-declarative-dev",
        "category": "build",
        "required": True,
        "reason": "Qt Quick and QuickControls2 CMake components",
    },
    {
        "name": "libqt6svg6",
        "category": "runtime",
        "required": True,
        "reason": "Qt SVG image-format plugin for the static wallpaper",
    },
    {
        "name": "libglib2.0-dev",
        "category": "optional",
        "required": False,
        "reason": "gio-unix-2.0 headers; native app launching falls back when absent",
    },
)

_VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}")
_PACKAGE_RE = re.compile(r"[a-z0-9][a-z0-9+.-]{0,63}")
_TRUSTED_NAMES = frozenset(p["name"] for p in QT_PACKAGES) | frozenset(REQUIRED_TOOLS)


def parse_qt_version(value):
    """Return a comparable version tuple, or None for missing or unsafe input."""
    # An exact str is required: isinstance() alone accepts a subclass whose
    # strip() can be overridden to return a valid label, manufacturing a
    # false sufficient-version claim for a hostile version label.
    if type(value) is not str:
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 24 or not _VERSION_RE.fullmatch(candidate):
        return None
    return tuple(int(part) for part in candidate.split("."))


def filter_trusted_packages(names):
    """Keep only known package names; count rejected inputs.

    Raw untrusted text is never echoed, so a bad manifest cannot inject strings
    into a report or a future command line.
    """
    accepted = []
    rejected = 0
    if names is None:
        return accepted, rejected
    try:
        items = iter(names)
    except TypeError:
        return accepted, 1
    for name in items:
        if (isinstance(name, str) and _PACKAGE_RE.fullmatch(name)
                and name in _TRUSTED_NAMES):
            if name not in accepted:
                accepted.append(name)
        else:
            rejected += 1
    return accepted, rejected


def assess_dependencies(available=None, qt_version=None, requested_packages=None):
    """Pure dependency report: no host calls, no installation, no side effects."""
    if available is None:
        available = {}
    elif not isinstance(available, Mapping):
        raise DependencyProbeError(
            "available must be a mapping of tool names to presence flags")
    tools = {name: bool(available.get(name, False)) for name in REQUIRED_TOOLS}
    missing_tools = [name for name, present in tools.items() if not present]

    parsed = parse_qt_version(qt_version)
    sufficient = parsed is not None and parsed >= MINIMUM_QT
    detected = ".".join(str(part) for part in parsed) if parsed else "unavailable-or-invalid"

    resolved, rejected = filter_trusted_packages(requested_packages)

    blockers = []
    if missing_tools:
        blockers.append("required tool(s) not found: " + ", ".join(missing_tools))
    if not sufficient:
        blockers.append("Qt " + MINIMUM_QT_TEXT + "+ required; detected " + detected)

    return {
        "schema_version": 1,
        "component": "canopy-classic-qt-dependency-probe",
        "probe_only": True,
        "installation": "NOT_ATTEMPTED",
        "minimum_qt_version": MINIMUM_QT_TEXT,
        "detected_qt_version": detected,
        "qt_version_sufficient": sufficient,
        "required_tools": tools,
        "missing_tools": missing_tools,
        "qt_packages": [dict(package) for package in QT_PACKAGES],
        "resolved_requested_packages": resolved,
        "untrusted_names_rejected": rejected,
        "blockers": blockers,
        "status": "COMPLETE" if not blockers else "INCOMPLETE",
    }


def collect(requested_packages=None):
    """Adapt existing read-only preflight facts; still no installation."""
    facts = _preflight_collect()
    return assess_dependencies(
        facts.get("commands_present", {}),
        facts.get("qt6_core_version"),
        requested_packages,
    )
