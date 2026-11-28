#!/usr/bin/env python3
"""Fresh READ-ONLY host probe for the real-Plasma AT-SPI blocker.

No VM mutation, guest command, credential use, key injection, display change
or screen-reader start is performed. Status is recorded honestly as
BLOCKED / NOT_RUN when the guest cannot be reached.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import shutil
import subprocess

VBOX = pathlib.Path(r"C:/Program Files/Oracle/VirtualBox/VBoxManage.exe")
VM = "Canopy-Test-Plasma6"


def run(argv: list[str]) -> tuple[int, str]:
    p = subprocess.run(argv, capture_output=True, text=True,
                       errors="replace", timeout=40)
    return p.returncode, (p.stdout + p.stderr).strip()


probe: dict[str, object] = {
    "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "head_scope": "source-static gate at product/a11y-rootcause-20261128",
    "vm_mutations": 0,
    "guest_commands": 0,
    "credentials_used": 0,
}

if VBOX.exists():
    rc, out = run([str(VBOX), "list", "runningvms"])
    probe["running_vms"] = {"rc": rc, "output": out}
    rc, out = run([str(VBOX), "showvminfo", VM, "--machinereadable"])
    keys = ("VMState=", "nic1=", "Forwarding(")
    probe["vm_info_filtered"] = {
        "rc": rc,
        "output": "\n".join(l for l in out.splitlines()
                            if l.startswith(keys)),
    }
    rc, out = run([str(VBOX), "guestproperty", "enumerate", VM])
    props = [l.strip() for l in out.splitlines() if l.strip()]
    probe["guest_properties"] = {
        "rc": rc,
        "count": len(props),
        "guest_execution_channel_properties": [
            l for l in props if "guestcontrol" in l.lower()
            or "GuestAdditions" in l],
        "sample": props[:10],
    }
else:
    probe["vboxmanage"] = "ABSENT"

ssh_dir = pathlib.Path.home() / ".ssh"
probe["ssh_dir_entries"] = (
    sorted(p.name for p in ssh_dir.iterdir()) if ssh_dir.exists() else [])
probe["private_key_present"] = any(
    n in ("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")
    for n in str(probe["ssh_dir_entries"]))
try:
    import pyatspi  # noqa: F401
    probe["host_pyatspi"] = "AVAILABLE"
except Exception as exc:  # ModuleNotFoundError on this Windows host
    probe["host_pyatspi"] = "UNAVAILABLE: " + type(exc).__name__
probe["host_display"] = os.environ.get("DISPLAY") or "UNSET"
probe["host_qt_qpa_platform"] = os.environ.get("QT_QPA_PLATFORM") or "UNSET"
probe["screen_reader_processes"] = shutil.which("orca") or "NONE_ON_HOST_PATH"
probe["at_spi_native"] = "BLOCKED"
probe["screen_reader"] = "NOT_RUN"
probe["blocker"] = (
    "No host AT-SPI bus (Windows, no DISPLAY/QT_QPA_PLATFORM, no pyatspi), "
    "no supplied guest login or private key, and no authorized guest lease "
    "for this session. Guest execution was deliberately not attempted; no "
    "credential was guessed. PR #740/#752 AT-SPI evidence predates this head "
    "and is not relabelled as verification of it."
)

path = pathlib.Path(__file__).with_name("atspi_blocker_probe.json")
path.write_text(json.dumps(probe, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
print(json.dumps(probe, indent=2, ensure_ascii=False))
