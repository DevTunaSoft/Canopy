#!/usr/bin/env python3
"""Safely prepend an unattended entry to a known ISOLINUX BIOS menu."""
from pathlib import Path
import re
import sys

def patch(text: str) -> str:
    if "LABEL canopy-auto" in text:
        raise ValueError("Canopy entry already exists")
    # Only modify known menus with explicit casper kernel/initrd paths.
    kernel = re.search(r"(?im)^\s*(?:KERNEL|LINUX)\s+(/?casper/vmlinuz\S*)\s*$", text)
    initrd = re.search(r"(?im)\binitrd=(/?casper/initrd\S*)", text)
    if not kernel or not initrd:
        raise ValueError("Unsupported BIOS menu: missing casper kernel/initrd")
    k = "/" + kernel.group(1).lstrip("/")
    i = "/" + initrd.group(1).lstrip("/")
    # Fail closed if the menu delegates its default to another configuration.
    if re.search(r"(?im)^\s*(?:CONFIG|UI)\s+", text):
        raise ValueError("Unsupported BIOS menu: delegated menu configuration")
    entry = (
        "DEFAULT canopy-auto\n"
        "TIMEOUT 10\n"
        "LABEL canopy-auto\n"
        "  MENU LABEL Canopy disposable VM automatic installation\n"
        f"  KERNEL {k}\n"
        f"  APPEND initrd={i} boot=casper automatic-ubiquity only-ubiquity "
        "file=/cdrom/preseed/canopy.seed noprompt ---\n"
    )
    # Remove pre-existing DEFAULT/TIMEOUT directives to avoid conflicting settings.
    original = re.sub(r"(?im)^\s*(?:DEFAULT|TIMEOUT)\s+[^\n]*\n", "", text)
    return entry + "\n" + original

def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: Patch-CanopyBiosMenu.py isolinux.cfg", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    updated = patch(path.read_text(encoding="utf-8"))
    path.write_text(updated, encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
