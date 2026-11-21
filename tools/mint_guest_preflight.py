#!/usr/bin/env python3
"""Read-only Linux Mint guest readiness probe; NOT a VM acceptance test.

Reports only non-personal environment readiness facts. Never changes the
default session, installs packages, runs Qt, or modifies system settings.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


NEEDED = ("cmake", "pkg-config", "ninja", "xvfb-run")
MAX_RELEASE_BYTES = 4096


def parse_release(data):
    """Parse the small ID, VERSION_ID and NAME subset of os-release safely."""
    result = {}
    for line in data.splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in ("ID", "VERSION_ID", "PRETTY_NAME"):
            continue
        value = value.strip()
        if value.startswith(("'", '"')) or value.endswith(("'", '"')):
            if len(value) < 2 or value[0] != value[-1]:
                continue
            value = value[1:-1]
        # Avoid logging arbitrary control characters or excessively long data.
        if not value or len(value) > 120 or any(ord(c) < 32 for c in value):
            continue
        result[key] = value
    return result


def assess(release, env, available, qt_version=None):
    """Pure, deterministic readiness evaluation with explicit blockers."""
    distro = release.get("ID", "").lower()
    is_mint = distro == "linuxmint"
    desktop = env.get("XDG_CURRENT_DESKTOP", "")
    session = env.get("XDG_SESSION_TYPE", "")
    # The desktop field may be colon-separated, but individual entries
    # must match Cinnamon exactly; substring matches would be unsafe.
    cinnamon = (isinstance(desktop, str)
                and any(name in ("X-Cinnamon", "Cinnamon")
                        for name in desktop.split(":")))
    # DISPLAY does not establish a Wayland session and WAYLAND_DISPLAY
    # does not establish X11. These are readiness hints, not proof of a
    # connected compositor or functioning user session.
    has_display = (
        bool(env.get("DISPLAY")) if session == "x11" else
        bool(env.get("WAYLAND_DISPLAY")) if session == "wayland" else False
    )
    commands = {name: bool(available.get(name, False)) for name in NEEDED}
    reasons = []
    if not is_mint:
        reasons.append("guest is not verified as Linux Mint")
    if not has_display:
        reasons.append("no graphical display for declared session")
    if not desktop:
        reasons.append("desktop session identity not provided")
    elif not cinnamon:
        reasons.append("Cinnamon desktop not identified")
    if not session:
        reasons.append("session type not provided")
    elif session not in ("x11", "wayland"):
        reasons.append("unsupported graphical session type")
    for name, present in commands.items():
        if not present:
            reasons.append(f"required build/smoke tool not found: {name}")
    if qt_version is None:
        reasons.append("Qt6Core pkg-config metadata not available")
    return {
        "schema_version": 1,
        "probe_only": True,
        "mint_guest_acceptance": "NOT_RUN",
        "runtime_functional_test": "NOT_RUN",
        "visual_acceptance": "NOT_RUN",
        "status": "READY_FOR_TESTS" if not reasons else "BLOCKED",
        "mint_identified": is_mint,
        "version_id": release.get("VERSION_ID", "unknown")[:30],
        "desktop_session_present": bool(desktop),
        "graphical_display_present": has_display,
        "session_type": session if session in ("x11", "wayland") else "other-or-unknown",
        "qt6_core_version": qt_version,
        "commands_present": commands,
        "blockers": reasons,
    }


def collect():
    path = Path("/etc/os-release")
    try:
        if path.stat().st_size > MAX_RELEASE_BYTES:
            raise ValueError("oversized os-release")
        release = parse_release(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        release = {}
    available = {name: shutil.which(name) is not None for name in NEEDED}
    version = None
    if available["pkg-config"]:
        try:
            result = subprocess.run(
                ["pkg-config", "--modversion", "Qt6Core"],
                timeout=3, capture_output=True, text=True, check=False,
            )
            candidate = result.stdout.strip()
            if result.returncode == 0 and candidate and len(candidate) < 40 \
                    and all(c.isdigit() or c == "." for c in candidate):
                version = candidate
        except (OSError, subprocess.TimeoutExpired):
            pass
    return assess(release, os.environ, available, version)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON evidence")
    args = parser.parse_args(argv)
    result = collect()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"MINT_GUEST_PREFLIGHT_{result['status']}: "
              f"Mint={result['mint_identified']} "
              f"Qt={result['qt6_core_version'] or 'unavailable'}")
        for blocker in result["blockers"]:
            print(f"BLOCKED: {blocker}")
    # A green probe is only readiness to perform testing, not acceptance.
    return 0 if result["status"] == "READY_FOR_TESTS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
