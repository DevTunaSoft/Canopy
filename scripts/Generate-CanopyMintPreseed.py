#!/usr/bin/env python3
"""Generate a Mint/Ubiquity preseed for a disposable, isolated test VM.

This does not modify an ISO or disk. The builder must integrate and validate it.
"""
import argparse
import pathlib
import re
import subprocess
import sys

USERNAME = "canopy-test"
TEST_PASSWORD = "12345678"

def make_preseed(password_hash: str) -> str:
    if not re.fullmatch(r"\$6\$[A-Za-z0-9./$]+", password_hash):
        raise ValueError("Expected SHA-512 crypt hash")
    return "\n".join([
        "d-i debian-installer/locale string en_US.UTF-8",
        "d-i keyboard-configuration/layoutcode string us",
        "d-i time/zone string America/Chicago",
        "d-i clock-setup/utc boolean true",
        "d-i passwd/user-fullname string Canopy Test",
        f"d-i passwd/username string {USERNAME}",
        f"d-i passwd/user-password-crypted password {password_hash}",
        "d-i user-setup/allow-password-weak boolean true",
        "d-i partman-auto/method string regular",
        "d-i partman-auto/choose_recipe select atomic",
        "d-i partman-partitioning/confirm_write_new_label boolean true",
        "d-i partman/choose_partition select finish",
        "d-i partman/confirm boolean true",
        "d-i partman/confirm_nooverwrite boolean true",
        "d-i ubiquity/summary note",
        "d-i ubiquity/reboot boolean true",
        "",
    ])

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--disposable-vm", action="store_true", help="Explicitly acknowledge disposable VM only")
    args = parser.parse_args()
    if not args.disposable_vm:
        parser.error("Refusing to prepare destructive partitioning preseed without --disposable-vm")
    try:
        result = subprocess.run(["openssl", "passwd", "-6", "-stdin"], input=TEST_PASSWORD + "\n",
                                text=True, capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"Unable to generate password hash: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(make_preseed(result.stdout.strip()), encoding="utf-8")
    print(f"Wrote VM-only preseed: {args.output}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
