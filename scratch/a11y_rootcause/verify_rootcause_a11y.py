#!/usr/bin/env python3
"""STATIC/SYNTHETIC gate for the M3/M5 out-of-ownership a11y fix.

Reads only checked-in QML bytes and git blobs at the exact base commit.
No Qt compile, VM, AT-SPI query, guest login or screen reader is used.
Exit 0 = all checks PASS; exit 1 = at least one FAIL.
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLASSIC = ROOT / "prototype" / "classic"
BASE = "ec910d7a7275296ecbc8b5e5c459d356205165d1"
BRANCH = "product/a11y-rootcause-20261128"
OWNED_QML = (
    "prototype/classic/PreviewWindow.qml",
    "prototype/classic/Main.qml",
)
ALLOWED = OWNED_QML + (
    "docs/NATIVE_A11Y_ROOTCAUSE_FIX.md",
    "scratch/a11y_rootcause/",
)

results: list[dict] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append({"name": name, "status": "PASS" if ok else "FAIL",
                    "detail": detail})


def norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(ROOT), check=True,
                          capture_output=True, text=True).stdout


def blob(rel: str) -> str:
    return norm(git("show", BASE + ":" + rel))


def current(rel: str) -> str:
    return norm((ROOT / rel).read_text(encoding="utf-8"))


def changed_paths() -> list[str]:
    tracked = git("diff", "--name-only", BASE, "--").split()
    untracked = git("ls-files", "--others", "--exclude-standard").split()
    return sorted(set(tracked) | set(untracked))


def added_lines(rel: str) -> list[str]:
    diff = norm(git("diff", "--unified=0", BASE, "--", rel))
    return [l[1:] for l in diff.splitlines()
            if l.startswith("+") and not l.startswith("+++")]


def projection(text: str, drop_comments: bool = False) -> str:
    """Same projection as tests/test_classic_status_a11y.py, optionally
    dropping full-line comments for the Main.qml visibility comparison."""
    keep: list[str] = []
    skipping = False
    for line in norm(text).split("\n"):
        if "// A11Y-ANNOUNCE-BEGIN" in line:
            skipping = True
            continue
        if "// A11Y-ANNOUNCE-END" in line:
            skipping = False
            continue
        if skipping or "Accessible." in line:
            continue
        if drop_comments and line.lstrip().startswith("//"):
            continue
        keep.append(line)
    return "\n".join(keep)


changed = changed_paths()
qml_changed = [p for p in changed if p in OWNED_QML]
check("owned_qml_files_changed",
      sorted(qml_changed) == sorted(OWNED_QML),
      "changed owned QML: " + (", ".join(qml_changed) or "none"))

outside = [p for p in changed if not any(
    p == a or p.startswith(a) for a in ALLOWED)]
check("changes_limited_to_owned_paths", not outside,
      "outside owned paths: " + (", ".join(outside) or "none"))

base_pw = blob(OWNED_QML[0])
new_pw = current(OWNED_QML[0])
base_main = blob(OWNED_QML[1])
new_main = current(OWNED_QML[1])

check("preview_window_rendered_input_byte_frozen",
      projection(base_pw) == projection(new_pw),
      "SHA-256 of non-accessibility projection: " + hashlib.sha256(
          projection(new_pw).encode("utf-8")).hexdigest())

size_label = [l.strip() for l in new_pw.splitlines()
              if 'text: isDir ? "" : size + " B"' in l]
check("preview_empty_secondary_label_ignored_for_folders",
      len(size_label) == 1 and "Accessible.ignored: isDir" in new_pw,
      "folder rows have no size; the empty label is excluded from AT")

pw_needles = (
    "Accessible.name: name",
    'Accessible.description: isDir ? "Folder name" : "File name"',
    'Accessible.name: isDir ? "" : size + " B"',
    'Accessible.description: "File size in bytes"',
)
check("preview_labels_have_names_and_descriptions",
      all(n in new_pw for n in pw_needles),
      "explicit name/description on both file-row labels")

old_visibility = (
    "visible: !root.compactLayout",
    '|| (modelData !== "Window" && modelData !== "Help")',
)
check("main_compact_window_help_hide_rule_removed",
      all(line not in new_main for line in old_visibility),
      "the 760x500 hide rule for Window/Help no longer exists")
check("main_all_six_menus_visible_at_every_width",
      sum(1 for l in new_main.splitlines()
          if l.startswith("                    ") and l.strip() == "visible: true") == 1
      and 'model: ["File", "Edit", "View", "Go", "Window", "Help"]' in new_main,
      "topMenuButton is visible at compact width; six approved menus unchanged")
check("main_menu_accessible_names_preserved",
      'Accessible.name: modelData + " menu"' in new_main
      and 'Accessible.description: "Open the " + modelData + " menu"' in new_main,
      "Window menu and Help menu keep their accessible name/description")

base_acc = collections.Counter(
    l.strip() for l in base_pw.splitlines() + base_main.splitlines()
    if "Accessible." in l)
new_acc = collections.Counter(
    l.strip() for l in new_pw.splitlines() + new_main.splitlines()
    if "Accessible." in l)
check("all_prior_accessibility_lines_preserved",
      all(new_acc[k] >= v for k, v in base_acc.items())
      and sum(new_acc.values()) >= sum(base_acc.values()) + 5,
      "base Accessible lines=%d, head Accessible lines=%d, none removed" % (
          sum(base_acc.values()), sum(new_acc.values())))

# Main.qml rendered bindings may differ only by the deliberate visibility fix.
base_proj_lines = projection(base_main, True).splitlines()
expected = []
i = 0
while i < len(base_proj_lines):
    if (i + 1 < len(base_proj_lines)
            and base_proj_lines[i].strip() == old_visibility[0]
            and base_proj_lines[i + 1].strip() == old_visibility[1]):
        expected.append("                    visible: true")
        i += 2
    else:
        expected.append(base_proj_lines[i])
        i += 1
check("main_rendered_bindings_unchanged_except_visibility",
      expected == projection(new_main, True).splitlines(),
      "all other Main.qml rendered bindings are byte-identical")

dock_start = "    Rectangle {\n        id: dock"
check("approved_dock_tail_byte_frozen",
      dock_start in base_main and dock_start in new_main
      and hashlib.sha256(base_main[base_main.index(dock_start):].encode()).hexdigest()
      == hashlib.sha256(new_main[new_main.index(dock_start):].encode()).hexdigest(),
      "dock/footer region including the final root brace is unchanged")

frozen = (
    "anchors.leftMargin: root.compactLayout ? 16 : 24",
    "anchors.rightMargin: root.compactLayout ? 16 : 24",
    "spacing: root.compactLayout ? 10 : 18",
    "height: canopyTheme.barHeight",
    "Layout.preferredHeight: 27",
    "padding: 6",
)
check("approved_top_bar_geometry_constants_unchanged",
      all(t in new_main and t in base_main for t in frozen),
      "approved margins, spacing, bar height, button height and padding intact")

added: list[str] = []
for rel in OWNED_QML:
    added.extend(added_lines(rel))
forbidden = ("width:", "height:", "anchors.", "Layout.", "font.", "color:",
             "opacity:", "z:", "Image {", "Timer {", "Animation {",
             "sequence:")
geometry_hits = [l.strip() for l in added
                 if l.strip().startswith(forbidden)]
check("no_geometry_art_or_shortcut_change_in_added_lines",
      not geometry_hits,
      "added lines contain only accessibility bindings, the visibility fix "
      "and explanatory comments")

check("no_new_shortcuts_or_menu_actions",
      new_main.count("Shortcut {") == base_main.count("Shortcut {")
      and new_main.count("onClicked: actionMenu.open()")
      == base_main.count("onClicked: actionMenu.open()"),
      "no accelerator/action change; no duplicate of PR #752 Alt+W/Alt+H")

theme_rel = "prototype/classic/Theme.qml"
check("theme_and_approved_art_untouched",
      blob(theme_rel) == current(theme_rel)
      and not any(p.startswith("prototype/classic/assets/") for p in changed),
      "Theme.qml bytes identical and prototype/classic/assets/** absent")

summary = {
    "schema_version": 1,
    "base_commit": BASE,
    "branch": BRANCH,
    "scope": "STATIC/SYNTHETIC source gate; no Qt compile, VM, AT-SPI or reader",
    "checks": results,
    "all_pass": all(r["status"] == "PASS" for r in results),
}
out = pathlib.Path(__file__).with_name("verify_rootcause_a11y.json")
out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
               encoding="utf-8")
print(json.dumps(summary, indent=2, ensure_ascii=False))
sys.exit(0 if summary["all_pass"] else 1)
