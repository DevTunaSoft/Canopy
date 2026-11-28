#!/usr/bin/env python3
"""Recompute native-Plasma accessibility evidence from captured artifacts.

STATIC/CI-SCOPED. This script never starts or logs into the VM, never queries a
live AT-SPI bus and never starts a screen reader. It reads already-captured
evidence bytes, recomputes counts, and probes only the *host* VM state so a
serialization blocker can be recorded honestly.

Usage:
    python scratch/native_a11y/verify_native_a11y.py <evidence-root> [output.json]
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIZES = ("1920x1080", "1200x750", "760x500")
DOCK_TILES = (
    "Browser preview", "Mail preview", "Files preview", "Calendar preview",
    "Photos preview", "Music preview", "Terminal preview", "Settings preview",
)
SCREEN_READER_RE = re.compile(
    r"\b(orca|screen[ -]?reader|speak|speech|announce(?:ment)?)\b", re.I)

# Role set before the bounded fix (canopy_features/accessibility/
# screen_reader_metadata.py at ec910d7a). Used only to quantify the defect.
LEGACY_KNOWN_ROLES = frozenset({
    "alert", "button", "checkBox", "comboBox", "container", "dialog",
    "group", "image", "label", "link", "list", "listItem", "menu",
    "menuItem", "menuSeparator", "progressBar", "radioButton", "row",
    "scrollBar", "slider", "spinBox", "staticText", "switch", "tab",
    "tabItem", "table", "textField", "toolButton", "window",
})
LEGACY_NAMED_ROLES = frozenset({
    "button", "checkBox", "comboBox", "link", "listItem", "menuItem",
    "radioButton", "slider", "spinBox", "switch", "tab", "tabItem",
    "textField", "toolButton", "alert", "image", "staticText",
})
VM_NAME = "Canopy-Test-Plasma6"
VBOXMANAGE = Path("C:/Program Files/Oracle/VirtualBox/VBoxManage.exe")
PERF_ARTIFACTS = (
    "native_perf_vm_info_probe.txt",
    "wt-native-perf-baseline-20261127",
    "native_build_baseline_vm.lock",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path):
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def iso_mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def size_report(evidence: Path, size: str) -> dict:
    per_size = evidence / "native_classic_functional_evidence2" / "per_size" / size
    extra = evidence / "native_classic_functional_evidence3"
    summary_path = per_size / "a11y_summary.json"
    extents_path = per_size / "a11y_extents.jsonl"
    summary = load_json(summary_path)
    extents = load_jsonl(extents_path)
    elements = summary.get("elements", [])

    named = sum(1 for e in elements if str(e.get("name") or "").strip())
    unnamed = [
        {"index": i, "role": e.get("role", ""), "depth": e.get("depth")}
        for i, e in enumerate(elements)
        if not str(e.get("name") or "").strip()
    ]
    roles = collections.Counter(str(e.get("role", "")) for e in elements)
    described = sum(1 for e in elements if "description" in e)

    legacy_invalid_roles = sorted(
        role for role in roles if role not in LEGACY_KNOWN_ROLES)
    legacy_invalid = sum(
        count for role, count in roles.items()
        if role not in LEGACY_KNOWN_ROLES)
    legacy_unnamed = sum(
        1 for e in elements
        if str(e.get("role", "")) in LEGACY_NAMED_ROLES
        and not str(e.get("name") or "").strip()
    )

    real_extents = [
        e for e in extents
        if isinstance(e.get("extents"), list) and len(e["extents"]) == 4
    ]
    extent_by_name = {
        e.get("name", ""): e.get("extents")
        for e in extents
    }
    named_menus = sorted(
        name for name in extent_by_name if name.endswith(" menu"))
    menus_with_extents = sorted(
        name for name in named_menus if isinstance(extent_by_name[name], list))
    dock_present = [name for name in DOCK_TILES if name in extent_by_name]
    dock_with_extents = [
        name for name in dock_present
        if isinstance(extent_by_name[name], list)
    ]

    keyboard = {}
    for step in ("altf", "escape"):
        path = extra / f"{size}_{step}_diff.json"
        data = load_json(path)
        keyboard[step] = {
            "changed_pixels": data.get("changed_pixels"),
            "bbox": data.get("bbox"),
            "sha256": sha256(path),
        }

    return {
        "size": size,
        "evidence_sha256": {
            "a11y_summary.json": sha256(summary_path),
            "a11y_extents.jsonl": sha256(extents_path),
            "keyboard_diff.json": sha256(
                per_size / "keyboard_diff.json"),
        },
        "atspi_available": bool(summary.get("atspi_available")),
        "elements": len(elements),
        "named": named,
        "unnamed": len(unnamed),
        "unnamed_details": unnamed,
        "roles": dict(sorted(roles.items())),
        "description_fields": described,
        "extent_records": len(extents),
        "extents_with_geometry": len(real_extents),
        "extents_null": len(extents) - len(real_extents),
        "named_menus": named_menus,
        "menus_with_extents": menus_with_extents,
        "dock_tiles_named": dock_present,
        "dock_tiles_with_extents": dock_with_extents,
        "keyboard": keyboard,
        "legacy_gate_defect": {
            "invalid_role_elements_before_fix": legacy_invalid,
            "invalid_role_names_before_fix": legacy_invalid_roles,
            "unnamed_named_role_elements_before_fix": legacy_unnamed,
        },
    }


def screen_reader_scan(evidence: Path) -> dict:
    hits = []
    scanned = 0
    for folder in ("native_classic_functional_evidence2",
                   "native_classic_functional_evidence3"):
        base = evidence / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            if path.suffix.lower() not in {".json", ".jsonl", ".log", ".txt", ".md"}:
                continue
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = SCREEN_READER_RE.search(text)
            if match:
                hits.append({
                    "path": str(path.relative_to(evidence)),
                    "term": match.group(0),
                })
    return {
        "status": "NOT_RUN",
        "text_files_scanned": scanned,
        "announcement_evidence_hits": hits[:20],
        "note": (
            "A text hit is not an announcement. No Orca process, speech log or "
            "AT-SPI event recording exists in these artifacts; screen-reader "
            "behaviour was never executed."
        ),
    }


def vm_probe(evidence: Path) -> dict:
    running = []
    probe_error = None
    if VBOXMANAGE.exists():
        try:
            result = subprocess.run(
                [str(VBOXMANAGE), "list", "runningvms"],
                capture_output=True, text=True, timeout=20,
            )
            running = [
                line.split('"')[1] for line in result.stdout.splitlines()
                if line.startswith('"')
            ]
        except (OSError, subprocess.SubprocessError) as exc:
            probe_error = repr(exc)
    else:
        probe_error = "VBoxManage.exe not present at probed path"

    artifacts = []
    for name in PERF_ARTIFACTS:
        path = evidence / name
        if path.exists():
            artifacts.append({
                "path": str(path),
                "mtime_utc": iso_mtime(path),
            })
    blocked = VM_NAME in running and bool(artifacts)
    return {
        "vm_running": running,
        "probe_error": probe_error,
        "performance_agent_artifacts": artifacts,
        "status": "BLOCKED_BY_PERFORMANCE_AGENT" if blocked else "NOT_BLOCKED",
        "decision": (
            "No guest login, AT-SPI query, key injection or screen-reader start "
            "performed; VM use is serialized behind the performance agent."
        ),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    evidence = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else (
        ROOT / "scratch" / "native_a11y" / "native_a11y_verification.json")

    sys.path.insert(0, str(ROOT))
    from canopy_features.accessibility import screen_reader_metadata as srm

    sizes = {size: size_report(evidence, size) for size in SIZES}
    native_records = []
    for report in sizes.values():
        summary_path = (evidence / "native_classic_functional_evidence2"
                        / "per_size" / report["size"] / "a11y_summary.json")
        native_records.extend(
            {"objectName": f"native-{i}", "role": e.get("role", ""),
             "name": e.get("name", "")}
            for i, e in enumerate(load_json(summary_path).get("elements", []))
        )
    issues = srm.validate_metadata(native_records)
    issue_codes = collections.Counter(issue.code for issue in issues)

    report = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "STATIC/CI-SCOPED; evidence bytes recomputed on host, no VM use",
        "evidence_root": str(evidence),
        "base_commit": "ec910d7a",
        "sizes": sizes,
        "native_metadata_gate": {
            "records_checked": len(native_records),
            "issue_codes": dict(sorted(issue_codes.items())),
            "known_native_roles": sorted(srm.NATIVE_ATSPI_ROLES),
            "status": (
                "PASS_SCOPED" if issue_codes.get(srm.INVALID_ROLE, 0) == 0
                else "FAIL"
            ),
        },
        "screen_reader": screen_reader_scan(evidence),
        "vm": vm_probe(evidence),
        "focus_order_tab_shift_tab": {
            "status": "NOT_RUN",
            "note": (
                "Existing native evidence records X11 active-window state and "
                "Alt+F/Escape pixel diffs only; no Tab/Shift+Tab traversal or "
                "AT-SPI state_focused capture exists."
            ),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "scope": report["scope"],
        "vm": report["vm"]["status"],
        "gate": report["native_metadata_gate"]["status"],
        "screen_reader": report["screen_reader"]["status"],
        "sizes": {
            size: {
                "named": data["named"],
                "total": data["elements"],
                "unnamed": data["unnamed"],
                "dock": len(data["dock_tiles_with_extents"]),
            }
            for size, data in sizes.items()
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
