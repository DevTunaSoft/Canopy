"""Unprivileged, non-destructive test runner for a disposable Linux Mint VM.

Runs a fixed allowlist of commands, with per-check timeouts and bounded logs.
Never installs packages, changes a login session, or executes a shell string.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

COMMANDS = {
    "unit": ("python3", "-m", "unittest", "discover", "-s", "tests", "-v"),
    "syntax": ("python3", "-m", "compileall", "-q", "canopy", "tests", "scripts"),
    "gtk": ("xvfb-run", "-a", "/usr/bin/python3", "-m", "unittest", "discover", "-s", "tests", "-v"),
    "cinnamon": ("python3", "-B", "-m", "scripts.cinnamon_guest_session"),
}
MAX_OUTPUT = 80_000

GTK_PROBE = (
    "xvfb-run", "-a", "/usr/bin/python3", "-c",
    "import gi; gi.require_version('Gtk', '3.0'); "
    "from gi.repository import Gtk; "
    "raise SystemExit(0 if Gtk.init_check()[0] else 3)",
)


def gtk_readiness(timeout, *, executor=subprocess.run, which=shutil.which):
    """Require a working GTK3 graphical display; don't accept skipped GUI tests."""
    missing = [program for program in ("xvfb-run", "xauth", "/usr/bin/python3")
               if which(program) is None]
    if missing:
        return "Missing GTK test dependencies: " + ", ".join(missing)
    try:
        probe = executor(GTK_PROBE, capture_output=True, text=True,
                         errors="replace", timeout=min(timeout, 15),
                         check=False, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    except (OSError, subprocess.TimeoutExpired) as error:
        return "GTK3 display probe unavailable: " + type(error).__name__
    if probe.returncode != 0:
        return "GTK3 display or Python GI introspection unavailable"
    return None



def run_check(name, command, root, timeout, *, executor=subprocess.run, which=shutil.which):
    """Run a predefined argv command; never invoke a shell."""
    start = time.monotonic()
    if which(command[0]) is None:
        return {"name": name, "status": "BLOCKED",
                "reason": f"Missing executable: {command[0]}", "duration_seconds": 0}
    if name == "gtk":
        blocker = gtk_readiness(timeout, executor=executor, which=which)
        if blocker is not None:
            return {"name": name, "status": "BLOCKED", "reason": blocker,
                    "duration_seconds": round(time.monotonic() - start, 3)}
    try:
        result = executor(command, cwd=root, capture_output=True, text=True,
                          errors="replace", timeout=timeout, check=False,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    except subprocess.TimeoutExpired as error:
        out = error.stdout or b""
        err = error.stderr or b""
        if isinstance(out, bytes):
            out = out.decode("utf-8", errors="replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", errors="replace")
        return {"name": name, "status": "FAIL", "reason": "TIMEOUT",
                "output": (out + err)[-MAX_OUTPUT:],
                "duration_seconds": round(time.monotonic() - start, 3)}
    except OSError as error:
        return {"name": name, "status": "BLOCKED", "reason": str(error),
                "duration_seconds": round(time.monotonic() - start, 3)}
    output = (result.stdout or "") + (result.stderr or "")
    return {"name": name, "status": "PASS" if result.returncode == 0 else "FAIL",
            "exit_code": result.returncode, "output": output[-MAX_OUTPUT:],
            "output_truncated": len(output) > MAX_OUTPUT,
            "duration_seconds": round(time.monotonic() - start, 3)}


def execute(root, output_path, checks, timeout=120, *, runner=run_check):
    root = Path(root).resolve()
    output_path = Path(output_path).resolve()
    if not (root / "canopy" / "__init__.py").is_file() or not (root / "tests").is_dir():
        raise ValueError("--root must be the checked-out Canopy repository")
    if not 1 <= timeout <= 900:
        raise ValueError("--timeout must be between 1 and 900 seconds")
    results = [runner(name, COMMANDS[name], root, timeout) for name in checks]
    status = "FAIL" if any(r["status"] == "FAIL" for r in results) else (
        "BLOCKED" if any(r["status"] == "BLOCKED" for r in results) else "PASS")
    report = {"schema_version": 1, "generated_utc": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "python": sys.version.split()[0],
              "repository": str(root), "status": status, "checks": results}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        os.replace(temp, output_path)
    finally:
        temp.unlink(missing_ok=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Unattended Canopy VM test checks")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("test-results/mint-testlab.json"))
    parser.add_argument("--checks", nargs="+", choices=sorted(COMMANDS),
                        default=["unit", "syntax", "gtk"])
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    try:
        report = execute(args.root, args.output, args.checks, args.timeout)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Canopy test-lab: {report['status']} — report: {args.output}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
