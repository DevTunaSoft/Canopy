"""Read-only Qt dependency report for the compiled Classic Qt prototype.

This module reports which Qt apt packages the build and runtime need. It never
installs, upgrades, opens a network connection or starts background work. Tool
presence and the installed Qt version are reused from
``tools.mint_guest_preflight`` instead of being probed a second time.

This is a report only. It does not prove a working desktop, a successful Qt
build, Linux Mint acceptance or visual approval.
"""
import argparse
import json
import platform
import re
import shutil
import subprocess

from tools.mint_guest_preflight import collect as preflight_collect

SCHEMA_VERSION = 1
SOURCE_FILE = "prototype/classic/CMakeLists.txt"
PACKAGE_SOURCE = ".github/workflows/classic-qt.yml"
REQUIRED_QT_VERSION = (6, 4)
REQUIRED_QT_VERSION_TEXT = "6.4"

# Mirrors the Qt packages in the Classic Qt CI workflow. A contract test checks
# this list against that workflow so drift is detected offline.
BUILD_PACKAGES = (
    "qt6-base-dev",
    "qt6-declarative-dev",
    "qt6-declarative-dev-tools",
)
RUNTIME_PACKAGES = (
    "libqt6svg6",
    "qml6-module-qtquick",
    "qml6-module-qtquick-controls",
    "qml6-module-qtquick-layouts",
    "qml6-module-qtquick-window",
    "qml6-module-qtquick-templates",
    "qml6-module-qtqml",
    "qml6-module-qtqml-workerscript",
)
REQUIRED_PACKAGES = BUILD_PACKAGES + RUNTIME_PACKAGES
# CMake treats gio-unix-2.0 as optional: native launching has a fallback.
OPTIONAL_PACKAGES = ("libglib2.0-dev",)

_PACKAGE_RE = re.compile(r"[a-z0-9][a-z0-9+.-]{1,63}")
_VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}")
MAX_VERSION_CHARS = 40
MAX_VERSION_PART = 65535
QUERY_TIMEOUT_SECONDS = 2


def is_safe_package_name(name):
    """Accept only a strict Debian package-name subset, never shell syntax."""
    if not isinstance(name, str):
        return False
    return _PACKAGE_RE.fullmatch(name) is not None


def validate_package_names(names):
    """Return (safe names, rejected count) without echoing untrusted values."""
    safe = []
    rejected = 0
    for name in names:
        if is_safe_package_name(name):
            safe.append(name)
        else:
            rejected += 1
    return tuple(safe), rejected


def parse_version(text):
    """Parse a bounded dotted numeric version, or return None if untrusted."""
    if not isinstance(text, str) or len(text) > MAX_VERSION_CHARS:
        return None
    if _VERSION_RE.fullmatch(text) is None:
        return None
    parts = tuple(int(part) for part in text.split("."))
    if any(part > MAX_VERSION_PART for part in parts):
        return None
    return parts


def assess(qt_version=None, installed=None, tools=None, required_names=None):
    """Pure, deterministic report. Performs no I/O and no installation."""
    names = REQUIRED_PACKAGES if required_names is None else tuple(required_names)
    safe_names, rejected = validate_package_names(names)
    version = parse_version(qt_version)
    tools = dict(tools or {})
    installed = dict(installed or {})

    blockers = []
    if rejected:
        blockers.append(f"untrusted package name rejected ({rejected})")
    if version is None:
        blockers.append("Qt6Core version unavailable; pkg-config metadata missing")
    elif version < REQUIRED_QT_VERSION:
        blockers.append(
            f"installed Qt {qt_version} older than required "
            f"{REQUIRED_QT_VERSION_TEXT}"
        )
    if not tools.get("pkg-config", True):
        blockers.append("pkg-config not found; Qt version unverified")
    if not tools.get("dpkg-query", True):
        blockers.append("dpkg-query not found; package state UNKNOWN")

    packages = []
    missing = []
    unknown = []
    for name in safe_names:
        if name in installed:
            state = "INSTALLED" if installed[name] else "NOT_INSTALLED"
        else:
            state = "UNKNOWN"
        packages.append({"name": name, "status": state})
        if state == "NOT_INSTALLED":
            missing.append(name)
        elif state == "UNKNOWN":
            unknown.append(name)

    if rejected:
        status = "BLOCKED"
    elif version is not None and version < REQUIRED_QT_VERSION:
        status = "UPGRADE_QT"
    elif version is None:
        status = "UNVERIFIED"
    elif missing:
        status = "PACKAGES_MISSING"
    elif unknown:
        status = "UNVERIFIED"
    else:
        status = "READY"

    return {
        "schema_version": SCHEMA_VERSION,
        "probe_only": True,
        "install_attempted": False,
        "install_commands_run": [],
        "source": SOURCE_FILE,
        "package_source": PACKAGE_SOURCE,
        "required_qt_version": REQUIRED_QT_VERSION_TEXT,
        "qt_core_version": qt_version if version is not None else None,
        "qt_version_supported": bool(
            version is not None and version >= REQUIRED_QT_VERSION
        ),
        "status": status,
        "packages": packages,
        "missing_packages": missing,
        "unknown_packages": unknown,
        "optional_packages": list(OPTIONAL_PACKAGES),
        "blockers": blockers,
    }


def query_installed(names):
    """Read dpkg package state with argv, no shell and a fixed timeout."""
    installed = {}
    for name in names:
        if not is_safe_package_name(name):
            continue
        try:
            proc = subprocess.run(
                ["dpkg-query", "-W", "-f=${Status}", name],
                capture_output=True,
                text=True,
                timeout=QUERY_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        installed[name] = (
            proc.returncode == 0 and "install ok installed" in proc.stdout
        )
    return installed


def collect():
    """Build a report from the existing preflight probe; never install."""
    preflight = preflight_collect()
    tools = dict(preflight.get("commands_present", {}))
    tools["dpkg-query"] = shutil.which("dpkg-query") is not None
    installed = query_installed(REQUIRED_PACKAGES) if tools["dpkg-query"] else {}
    report = assess(preflight.get("qt6_core_version"), installed, tools)
    report["host_os"] = platform.system()
    report["mint_verified"] = bool(preflight.get("mint_identified"))
    return report


def main(argv=None):
    """Print a report; exit status 0 means the report ran, not that Qt works."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON evidence")
    args = parser.parse_args(argv)
    report = collect()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"QT_DEPENDENCY_PROBE_{report['status']}: "
            f"Qt={report['qt_core_version'] or 'unavailable'} "
            f"packages={len(report['packages'])}"
        )
        for blocker in report["blockers"]:
            print(f"BLOCKED: {blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
