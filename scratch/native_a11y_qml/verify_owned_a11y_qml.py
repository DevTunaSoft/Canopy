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
# Frozen visual constants from the owner-approved 32/96/14/7 geometry line.
# This base (ec910d7a) still carries the then-current dock mirror; the gate
# only requires that neither Theme.qml nor any artwork byte was touched.
BASE_THEME_SHA = hashlib.sha256(
    (CLASSIC / "Theme.qml").read_bytes()).hexdigest()

results: list[dict] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append({"name": name, "status": "PASS" if ok else "FAIL",
                    "detail": detail})


def read(name: str) -> str:
    return (CLASSIC / name).read_text(encoding="utf-8")


def git_diff() -> str:
    return subprocess.run(
        ["git", "diff", "--unified=0", "ec910d7a", "--"],
        cwd=str(ROOT), capture_output=True, text=True, check=True).stdout


diff = git_diff()
changed = subprocess.run(
    ["git", "diff", "--name-only", "ec910d7a", "--"],
    cwd=str(ROOT), capture_output=True, text=True, check=True).stdout.split()
tracked_changed = [p for p in changed if p in OWNED]

check("owned_qml_files_changed",
      len(tracked_changed) == len(OWNED),
      "changed owned QML: " + ", ".join(sorted(tracked_changed)))

added = [l[1:] for l in diff.splitlines()
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
      "Alt+W and Alt+H reach the two existing menu proxies at compact width")
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

outside = [p for p in changed if p not in OWNED
           and p + "/" not in OWNED]
check("changes_limited_to_owned_paths",
      all(p.startswith(("docs/NATIVE_A11Y_QML_FIX.md", "scratch/native_a11y_qml/"))
          for p in outside),
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
