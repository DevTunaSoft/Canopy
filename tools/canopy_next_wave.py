#!/usr/bin/env python3
"""Idempotent, bounded next-wave launcher for real Canopy Classic Qt QA.

Run from the *separate* Canopy-Supervisor checkout, after updating it and
cleanly stopping the old runner. Does not install apps, alter approved artwork,
merge PRs, or edit existing task histories.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Works when called as "py -3 tools/canopy_next_wave.py" on Windows.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_supervisor import gitops, policy, state  # noqa: E402
from canopy_supervisor.cli import build_supervisor, load_config  # noqa: E402

QT_BASE = "feat/classic-qt-port-buildable-20261121"

# These paths are purposely distinct from PRs 151-155 and protected artwork.
# They run as stacked draft PRs against the *real* compiled Qt prototype.
TASKS = [
    {
        "id": "qt-mint-runtime-acceptance",
        "title": "Build safe Linux Mint guest runtime acceptance runner",
        "base": QT_BASE,
        "kind": "implementation",
        "scope": [
            "tools/qa/classic_mint_guest_runtime.py",
            "tests/test_classic_mint_guest_runtime.py",
        ],
        "artifacts": [
            "tools/qa/classic_mint_guest_runtime.py",
            "tests/test_classic_mint_guest_runtime.py",
        ],
        "tests_required": True,
        "objective": (
            "Work against existing compiled Canopy Classic Qt code in this branch. "
            "Implement a safe optional Linux Mint VM runtime acceptance runner and "
            "thorough unit tests. Locate and reuse the repository's existing "
            "Mint preflight and Qt self-test commands; do not duplicate their "
            "implementations. Default to read-only discovery and dry-run; do not "
            "install Linux, modify VM settings, alter images, read passwords, "
            "or declare Mint acceptance unless the guest actually ran the Qt "
            "binary with recorded command, exit status and authentic logs. "
            "Check timeouts, absent VBoxManage/SSH, invalid paths and errors. "
            "On unavailable guest report guest acceptance NOT RUN while honestly "
            "reporting passing unit tests. Do not edit Qt UI, docks, icons, "
            "wallpaper or protected files. Run py -3 -m unittest "
            "tests.test_classic_mint_guest_runtime -v; record exact outputs "
            "and both authored file SHA-256 values."
        ),
    },
    {
        "id": "qt-classic-preview-packaging",
        "title": "Build safe user-level Canopy Classic preview packaging",
        "base": QT_BASE,
        "kind": "implementation",
        "scope": [
            "tools/qa/classic_preview_package.py",
            "tests/test_classic_preview_package.py",
        ],
        "artifacts": [
            "tools/qa/classic_preview_package.py",
            "tests/test_classic_preview_package.py",
        ],
        "tests_required": True,
        "objective": (
            "Based on the actual Canopy Classic Qt spike, implement a strictly "
            "user-level, reversible Linux Mint preview packaging helper with "
            "unit tests. Respect existing CMake install and preview-registration "
            "mechanisms: check them first and add only missing safe functionality. "
            "Never claim the preview is a complete session/compositor or replace "
            "the user's desktop or login manager. Require an explicitly supplied "
            "compiled binary and approved exact artwork for a live preview, "
            "quote desktop Exec paths safely, prohibit arbitrary paths/traversal, "
            "and allow dry-run plus a reversible uninstall. No sudo, background "
            "services, generated substitute art, or changes to approved dock "
            "geometry. Run py -3 -m unittest tests.test_classic_preview_package "
            "-v; provide real passing unit test output, or report BLOCKED, "
            "and SHA-256 hashes of both authored files."
        ),
    },
    {
        "id": "qt-classic-runtime-smoke-matrix",
        "title": "Strengthen compiled Qt runtime interaction smoke matrix",
        "base": QT_BASE,
        "kind": "implementation",
        "scope": [
            "tools/qa/classic_runtime_matrix.py",
            "tests/test_classic_runtime_matrix.py",
        ],
        "artifacts": [
            "tools/qa/classic_runtime_matrix.py",
            "tests/test_classic_runtime_matrix.py",
        ],
        "tests_required": True,
        "objective": (
            "Improve Canopy Classic compiled-Qt regression evidence without "
            "editing any Qt source or approved artwork. Reuse tools/qt_smoke.py, "
            "tools/check_screenshot.py and the real CLI arguments implemented "
            "in prototype/classic/main.cpp; do not invent flags or recreate "
            "existing PNG provenance validators. Add a bounded smoke-matrix "
            "orchestrator with true process exit checks, approved artwork "
            "startup validation, QML error detection, and captures at 760x500, "
            "1200x750 and 1920x1080 only if the real binary is available. "
            "Never pass synthetic screenshots off as real captures. An absent "
            "compiler/binary is a separately reported NOT RUN prerequisite, "
            "not a fabricated runtime PASS. Unit-test command construction, "
            "timeout, failure paths and report format. Run py -3 -m unittest "
            "tests.test_classic_runtime_matrix -v; provide exact results "
            "and SHA-256 hashes of both authored files."
        ),
    },
]


def prepare_wave(root: Path) -> int:
    """Append only new, approved tasks. Never reset state or existing work."""
    store = state.TaskStore(root)
    config = load_config(root)
    with state.exclusive_lock(store.lock_path):
        if not store.paused:
            raise ValueError("supervisor must be paused before preparing a wave")
        data = store.load()
        active = [t["id"] for t in data["tasks"]
                  if t.get("status") in ("assigned", "running",
                                         "verifying", "publishing", "interrupted")]
        if active:
            raise ValueError("active work must finish first: " + ", ".join(active))
        repo = Path(config["repo"])
        # Only update remote refs; do not alter checkout or other worktrees.
        gitops.run(["git", "fetch", config["remote"]], cwd=repo, timeout=180)
        gitops.rev_parse(repo, config["remote"] + "/" + QT_BASE)
        path = store.root / "roadmap.json"
        if path.is_file():
            catalog = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(catalog, list):
                raise ValueError("roadmap.json must be an array")
        else:
            # The built-in catalog is already exhausted in the task ledger;
            # an optional roadmap.json need not exist. Start a new explicit
            # catalog containing *only* these next-wave jobs. Old task state,
            # evidence and draft PRs are preserved in tasks.json.
            catalog = []
        by_id = {row.get("id"): row for row in catalog if isinstance(row, dict)}
        if len(by_id) != len(catalog):
            raise ValueError("invalid or duplicate IDs in existing roadmap")
        known_ids = {t["id"] for t in data["tasks"]}
        additions = []
        for task in TASKS:
            safe = policy.validate_task(task, config["protected_paths"])
            if safe["id"] in by_id:
                if policy.validate_task(by_id[safe["id"]],
                                        config["protected_paths"]) != safe:
                    raise ValueError("existing roadmap task differs: " + safe["id"])
                continue
            if safe["id"] in known_ids:
                continue
            additions.append(safe)
        if len(catalog) + len(additions) > 64:
            raise ValueError("roadmap is at its configured limit")
        # Atomic replacement, no task state rewrites and no worktree deletion.
        if additions:
            state.atomic_write(path, json.dumps(catalog + additions, indent=2) + "\n")
            for task in additions:
                store.event(task["id"], "new_approved_qa_wave",
                            "stacked against " + QT_BASE)
        return len(additions)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--start", action="store_true",
                        help="resume and run until this bounded roadmap becomes idle")
    args = parser.parse_args(argv)
    try:
        count = prepare_wave(args.state_root)
        print(f"QT_WAVE_READY added={count} (existing work retained)", flush=True)
        if args.start:
            store = state.TaskStore(args.state_root)
            config = load_config(args.state_root)
            with state.exclusive_lock(store.lock_path):
                store.set_paused(False)
                store.event("-", "qt_wave_started", "bounded stacked Qt QA wave")
            supervisor = build_supervisor(config, store)
            data = supervisor.run(until_idle=True)
            counts: dict[str, int] = {}
            for task in data["tasks"]:
                if task["id"] in {row["id"] for row in TASKS}:
                    counts[task["status"]] = counts.get(task["status"], 0) + 1
            print("QT_WAVE_FINISHED " + json.dumps(counts, sort_keys=True), flush=True)
            print(f"Dashboard: {store.dashboard_path}", flush=True)
            if counts.get("failed", 0) or counts.get("blocked", 0):
                return 1
        return 0
    except (ValueError, OSError, gitops.GitError,
            policy.PolicyError, state.LockBusy) as exc:
        print("QT_WAVE_BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
