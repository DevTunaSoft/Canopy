#!/usr/bin/env python3
"""Read-only Plasma guest readiness probe for the M4 display response.

Run this inside a real Plasma 6 session once a compiled host adapter exists.
It never changes display configuration, installs packages, guesses credentials
or starts a service. Without ``--adapter`` it reports ``HOST_ADAPTER_ABSENT``
and ``NATIVE_RUNTIME=NOT RUN``; it never upgrades a structural check into a
runtime pass. With ``--adapter`` it executes exactly one trusted command that
prints adapter JSON and records the observed display configuration.
"""
import argparse
import json
import os
import platform
import shlex
import subprocess
import sys


def run(argv, timeout=30):
    try:
        completed = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, text=True, check=False)
        return {"argv": argv, "rc": completed.returncode,
                "stdout": completed.stdout[:8000],
                "stderr": completed.stderr[:2000]}
    except Exception as exc:
        return {"argv": argv, "rc": None, "error": repr(exc)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", help="trusted adapter command (no shell)")
    parser.add_argument("--out", help="optional JSON output path")
    args = parser.parse_args()

    desktop = (sys.platform or "") + ":" + platform.platform()
    env = {
        "desktop_token_present": bool(os.environ.get("XDG_CURRENT_DESKTOP")),
        "plasma_token_present": "plasma" in os.environ.get(
            "XDG_CURRENT_DESKTOP", "").lower(),
        "session_type": os.environ.get("XDG_SESSION_TYPE", "unset"),
        "display_present": bool(os.environ.get("DISPLAY")),
        "wayland_present": bool(os.environ.get("WAYLAND_DISPLAY")),
    }
    observed = run(["xrandr", "--listmonitors"]) if env["display_present"] else None

    adapter = None
    if args.adapter:
        adapter = run(shlex.split(args.adapter))
        if adapter.get("rc") == 0:
            try:
                adapter["json"] = json.loads(adapter["stdout"])
            except (ValueError, TypeError):
                adapter["json"] = None

    session_ok = (env["plasma_token_present"]
                  and env["session_type"] in ("x11", "wayland")
                  and (env["display_present"] or env["wayland_present"]))
    adapter_ok = bool(adapter and adapter.get("json"))
    verdict = "NATIVE_RUNTIME" if session_ok and adapter_ok else "NOT_RUN"

    report = {
        "artifact": "m4_plasma_guest_readiness_probe",
        "classification": "NATIVE_RUNTIME" if verdict == "NATIVE_RUNTIME"
                          else "NOT_RUN",
        "host": desktop,
        "environment": env,
        "xrandr_listmonitors": observed,
        "adapter": adapter or {"status": "HOST_ADAPTER_ABSENT"},
        "verdict": verdict,
        "note": ("A readiness probe is not acceptance. Attach real screenshots "
                 "and independent review before claiming PASS."),
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
