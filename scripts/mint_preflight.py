"""Read-only Linux Mint VM readiness probe.

Reports prerequisites for later tests; makes no host or VM changes.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def parse_os_release(contents):
    values = {}
    for line in contents.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        values[key] = value
    return values


def detect(*, os_release, environ, which, probe_gtk, geteuid):
    """Return evidence of readiness, not a claim that Mint GUI was tested."""
    distro = parse_os_release(os_release)
    checks = []
    def add(name, passed, detail):
        checks.append({"name": name, "status": "PASS" if passed else "BLOCKED",
                       "detail": detail})
    add("linux-mint", distro.get("ID", "").lower() == "linuxmint",
        "Detected ID=" + distro.get("ID", "<missing>"))
    add("unprivileged", geteuid() != 0, "Test process must not run as root")
    for executable in ("python3", "xvfb-run", "git"):
        add(executable, which(executable) is not None, "Executable on PATH")
    add("gtk3-python", probe_gtk(), "System Python GTK3 introspection import")
    desktop = environ.get("XDG_CURRENT_DESKTOP", "")
    add("cinnamon-session", "cinnamon" in desktop.lower().split(":"),
        "Desktop=" + (desktop[:100] or "<unavailable>"))
    display = environ.get("DISPLAY", "")
    add("x11-display", display.startswith(":") and len(display) <= 80,
        "X11 DISPLAY configured (Wayland-only not sufficient)")
    return {"schema_version": 1,
            "status": "PASS" if all(c["status"] == "PASS" for c in checks) else "BLOCKED",
            "distro": {"id": distro.get("ID"), "version": distro.get("VERSION_ID")},
            "checks": checks, "note": "Preflight only; no Cinnamon UI tests were executed"}


def gtk_available():
    result = subprocess.run(
        ["/usr/bin/python3", "-c",
         "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk"],
        timeout=10, capture_output=True, check=False)
    return result.returncode == 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Canopy Mint readiness probe")
    parser.add_argument("--output", type=Path, default=Path("test-results/mint-preflight.json"))
    args = parser.parse_args(argv)
    try:
        os_release = Path("/etc/os-release").read_text(encoding="utf-8")
        report = detect(os_release=os_release, environ=os.environ, which=shutil.which,
                        probe_gtk=gtk_available, geteuid=os.geteuid)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print(f"Mint preflight: {report['status']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
