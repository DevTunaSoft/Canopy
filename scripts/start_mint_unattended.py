"""Opt-in VirtualBox unattended Mint install attempt on the dedicated disposable VM.

This can START an installation if supported. It never claims a Mint install
succeeded without separate postboot, GUI, and SSH acceptance evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from scripts.probe_vbox_unattended import inspect_installer
from scripts.vbox_lab_controller import inspect_vm

SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
UUID = re.compile(r"[0-9a-fA-F-]{36}\Z")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def start(executable, iso, password_file, expected_iso_sha256,
          expected_vm_uuid, *, authorized=False, runner=subprocess.run):
    if not authorized:
        raise PermissionError("Explicit dedicated disposable-VM install authorization required")
    if not isinstance(expected_iso_sha256, str) or not SHA256.fullmatch(expected_iso_sha256):
        raise ValueError("Expected approved SHA256 required")
    if not isinstance(expected_vm_uuid, str) or not UUID.fullmatch(expected_vm_uuid):
        raise ValueError("Explicit dedicated VM UUID required")
    iso = Path(iso).resolve()
    if not iso.is_file() or iso.suffix.lower() != ".iso":
        raise ValueError("Mint ISO file not present")
    if sha256(iso) != expected_iso_sha256.lower():
        raise ValueError("Mint ISO does not match authenticated expected digest")
    initial = inspect_vm(executable, runner=runner)
    if initial["uuid"].lower() != expected_vm_uuid.lower() or initial["state"] != "poweroff":
        raise ValueError("VM UUID/state does not match approved disposable target")
    test = inspect_installer(executable, iso, password_file, runner=runner)
    if test["status"] != "CAPABILITY_PROBE_PASSED" or test["vm_uuid"].lower() != expected_vm_uuid.lower():
        raise RuntimeError("VirtualBox did not approve unattended Mint ISO dry-run")
    # VirtualBox itself controls guest install. Never run an arbitrary shell.
    command = [str(executable), "unattended", "install", "Canopy-Test-Mint",
               "--iso=" + str(iso), "--user=canopy-test",
               "--user-password-file=" + str(Path(password_file).resolve()),
               "--no-install-additions", "--start-vm=headless"]
    result = runner(command, capture_output=True, text=True, errors="replace",
                    timeout=60, check=False)
    if result.returncode != 0:
        raise RuntimeError("VirtualBox unattended install request failed")
    # No PASS: the OS installer may still hang/fail later.
    return {"status": "INSTALL_STARTED_NOT_VERIFIED",
            "vm_uuid": expected_vm_uuid, "iso_sha256": expected_iso_sha256.lower(),
            "os_installed": False, "cinnamon_verified": False,
            "next_required": "Independent guest boot, SSH and real Cinnamon acceptance"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit disposable Mint unattended install attempt")
    parser.add_argument("--vboxmanage", type=Path, required=True)
    parser.add_argument("--iso", type=Path, required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--iso-sha256", required=True)
    parser.add_argument("--vm-uuid", required=True)
    parser.add_argument("--authorize-disposable-install", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = start(args.vboxmanage, args.iso, args.password_file, args.iso_sha256,
                       args.vm_uuid, authorized=args.authorize_disposable_install)
    except (PermissionError, ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
