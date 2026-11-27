#!/usr/bin/env python3
"""Structural validator for the scratch-only Canopy Classic Plasma 6 KPackage scaffold.

Checks structure only. It does NOT compile, install, run, render, screenshot,
measure resources or accept a desktop. Pure Python standard library.

Usage: python validate_skeleton.py [--root DIR] [--report PATH]
Exit 0 = all structural checks PASS, 1 = at least one FAIL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXPECTED_SHA = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_BLOB = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_QML_TOKENS = (
    "ApplicationWindow",
    "QQmlApplicationEngine",
    "QGuiApplication",
    "QProcess",
    "Process {",
    "Qt.createWindow",
    "canopy-classic-spike",
)
FORBIDDEN_METADATA_KEYS = ("X-Plasma-MainScript", "X-Plasma-API", "ServiceTypes")
FORBIDDEN_ASSET_SUFFIXES = {
    ".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp",
    ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".elf", ".appimage",
}
REQUIRED_FILES = (
    "metadata.json",
    "contents/ui/main.qml",
    "DESIGN.md",
    "ASSET_BINDINGS.json",
)
REQUIRED_DESIGN_TOKENS = (
    "ContainmentItem", "PlasmoidItem", "TasksModel", "KWin", "KPackage",
    "org.freedesktop.Notifications", "KSycoca", "KRun", "A17", "A24",
    "one compositor", "COMPILE_NOT_RUN", "RUNTIME_NOT_RUN",
    "VISUAL_APPROVAL_NOT_RUN",
)
REQUIRED_ROLES = (
    "approved-wallpaper-default", "tux-launcher-mark", "approved-asset-manifest",
    "dock-icon-browser", "dock-icon-mail", "dock-icon-files",
    "dock-icon-calendar", "dock-icon-photos", "dock-icon-music",
    "dock-icon-terminal", "dock-icon-settings",
)
LEGACY_ASSET_TOKENS = ("canopy-wave-preview.png", "blue-current.svg")


def qml_without_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--report", default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    checks: list[dict[str, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    # 1. Required files.
    missing = [p for p in REQUIRED_FILES if not (root / p).is_file()]
    check("required_files_present", not missing,
          "all present" if not missing else "missing: " + ", ".join(missing))

    # 2-5. metadata.json.
    metadata = None
    mpath = root / "metadata.json"
    if mpath.is_file():
        try:
            metadata = json.loads(mpath.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            check("metadata_json_valid", False, f"unreadable JSON: {exc}")
    check("metadata_json_valid", isinstance(metadata, dict),
          "parsed object" if isinstance(metadata, dict) else "not a JSON object")
    md = metadata if isinstance(metadata, dict) else {}
    structure = md.get("KPackageStructure")
    check("kpackage_structure_present", structure == "Plasma/Applet",
          f"KPackageStructure={structure!r}")
    minver = md.get("X-Plasma-API-Minimum-Version")
    check("plasma_api_minimum_6_0", minver == "6.0",
          f"X-Plasma-API-Minimum-Version={minver!r}")
    bad_keys = [k for k in FORBIDDEN_METADATA_KEYS if k in md]
    check("no_legacy_metadata_keys", not bad_keys,
          "none" if not bad_keys else "present: " + ", ".join(bad_keys))

    # 6-10. QML structural rules.
    qml_dir = root / "contents" / "ui"
    qml_files = sorted(qml_dir.glob("*.qml")) if qml_dir.is_dir() else []
    check("contents_ui_qml_present", bool(qml_files),
          f"{len(qml_files)} QML files" if qml_files else "no contents/ui/*.qml")
    main_qml = qml_dir / "main.qml"
    root_type = None
    if main_qml.is_file():
        body = qml_without_comments(main_qml.read_text(encoding="utf-8"))
        body = re.sub(r"^\s*import\s+[^\n]*$", "", body, flags=re.M)
        found = re.search(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\{", body, flags=re.M)
        root_type = found.group(1) if found else None
    check("main_qml_root_is_containment_or_plasmoid",
          root_type in ("ContainmentItem", "PlasmoidItem"),
          f"main.qml root={root_type!r}")
    token_hits: list[str] = []
    versioned_imports: list[str] = []
    has_tasks_model = False
    synthetic_rows: list[str] = []
    for qml in qml_files:
        raw = qml.read_text(encoding="utf-8")
        for token in FORBIDDEN_QML_TOKENS:
            if token in raw:
                token_hits.append(f"{qml.name}:{token}")
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") and re.search(r"\s+\d+(?:\.\d+)*\s*$", stripped):
                versioned_imports.append(f"{qml.name}:{stripped}")
        code = qml_without_comments(raw)
        if "TaskManager.TasksModel" in code:
            has_tasks_model = True
        if "ListModel" in code:
            synthetic_rows.append(qml.name)
    check("no_second_shell_or_process_tokens", not token_hits,
          "none" if not token_hits else "hits: " + ", ".join(token_hits))
    check("qml_imports_unversioned", not versioned_imports,
          "all unversioned" if not versioned_imports else "versioned: " + ", ".join(versioned_imports))
    check("taskmanager_model_bound", has_tasks_model,
          "TaskManager.TasksModel referenced" if has_tasks_model else "no upstream task model")
    check("no_synthetic_task_rows", not synthetic_rows,
          "no ListModel" if not synthetic_rows else "ListModel in: " + ", ".join(synthetic_rows))

    # 11. No copied assets or compiled runtime in the scaffold.
    extra = [
        str(p.relative_to(root)) for p in root.rglob("*")
        if p.is_file() and (p.suffix.lower() in FORBIDDEN_ASSET_SUFFIXES
                            or "canopy-classic-spike" in p.name)
    ]
    check("no_asset_bytes_or_runtime_in_package", not extra,
          "none" if not extra else "forbidden: " + ", ".join(sorted(extra)))

    # 12-13. ASSET_BINDINGS.json hash-only contract.
    ab_path = root / "ASSET_BINDINGS.json"
    bindings_doc = None
    if ab_path.is_file():
        try:
            bindings_doc = json.loads(ab_path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            check("asset_bindings_valid", False, f"unreadable JSON: {exc}")
    ab = bindings_doc if isinstance(bindings_doc, dict) else {}
    bindings = ab.get("bindings") if isinstance(ab.get("bindings"), list) else []
    roles = [b.get("role") for b in bindings if isinstance(b, dict)]
    invalid: list[str] = []
    for b in bindings:
        if not isinstance(b, dict):
            invalid.append("non-object binding")
            continue
        if not EXPECTED_SHA.fullmatch(str(b.get("sha256", ""))):
            invalid.append(f"{b.get('role')}:bad-sha256")
        if not EXPECTED_BLOB.fullmatch(str(b.get("git_blob", ""))):
            invalid.append(f"{b.get('role')}:bad-git-blob")
        if b.get("local_copy") is not None:
            invalid.append(f"{b.get('role')}:local_copy-not-null")
        if any(k != "local_copy" and "copy" in k for k in b):
            invalid.append(f"{b.get('role')}:copy-key")
    roles_ok = all(role in roles for role in REQUIRED_ROLES)
    binding_ok = (ab.get("schema") == "canopy.asset_bindings/1"
                  and ab.get("mode") == "HASH_ONLY_REFERENCES"
                  and len(bindings) == len(REQUIRED_ROLES) and roles_ok and not invalid)
    check("asset_bindings_valid", binding_ok,
          f"mode={ab.get('mode')!r}, bindings={len(bindings)}, invalid={invalid or 'none'}")
    binding_text = json.dumps(bindings, sort_keys=True)
    legacy_hits = [t for t in LEGACY_ASSET_TOKENS if t in binding_text]
    denylist = ab.get("denylist") if isinstance(ab.get("denylist"), list) else []
    deny_names = {d.get("name") for d in denylist if isinstance(d, dict)}
    deny_ok = all(t in deny_names for t in LEGACY_ASSET_TOKENS)
    check("legacy_assets_denylisted", not legacy_hits and deny_ok,
          f"bindings_hits={legacy_hits or 'none'}, denylist={sorted(n for n in deny_names if n)}")

    # 14-15. DESIGN.md mapping and explicit scope labels.
    design_path = root / "DESIGN.md"
    design_text = design_path.read_text(encoding="utf-8") if design_path.is_file() else ""
    absent = [t for t in REQUIRED_DESIGN_TOKENS if t not in design_text]
    check("design_maps_upstream_apis", not absent,
          "all upstream/API tokens present" if not absent else "absent: " + ", ".join(absent))
    labels = ("DESIGN_AND_STRUCTURE_ONLY", "NO_COMPILE", "NO_RUNTIME",
              "AWAITING_OWNER_FINAL_VISUAL_ACCEPTANCE")
    missing_labels = [t for t in labels if t not in design_text]
    check("scope_labels_present", not missing_labels,
          "all scope labels present" if not missing_labels else "absent: " + ", ".join(missing_labels))

    passed = sum(1 for c in checks if c["status"] == "PASS")
    failed = len(checks) - passed
    report = {
        "artifact": "canopy-classic-native-plasma6-kpackage-scaffold",
        "root": str(root),
        "scope": "STRUCTURAL_ONLY;NO_COMPILE;NO_RUNTIME;NO_VISUAL_APPROVAL;NO_REPO_MUTATION",
        "checks": checks,
        "passed": passed,
        "failed": failed,
        "verdict": "PASS" if failed == 0 else "FAIL",
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        Path(args.report).write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
