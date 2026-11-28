#!/usr/bin/env python3
"""STATIC / SYNTHETIC gate for the owned QML accessibility remediation.

No Qt compilation, VM, guest login, AT-SPI query or screen reader is used.
Every check reads checked-in bytes or the exact git diff of this worktree.
Exit 0 = all checks pass; exit 1 = at least one FAIL.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLASSIC = ROOT / "prototype" / "classic"
OWNED = (
    "prototype/classic/ShellMenuBar.qml",
    "prototype/classic/ShellMenuPopupSet.qml",
    "prototype/classic/QuickControlsOverlay.qml",
    "prototype/classic/SettingsPanel.qml",
)
# Theme.qml is only required to be untouched; do NOT claim a byte-frozen
# "32/96/14/7 geometry line" — at this base the pinned visual constants are
# barHeight: 32, dockSize: 88, dockPadding: 12 and dockSpacing: 7, as asserted
# by tests/test_classic_qt_source.py. The honest rendered-input proof here is
# the projection check below (all Accessible.* lines stripped).
BASE_THEME_SHA = hashlib.sha256(
    (CLASSIC / "Theme.qml").read_bytes()).hexdigest()

results: list[dict] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append({"name": name, "status": "PASS" if ok else "FAIL",
                    "detail": detail})


def read(name: str) -> str:
    return (CLASSIC / name).read_text(encoding="utf-8")


def git_diff(paths: tuple[str, ...] = ()) -> str:
    return subprocess.run(
        ["git", "diff", "--unified=0", "ec910d7a", "--", *paths],
        cwd=str(ROOT), capture_output=True, text=True, check=True).stdout


# Scope the added-line checks to the four owned QML files only. Counting the
# whole tree would count the script's own "Accessible." string literals and
# the docs/test pin-sync lines as product edits (the clean-checkout mismatch).
qml_diff = git_diff(OWNED)
changed = subprocess.run(
    ["git", "diff", "--name-only", "ec910d7a", "--"],
    cwd=str(ROOT), capture_output=True, text=True, check=True).stdout.split()
tracked_changed = [p for p in changed if p in OWNED]

check("owned_qml_files_changed",
      len(tracked_changed) == len(OWNED),
      "changed owned QML: " + ", ".join(sorted(tracked_changed)))

added = [l[1:] for l in qml_diff.splitlines()
         if l.startswith("+") and not l.startswith("+++")]
added_acc = [l for l in added if "Accessible." in l]
check("secondary_labels_named_or_described",
      len(added_acc) >= 12,
      "%d accessibility-only lines added (name/description)" % len(added_acc))

for fn, needles in (
    ("QuickControlsOverlay.qml", (
        "Accessible.name: text", "canopyQuickStatus",
        "Accessible.description: quickControls.titleFor(modelData) + \" host status\"",
    )),
    ("SettingsPanel.qml", (
        "canopySettingsTitle", "canopySettingsDisclosure",
        "Accessible.name: text",
    )),
    ("ShellMenuPopupSet.qml", (
        "component PremiumMenuItem: MenuItem {", "Accessible.name: text",
    )),
):
    src = read(fn)
    check(fn + "_secondary_label_names",
          all(n in src for n in needles),
          "all required name tokens present")

bar = read("ShellMenuBar.qml")
check("compact_window_help_reachability",
      'sequence: "Alt+W"' in bar and 'sequence: "Alt+H"' in bar
      and "onActivated: windowMenu.open()" in bar
      and "onActivated: helpMenu.open()" in bar
      and bar.count("Shortcut {") == 2,
      "SOURCE/COMPILED-LOAD ONLY: Alt+W and Alt+H bind to the two existing "
      "menu proxies; no native keyboard-activation run is claimed")
check("shortcuts_do_not_collide_with_classic_bindings",
      not re.search(r'sequence: "(Ctrl\\+W|Ctrl\\+Space|Ctrl\\+Shift\\+F|Ctrl\\+Alt\\+N)"', bar),
      "no reuse of the four registered Classic shortcuts")

forbidden = ("width:", "height:", "anchors.", "Layout.", "font.", "color:",
             "opacity:", "visible:", "z:", "Image {", "Timer {", "Animation {")
geometry_hits = [l.strip() for l in added
                 if any(l.strip().startswith(t) for t in forbidden)]
check("no_geometry_or_art_change_in_added_lines",
      not geometry_hits,
      "added lines contain no geometry/visual binding")

# The only tests/** path permitted here is the mechanical ND-041 pin sync
# for the Accessible-only lines added below `visible: opened`.
ALLOWED_NON_QML = (
    "docs/NATIVE_A11Y_QML_FIX.md",
    "scratch/native_a11y_qml/",
    "tests/test_nd041_native_settings_controls_wiring.py",
)
outside = [p for p in changed if p not in OWNED
           and p + "/" not in OWNED]
check("changes_limited_to_owned_paths",
      all(p.startswith(ALLOWED_NON_QML) for p in outside),
      "non-QML changed paths: " + (", ".join(sorted(outside)) or "none"))
check("theme_and_approved_art_untouched",
      not any(p.startswith(("prototype/classic/Theme.qml",
                           "prototype/classic/assets/")) for p in changed)
      and hashlib.sha256((CLASSIC / "Theme.qml").read_bytes()).hexdigest() == BASE_THEME_SHA,
      "Theme.qml and prototype/classic/assets/** not in diff")

# Byte-level rendered-input projection (same definition as the status gate):
# strip accessibility-only lines and confirm rendered inputs are unchanged.
def projection(path: str) -> str:
    keep = []
    skipping = False
    for line in read(path).replace("\r\n", "\n").split("\n"):
        if "// A11Y-ANNOUNCE-BEGIN" in line:
            skipping = True
            continue
        if "// A11Y-ANNOUNCE-END" in line:
            skipping = False
            continue
        if skipping or "Accessible." in line:
            continue
        keep.append(line)
    return "\n".join(keep)

import subprocess as _sp
base_projection = {}
for fn in ("QuickControlsOverlay.qml", "SettingsPanel.qml"):
    blob = _sp.run(["git", "show", "ec910d7a:prototype/classic/" + fn],
                   cwd=str(ROOT), capture_output=True, text=True,
                   check=True).stdout.replace("\r\n", "\n")
    skipping = False
    keep = []
    for line in blob.split("\n"):
        if "// A11Y-ANNOUNCE-BEGIN" in line:
            skipping = True
            continue
        if "// A11Y-ANNOUNCE-END" in line:
            skipping = False
            continue
        if skipping or "Accessible." in line:
            continue
        keep.append(line)
    base_projection[fn] = "\n".join(keep)

check("rendered_inputs_byte_frozen",
      all(projection(fn) == base_projection[fn] for fn in base_projection),
      "rendered halves of both panels are byte-identical after stripping "
      "Accessibility-only lines")

summary = {
    "schema_version": 1,
    "base_commit": "ec910d7a7275296ecbc8b5e5c459d356205165d1",
    "branch": "product/native-a11y-qml-20261128",
    "scope": "STATIC/SYNTHETIC source-gate; no Qt compile, VM, AT-SPI or reader",
    "checks": results,
    "all_pass": all(r["status"] == "PASS" for r in results),
}
print(json.dumps(summary, indent=2, ensure_ascii=False))
sys.exit(0 if summary["all_pass"] else 1)
