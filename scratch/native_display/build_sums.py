#!/usr/bin/env python3
"""Write an LF-only SHA-256 manifest for the M4 display-response evidence.

Run from any cwd. The manifest lists only owned paths and excludes itself and
the still-writing full-suite log so the digest set stays reproducible.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "scratch" / "native_display"
EXCLUDE = {"SHA256SUMS.txt"}

paths = [
    "canopy_features/dock/display_change_response.py",
    "canopy_features/dock/display_geometry_contract.py",
    "canopy_features/dock/display_scaling_contract.py",
    "docs/NATIVE_DISPLAY_RESPONSE.md",
]
paths += sorted(
    "scratch/native_display/" + item.name
    for item in DIR.iterdir()
    if item.is_file() and item.name not in EXCLUDE
)

lines = []
for relative in paths:
    path = ROOT / relative
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    lines.append(digest + "  " + relative + "\n")
(DIR / "SHA256SUMS.txt").write_text("".join(lines), encoding="utf-8",
                                    newline="\n")
print("wrote %d entries" % len(lines))
