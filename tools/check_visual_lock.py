#!/usr/bin/env python3
"""Read-only visual-lock check for Canopy Classic.

Verifies byte-exact approved assets from the recorded manifest and reports,
but never creates, visual baselines. A missing owner-approved baseline is
reported as AWAITING_CHATGPT_VISUAL_APPROVAL and is not treated as a pass.
The tool never rewrites assets, screenshots or manifests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

MANIFEST = Path("prototype/classic/assets/approved/manifest.json")
AWAITING = "AWAITING_CHATGPT_VISUAL_APPROVAL"
IMAGE_REF = re.compile(r"(?i)(?:image://[A-Za-z0-9_/-]+|[A-Za-z0-9_./-]+\.(?:png|svg))")
UI_SOURCE = ("*.qml", "*.cpp", "*.h")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_approved_assets(root: Path) -> list[str]:
    """Fail-closed byte-exact check of every manifest-listed asset."""
    problems: list[str] = []
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        return ["approved asset manifest missing"]
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ["approved asset manifest unreadable: " + str(exc)[:80]]
    assets = list(data.get("icons", []))
    if isinstance(data.get("wallpaper"), dict):
        assets.append(data["wallpaper"])
    if not assets:
        return ["approved asset manifest has no entries"]
    for item in assets:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            problems.append("invalid approved asset entry")
            continue
        relative = item["path"]
        if relative.startswith("/") or ".." in Path(relative).parts:
            problems.append("unsafe approved asset path: " + relative)
            continue
        path = root / MANIFEST.parent / relative
        if not path.is_file():
            problems.append("approved asset missing: " + relative)
            continue
        expected = item.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            problems.append("invalid approved asset hash: " + relative)
        elif sha256(path) != expected.lower():
            problems.append("approved asset modified: " + relative)
    return problems


def verify_baseline(root: Path, baseline: Path | None) -> tuple[list[str], bool]:
    """Compare protected UI sources to an owner-supplied baseline, if any.

    Returns (problems, awaiting_owner). A missing baseline is a flag, not a
    pass: this tool must never silently bless the current appearance.
    """
    if baseline is None or not baseline.is_file():
        return [], True
    try:
        data = json.loads(baseline.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ["visual baseline unreadable: " + str(exc)[:80]], False
    entries = data.get("files", []) if isinstance(data, dict) else []
    if not isinstance(entries, list) or not entries:
        return ["visual baseline has no files"], False
    problems = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            problems.append("invalid baseline entry")
            continue
        relative = item["path"]
        if relative.startswith("/") or ".." in Path(relative).parts:
            problems.append("unsafe baseline path: " + relative)
            continue
        path = root / relative
        if not path.is_file():
            problems.append("protected source missing: " + relative)
        elif not isinstance(item.get("sha256"), str) or \
                sha256(path) != item["sha256"].lower():
            problems.append("protected source changed: " + relative)
    return problems, False


def scan_ui_references(root: Path) -> bool:
    """Return True when UI sources reference imagery outside the locked manifest."""
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        return True
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    locked = {Path(item["path"]).name for item in data.get("icons", [])
              if isinstance(item, dict) and isinstance(item.get("path"), str)}
    wallpaper = data.get("wallpaper")
    if isinstance(wallpaper, dict) and isinstance(wallpaper.get("path"), str):
        locked.add(Path(wallpaper["path"]).name)
    prototype = root / "prototype/classic"
    for pattern in UI_SOURCE:
        for source in prototype.glob("**/" + pattern):
            text = source.read_text(encoding="utf-8", errors="replace")
            for match in IMAGE_REF.finditer(text):
                name = Path(match.group(0)).name
                if name.lower().endswith((".png", ".svg")) and name not in locked:
                    return True
    return False


def check(root: Path, baseline: Path | None = None) -> dict:
    problems = verify_approved_assets(root)
    baseline_problems, awaiting = verify_baseline(root, baseline)
    problems.extend(baseline_problems)
    awaiting = awaiting or scan_ui_references(root)
    return {
        "status": "FAIL" if problems else (AWAITING if awaiting else "PASS"),
        "approved_assets_checked": len(
            json.loads((root / MANIFEST).read_text(encoding="utf-8")).get("icons", []))
        if (root / MANIFEST).is_file() else 0,
        "problems": problems,
        "baseline": "owner-supplied" if baseline and baseline.is_file() else "none",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = check(args.root, args.baseline)
    except (OSError, ValueError) as exc:
        print("VISUAL_LOCK_BLOCKED: " + str(exc), file=__import__("sys").stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True) if args.json
          else f"VISUAL_LOCK {result['status']} problems={len(result['problems'])}")
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
