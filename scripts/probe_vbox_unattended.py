"""Probe VirtualBox unattended installer compatibility without launching a guest.

Dry-run success is a prerequisite, NOT proof a Linux Mint ISO installs correctly.
"""
import argparse
from pathlib import Path
import json
import re
import subprocess
import sys

from scripts.vbox_lab_controller import inspect_vm

VM = "Canopy-Test-Mint"


def inspect_installer(exe, iso, user_password_file, *,
                      runner=subprocess.run):
    iso = Path(iso).resolve()
    password = Path(user_password_file).resolve()
    if not iso.is_file() or iso.suffix.lower() != ".iso":
        raise ValueError("An existing locally verified Linux Mint ISO is required")
    if not password.is_file() or password.stat().st_size > 128:
        raise ValueError("A nonempty protected password-file is required")
    if not 0 < password.stat().st_size <= 128:
        raise ValueError("Password file is empty")
    state = inspect_vm(exe, runner=runner)
    if state["state"] != "poweroff":
        raise ValueError("Dedicated VM must be powered off")
    command = [str(exe), "unattended", "install", VM, "--iso=" + str(iso),
               "--user=canopy-test", "--user-password-file=" + str(password),
               "--no-install-additions", "--dry-run"]
    result = runner(command, capture_output=True, text=True,
                    errors="replace", check=False, timeout=45)
    return {"vm": VM, "vm_uuid": state["uuid"],
            "status": "CAPABILITY_PROBE_PASSED" if result.returncode == 0 else "BLOCKED",
            "exit_code": result.returncode,
            "installation_started": False,
            "note": "Dry-run only. Mint 22.3 Ubiquity compatibility is not verified",
            "reason": "" if result.returncode == 0 else "VirtualBox rejected unattended dry-run for this ISO"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Non-destructive Mint unattended install probe")
    parser.add_argument("--vboxmanage", required=True, type=Path)
    parser.add_argument("--iso", required=True, type=Path)
    parser.add_argument("--password-file", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = inspect_installer(args.vboxmanage, args.iso, args.password_file)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "CAPABILITY_PROBE_PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
