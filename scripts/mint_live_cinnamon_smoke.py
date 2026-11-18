"""Launch Canopy Classic in a real Mint Cinnamon X11 login and inspect windows.

This is an explicitly opt-in in-session smoke test, not Xvfb compatibility.
Requires independent X11 window enumeration and process survival.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def session_ready(env, uid):
    desktop = env.get("XDG_CURRENT_DESKTOP", "").lower().split(":")
    session = env.get("XDG_SESSION_TYPE", "").lower()
    return (uid != 0 and ("cinnamon" in desktop or "x-cinnamon" in desktop) and session == "x11"
            and bool(re.fullmatch(r":[0-9]+(?:\.[0-9]+)?", env.get("DISPLAY", "")))
            and env.get("CANOPY_ISOLATED_DISPLAY") != "1")


def parse_wmctrl(output, pid):
    matches = []
    for line in output.splitlines():
        parts = line.split(None, 4)
        if len(parts) != 5:
            continue
        try:
            item_pid = int(parts[2])
        except ValueError:
            continue
        if item_pid == pid and parts[4].endswith("Canopy Classic preview"):
            matches.append(parts[0])
    return matches


def observe(root, *, environment=None, uid=None, start=subprocess.Popen,
            run=subprocess.run, sleep=time.sleep, clock=time.monotonic):
    env = dict(os.environ if environment is None else environment)
    real_uid = os.geteuid() if uid is None else uid
    if not session_ready(env, real_uid):
        raise ValueError("Requires ordinary user in a real Cinnamon X11 login session")
    root = Path(root).resolve()
    if not (root / "canopy/classic_gtk.py").is_file():
        raise ValueError("Canopy source checkout missing")
    child_env = {**env, "PYTHONDONTWRITEBYTECODE": "1"}
    process = start([sys.executable, "-B", "-m", "canopy.classic_gtk", "--safe-defaults"],
                    cwd=root, env=child_env, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
    deadline = clock() + 12
    attempts = 0
    observations = []
    try:
        while clock() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Canopy preview exited before visual confirmation")
            result = run(["wmctrl", "-lp"], capture_output=True, text=True,
                         timeout=4, check=False, env=child_env)
            if result.returncode:
                raise RuntimeError("wmctrl could not inspect Cinnamon window manager")
            ids = parse_wmctrl(result.stdout, process.pid)
            observations.append(len(ids))
            attempts += 1
            if len(set(ids)) == 2:
                # Independent xdotool window enumeration (not same output source).
                found = run(["xdotool", "search", "--onlyvisible", "--pid",
                             str(process.pid), "--name", "Canopy Classic preview"],
                            capture_output=True, text=True, timeout=4,
                            check=False, env=child_env)
                candidates = [x for x in found.stdout.splitlines() if x.strip().isdigit()]
                if found.returncode == 0 and len(set(candidates)) >= 2:
                    return {"status": "PASS", "pid": process.pid, "window_count": 2,
                            "wmctrl_windows": len(set(ids)), "xdotool_windows": len(set(candidates)),
                            "polls": attempts, "desktop": "Cinnamon X11",
                            "limitation": "Launch/window evidence only, not full UI behavior"}
            sleep(0.3)
        raise RuntimeError("Two Canopy windows not independently observed within deadline")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Test Canopy Classic in real Cinnamon X11")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = observe(args.root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"BLOCKED/FAIL: {error}\n")
    print("Canopy Classic visible in actual Cinnamon X11; full interaction tests pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
