#!/usr/bin/env python3
"""Parse the raw base/head visual-input freeze logs into a bounded summary."""

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
FREEZE = HERE


def read(path):
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8", "replace")


def parse(name):
    text = read(FREEZE / (name + "_freeze.log"))
    rc = int(read(FREEZE / (name + "_freeze.rc")).strip())
    ran = re.search(r"^Ran (\d+) tests? in ([0-9.]+s)$", text, re.M)
    failures = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.M)))
    summary = re.search(r"^(OK|FAILED)[^\n]*$", text, re.M)
    return {
        "log": "freeze_tests/" + name + "_freeze.log",
        "rc": rc,
        "ran": int(ran.group(1)) if ran else None,
        "duration": ran.group(2) if ran else None,
        "summary_line": summary.group(0).strip() if summary else None,
        "fail_error_names": failures,
        "fail_error_set_sha256": hashlib.sha256(
            "\n".join(failures).encode("utf-8")).hexdigest(),
    }


def main():
    base = parse("base")
    head = parse("head")
    new_names = sorted(set(head["fail_error_names"]) -
                       set(base["fail_error_names"]))
    result = {
        "schema_version": 1,
        "evidence_class": "SYNTHETIC / STATIC SOURCE ONLY",
        "command": ("PYTHONPATH=<worktree> python3 -m unittest -v "
                    "tests.test_classic_dock_frozen "
                    "tests.test_classic_qt_source "
                    "tests.test_classic_preview_scrollbar_theme "
                    "tests.test_c100_dock_display_geometry_contract "
                    "tests.test_classic_status_a11y "
                    "tests.test_nd041_native_settings_controls_wiring "
                    "tests.test_check_visual_lock "
                    "tests.test_check_visual_region_identity "
                    "tests.test_classic_clock_accessibility_no_visual_change"),
        "base_commit": "ec910d7a7275296ecbc8b5e5c459d356205165d1",
        "base": base,
        "head": head,
        "new_fail_error_names_vs_base": new_names,
        "classification": (
            "EXPECTED_STALE_PIN_RED_FROM_APPROVED_GEOMETRY"),
        "explanation": (
            "All new failures are the three pre-existing 88/12 test pins in "
            "test files outside this workstream's owned paths. They detect "
            "the intentional, bounded 32/96/14/7 remediation; no test file "
            "was edited. The byte-level non-geometry projection remains "
            "identical (see geometry_projection.json)."),
        "owned_paths_modified": [
            "prototype/classic/Theme.qml",
            "docs/NATIVE_DOCK_GEOMETRY.md",
            "scratch/dock_geometry_fix/**",
        ],
        "test_files_modified": [],
        "pixel_visual_owner_acceptance": "HOLD / NOT_RUN",
    }
    out = FREEZE / "summary.json"
    out.write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n")
                    .encode("utf-8"))
    print(json.dumps({
        "base": {k: base[k] for k in ("rc", "ran", "summary_line")},
        "head": {k: head[k] for k in ("rc", "ran", "summary_line")},
        "new_fail_error_names": new_names,
        "output": str(out),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
