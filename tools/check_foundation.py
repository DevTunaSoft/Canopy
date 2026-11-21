#!/usr/bin/env python3
"""Dependency-free checks for Canopy's initial engineering contract."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md",
    "AGENTS.md",
    "docs/ARCHITECTURE.md",
    "docs/QUALITY.md",
    "docs/ROADMAP.md",
)
LOCAL_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def validate(root=ROOT):
    errors = []
    for relative in REQUIRED:
        path = root / relative
        if not path.is_file():
            errors.append(f"Missing required file: {relative}")
            continue
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            errors.append(f"Empty required file: {relative}")
        for match in LOCAL_LINK.finditer(content):
            target = match.group(1).split("#", 1)[0].strip()
            if not target or target.startswith(("https://", "http://", "mailto:")):
                continue
            if not (path.parent / target).exists():
                errors.append(f"Broken relative link in {relative}: {target}")
    readme = root / "README.md"
    if readme.exists() and "The Familiar Feel. The Freedom of Linux." not in readme.read_text(encoding="utf-8"):
        errors.append("README missing current Canopy tagline")
    return errors


if __name__ == "__main__":
    issues = validate()
    for issue in issues:
        print("FAIL:", issue, file=sys.stderr)
    if issues:
        sys.exit(1)
    print("PASS: foundation files, tagline, and local Markdown links")
