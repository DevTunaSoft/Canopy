#!/usr/bin/env python3
"""Parity + scope gate for the compiled native display host bridge.

Reads only on-disk artifacts: the canonical vectors generated from the Python
contracts, the compiled self-test log, the compiled source and the git diff.
It never launches a desktop, never claims a Plasma runtime result and never
writes a pass into an artifact that did not actually occur.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

VECTORS = HERE / "canonical_vectors.json"
LOG = HERE / "compiled_self_test.log"
CPP = ROOT / "prototype/classic/main.cpp"

# The four upstream Qt screen signals from the original blocker's next-action
# list, plus the two DPI signals actually available in Qt 6.12.
REQUIRED_MARKERS = (
    "QGuiApplication::screenAdded",
    "QGuiApplication::screenRemoved",
    "QGuiApplication::primaryScreenChanged",
    "QScreen::geometryChanged",
    "QScreen::logicalDotsPerInchChanged",
    "CANOPY_NATIVE_DISPLAY_WIRED",
    "applyRecoverySnapshot",
    "applyLogicalDpiChange",
    "CANOPY_NATIVE_DISPLAY_RELAYOUT_APPLIED",
)
FORBIDDEN_IN_BRIDGE = (
    "QProcess", "QTcpSocket", "QLocalSocket", "QTimer", "startTimer(",
    "system(", "QDBusConnection", "QThread",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_log(text: str):
    rows = {}
    for line in text.splitlines():
        match = re.match(
            r"^CANOPY_NATIVE_DISPLAY_VECTOR\s+(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\S+)\s*$",
            line.strip())
        if match:
            rows[match.group(1)] = {
                "kind": match.group(2),
                "width": int(match.group(3)),
                "height": int(match.group(4)),
                "reason": match.group(5),
            }
    return rows, "CANOPY_NATIVE_DISPLAY_SELF_TEST_PASS" in text


def bridge_source(source: str) -> str:
    start = source.index("class NativeDisplayHostBridge final : public QObject")
    end = source.index("// Canonical vectors shared with the Python producer", start)
    return source[start:end]


def main() -> int:
    payload = json.loads(VECTORS.read_text(encoding="utf-8"))
    rows, marker = parse_log(LOG.read_text(encoding="utf-8", errors="replace"))
    source = CPP.read_text(encoding="utf-8")
    bridge = bridge_source(source)

    mismatches = []
    for case in payload["cases"]:
        expected = {key: case["expected"][key]
                    for key in ("kind", "width", "height", "reason")}
        actual = rows.get(case["id"])
        if actual != expected:
            mismatches.append({"id": case["id"], "expected": expected,
                               "actual": actual})
    missing_markers = [token for token in REQUIRED_MARKERS if token not in source]
    forbidden = [token for token in FORBIDDEN_IN_BRIDGE if token in bridge]
    scope_file = HERE / "git_diff_names.txt"
    changed = (scope_file.read_text(encoding="utf-8").splitlines()
               if scope_file.exists() else [])
    visual_assets = ("prototype/classic/assets/", "prototype/classic/Theme.qml",
                     "prototype/classic/Main.qml", "prototype/classic/DockTile.qml",
                     "prototype/classic/ShellMenuBar.qml",
                     "prototype/classic/QuickControlsOverlay.qml")
    visual_paths_changed = [name for name in changed
                            if any(marker in name for marker in visual_assets)]

    verdict = "PASS" if (not mismatches and marker and not missing_markers
                         and not forbidden and not visual_paths_changed) else "FAIL"
    report = {
        "artifact": "native_display_host_parity_gate",
        "classification": "SYNTHETIC",
        "vector_provenance": {
            "classification": "EMBEDDED_SYNTHETIC_GENERATED_FIXTURES",
            "compiled_location": ("prototype/classic/main.cpp :: "
                                  "kNativeDisplaySteps / kNativeDisplayCases"),
            "generator": "scratch/native_host_wiring/generate_vectors.py",
            "external_mirrors": (
                "scratch/native_host_wiring/canonical_vectors.json",
                "scratch/native_host_wiring/canonical_vectors_cpp.txt",
            ),
            "note": ("The compiled offscreen self-test uses vectors frozen in "
                     "the translation unit, not an external fixture file. "
                     "The mirrors are generated offline from the Python "
                     "contract; this gate compares the compiled log rows "
                     "with those canonical expectations. It is a synthetic "
                     "equivalence check, not a runtime observation."),
        },
        "verdict": verdict,
        "vector_count": len(payload["cases"]),
        "observed_vector_count": len(rows),
        "self_test_pass_marker": marker,
        "mismatches": mismatches,
        "missing_wiring_markers": missing_markers,
        "forbidden_bridge_tokens": forbidden,
        "visual_paths_changed": visual_paths_changed,
        "sha256": {
            "canonical_vectors.json": sha256(VECTORS),
            "compiled_self_test.log": sha256(LOG),
            "main.cpp": sha256(CPP),
        },
        "note": ("Compiled offscreen self-test and source inspection only. "
                 "NOT_RUN: real Plasma compositor, real monitor/DPI change, "
                 "screenshots, screen reader and owner visual acceptance."),
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (HERE / "parity_report.json").write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
