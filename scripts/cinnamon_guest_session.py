"""Find the dedicated Mint Cinnamon X11 session without trusting an SSH shell env.

Read only same-UID process environment; never execute privileged commands.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

from scripts.mint_live_cinnamon_smoke import observe, session_ready

ALLOWED = {"DISPLAY", "XAUTHORITY", "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE",
           "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR"}
MAX_ENV = 65536


def parse_environ(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_ENV:
        raise ValueError("Unbounded process environment")
    result = {}
    for entry in raw.split(b"\0"):
        if b"=" not in entry:
            continue
        name, value = entry.split(b"=", 1)
        key = name.decode("ascii", errors="ignore")
        if key in ALLOWED:
            result[key] = value.decode("utf-8", errors="replace")
    return result


def find_cinnamon_session(*, proc=Path("/proc"), uid=None, home=None):
    actual_uid = os.geteuid() if uid is None else uid
    if actual_uid == 0:
        raise ValueError("Cinnamon GUI observer cannot run as root")
    expected_home = Path.home() if home is None else Path(home)
    if expected_home.name != "canopy-test":
        raise ValueError("Requires the dedicated canopy-test account")
    for pid_path in proc.iterdir():
        if not pid_path.name.isdecimal():
            continue
        try:
            if pid_path.stat().st_uid != actual_uid:
                continue
            if (pid_path / "comm").read_text(encoding="ascii").strip() != "cinnamon":
                continue
            environment = parse_environ((pid_path / "environ").read_bytes())
            if not session_ready(environment, actual_uid):
                continue
            auth = environment.get("XAUTHORITY") or str(expected_home / ".Xauthority")
            auth_path = Path(auth)
            if not auth_path.is_file() or auth_path.stat().st_uid != actual_uid:
                continue
            environment["XAUTHORITY"] = str(auth_path)
            return environment
        except (PermissionError, FileNotFoundError, ProcessLookupError, OSError):
            continue
    raise RuntimeError("No verified same-user Cinnamon X11 graphical session found")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run Classic visual smoke in dedicated Cinnamon login")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        environment = find_cinnamon_session()
        result = observe(args.root, environment=environment, uid=os.geteuid())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"BLOCKED/FAIL: {error}", file=sys.stderr)
        return 1
    # One machine-readable line for independent host report checking.
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
