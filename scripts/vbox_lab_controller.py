"""Restricted VirtualBox host-side operations for a disposable Canopy Mint VM.

No guest login credentials, no network listener, no arbitrary VBoxManage command.
Reset is deliberately gated by a local, dedicated-VM authorization switch.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

VM_NAME = "Canopy-Test-Mint"
SNAPSHOT = "Canopy-Clean"
UUID = re.compile(r"^[0-9a-fA-F-]{36}$")


def machine_values(text):
    result = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        result[key] = value
    return result


def invoke(exe, args, *, runner=subprocess.run):
    result = runner([str(exe), *args], capture_output=True, text=True,
                    errors="replace", timeout=45, check=False)
    if result.returncode:
        raise RuntimeError(f"VBoxManage operation failed ({args[0]})")
    if len(result.stdout) > 100000:
        raise ValueError("VBoxManage response too large")
    return result.stdout


def inspect_vm(exe, *, runner=subprocess.run):
    values = machine_values(invoke(exe, ["showvminfo", VM_NAME, "--machinereadable"], runner=runner))
    if values.get("name") != VM_NAME:
        raise ValueError("Selected VM is not the dedicated Canopy testing VM")
    if not UUID.fullmatch(values.get("UUID", "")):
        raise ValueError("Missing stable VM UUID")
    state = values.get("VMState")
    if state not in ("running", "poweroff", "saved", "aborted", "paused"):
        raise ValueError("Unknown VM state; refuse state-changing operations")
    return {"name": VM_NAME, "uuid": values["UUID"], "state": state}


def operate(exe, action, *, allow_reset=False, runner=subprocess.run):
    if action not in ("status", "start", "reset"):
        raise ValueError("Unknown operation")
    before = inspect_vm(exe, runner=runner)
    if action == "status":
        return {"status": "PASS", "operation": "status", "vm": before}
    if action == "start":
        if before["state"] != "poweroff":
            raise ValueError("VM must be powered off to start; no implicit reset")
        invoke(exe, ["startvm", VM_NAME, "--type", "headless"], runner=runner)
        after = inspect_vm(exe, runner=runner)
        if after["uuid"] != before["uuid"] or after["state"] != "running":
            raise RuntimeError("VM start did not reach expected state")
        return {"status": "PASS", "operation": "start", "vm": after}
    if not allow_reset:
        raise PermissionError("Explicit --allow-reset required for destructive snapshot restoration")
    if before["state"] != "poweroff":
        raise ValueError("Power off the dedicated VM separately before snapshot restoration")
    # Exact named snapshot must exist; do not restore an unknown 'current' snapshot.
    invoke(exe, ["snapshot", VM_NAME, "showvminfo", SNAPSHOT], runner=runner)
    invoke(exe, ["snapshot", VM_NAME, "restore", SNAPSHOT], runner=runner)
    after = inspect_vm(exe, runner=runner)
    if after["uuid"] != before["uuid"] or after["state"] != "poweroff":
        raise RuntimeError("Snapshot restore failed identity/state verification")
    return {"status": "PASS", "operation": "reset", "vm": after, "snapshot": SNAPSHOT}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Restricted Canopy VirtualBox VM controller")
    parser.add_argument("action", choices=("status", "start", "reset"))
    parser.add_argument("--vboxmanage", type=Path, default=Path("VBoxManage"))
    parser.add_argument("--allow-reset", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = operate(args.vboxmanage, args.action, allow_reset=args.allow_reset)
    except (OSError, ValueError, RuntimeError, PermissionError, subprocess.TimeoutExpired) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
