"""Continuous roadmap source with bounded, prioritized campaigns.

The supervisor never runs a fixed number of waves. It refills the worker
pipeline from this ordered campaign list. Real build/runtime/acceptance work
ranks above documentation. Every campaign has a hard attempt cap and a
retry backoff, so a failing task cannot loop forever or spawn duplicate PRs.
"""
from __future__ import annotations

from pathlib import Path
import json
import time

from . import policy

# Ordered by user-approved priority. No campaign modifies approved artwork,
# dock geometry, wallpaper, Qt GUI source or CI workflows.
CAMPAIGNS = [
    {
        "id": "qt-toolchain-enablement",
        "kind": "build",
        "title": "Enable Qt build toolchain",
        "objective": "Try to make a Qt build possible on this host. Run read-only probes first: Get-Command cmake,ninja,qmake,g++,cl; wsl.exe --list --quiet; winget search Qt if winget exists. If a supported package manager is available AND a Qt prototype source is present in the worktree, install only the missing build packages into the existing environment and record the exact commands and exit codes. Never change approved artwork, dock design or CI. If no source or no safe installer exists, report BLOCKED with the exact command output. Write only docs/qt_toolchain_attempt_{n}.md. Do not fabricate a build or screenshot.",
        "scope": ["docs/qt_toolchain_attempt_{n}.md"],
        "max_attempts": 3,
    },
    {
        "id": "qt-source-build",
        "kind": "build",
        "title": "Attempt real Qt source compilation",
        "objective": "Attempt to compile the existing Canopy Qt prototype in a temporary directory, without changing approved design files. First verify a Qt toolchain from the previous campaign evidence. Locate prototype sources with git ls-tree on the existing feature branch references; do not load full git history. If sources and toolchain exist, configure and build into a temp directory, record exact commands, compiler output and exit code. If either is missing, report BLOCKED with command output. Write only docs/qt_source_build_attempt_{n}.md. Never claim a compiled binary without its build log.",
        "scope": ["docs/qt_source_build_attempt_{n}.md"],
        "max_attempts": 3,
    },
    {
        "id": "qt-runtime-screenshot",
        "kind": "verify",
        "title": "Capture genuine compiled-Qt runtime evidence",
        "objective": "If a compiled Qt binary was proven in the previous campaign, launch it with the existing self-test flags and capture real screenshots at 1200x750, 1920x1080 and 760x500. Record command, exit code, PNG paths and SHA-256 hashes. If no genuine compiled binary exists, report NOT RUN with the exact absence check; never use a synthetic PNG as a real screenshot. Do not modify approved icons, dock or wallpaper. Write only docs/qt_runtime_screenshot_attempt_{n}.md.",
        "scope": ["docs/qt_runtime_screenshot_attempt_{n}.md"],
        "max_attempts": 3,
    },
    {
        "id": "original-icon-verification",
        "kind": "verify",
        "title": "Verify original approved icon assets",
        "objective": "Locate the eight owner-approved icon masters or their SHA manifest in existing references. Run read-only hash verification with tools/audit_approved_icon_optics.py if assets are present. Never regenerate, replace or modify artwork. If masters are unavailable in this checkout, report BLOCKED with the exact lookup commands and output. Write only docs/icon_verification_attempt_{n}.md.",
        "scope": ["docs/icon_verification_attempt_{n}.md"],
        "max_attempts": 2,
    },
    {
        "id": "mint-guest-acceptance",
        "kind": "verify",
        "title": "Attempt Linux Mint guest acceptance",
        "objective": "Check for VirtualBox/VBoxManage, a prepared Mint VM and the existing guest preflight. If all exist, run only the documented read-only preflight and report exact output. Do not install a distribution, change the host desktop or fabricate guest results. If prerequisites are absent, report BLOCKED with commands and output. Write only docs/mint_acceptance_attempt_{n}.md.",
        "scope": ["docs/mint_acceptance_attempt_{n}.md"],
        "max_attempts": 2,
    },
    {
        "id": "security-performance-gate",
        "kind": "verify",
        "title": "Run offline security and resource gates",
        "objective": "Run the existing offline gate tests (reliability, performance evidence, shell pack validation) and record exact commands and output. Report five-minute CPU/PSS as NOT RUN because no real Mint guest measurement exists; invent no figures. Do not edit CI or approved designs. Write only docs/security_performance_attempt_{n}.md.",
        "scope": ["docs/security_performance_attempt_{n}.md"],
        "max_attempts": 2,
    },
    # Independent engineering work follows blocked/exhausted art and Mint
    # prerequisites. Each campaign has distinct owned paths and requires real
    # code/test evidence; do not create another blocker-only documentation PR.
    {
        "id": "shared-event-queue",
        "kind": "implementation",
        "title": "Implement bounded shared shell event queue",
        "objective": "Implement a small dependency-free, event-driven and versioned in-process shell event queue for trusted shell-core producers/consumers, with deterministic bounded storage and no timers, polling loops, network or workers. Define explicit overflow and invalid-event handling; write exhaustive unit tests including large input and overflow. Do not integrate into a live compositor or change existing Classic Qt or owner artwork. Work only in owned paths; test with py -3 -m unittest tests.test_event_queue -v and record output and SHA-256 of both authored files.",
        "scope": ["canopy_core/event_queue.py", "tests/test_event_queue.py"],
        "artifacts": ["canopy_core/event_queue.py", "tests/test_event_queue.py"],
        "max_attempts": 2,
    },
    {
        "id": "shell-host-fault-matrix",
        "kind": "implementation",
        "title": "Exercise trusted Shell Host failure and recovery paths",
        "objective": "Add meaningful fault-injection regression tests against the existing ShellHost trusted-adapter lifecycle: factory failures, preparation, activation, deactivation, disposal, rollback and repeated switching. Verify state and resource cleanup invariants without loading untrusted QML. Do not rewrite or modify shell_host.py; if tests find a genuine host defect, record the exact failing reproduction as BLOCKED and leave a separate fix recommendation rather than falsifying PASS. Work only in owned test file; run py -3 -m unittest tests.test_shell_host_fault_matrix -v and record exact output and SHA-256.",
        "scope": ["tests/test_shell_host_fault_matrix.py"],
        "artifacts": ["tests/test_shell_host_fault_matrix.py"],
        "max_attempts": 2,
    },
    {
        "id": "registry-negative-controls",
        "kind": "implementation",
        "title": "Expand Shell Pack registry security negative controls",
        "objective": "Write independent regression tests for the existing read-only Shell Pack registry: invalid catalog shapes, malformed manifests, path traversal, symlink escapes, duplicate IDs, path normalization and hostile metadata lengths where supported. Use temporary directories and local files; do not execute community pack code or modify registry implementation. Record real failures as BLOCKED with reproducible details. Work only in owned test file; run py -3 -m unittest tests.test_registry_negative_controls -v and record output and SHA-256.",
        "scope": ["tests/test_registry_negative_controls.py"],
        "artifacts": ["tests/test_registry_negative_controls.py"],
        "max_attempts": 2,
    },
    {
        "id": "screenshot-provenance-gate",
        "kind": "implementation",
        "title": "Validate screenshot evidence provenance metadata offline",
        "objective": "Implement a standard-library-only offline validator for a JSON screenshot evidence manifest describing exact PNG paths, expected dimensions, SHA-256 checksums, source commit, and Qt capture command. Fail closed on corrupt PNG, unsupported dimensions, path escapes, symlinks, duplicate entries and mismatched hashes; add negative regression tests. Explicitly state that metadata validation alone does NOT prove the screenshot came from compiled Qt or grant visual approval. Do not create/change any screenshot, wallpaper, icon, dock or GUI. Work only in owned files; run py -3 -m unittest tests.test_screenshot_provenance -v and record output and SHA-256.",
        "scope": ["tools/check_screenshot_provenance.py", "tests/test_screenshot_provenance.py"],
        "artifacts": ["tools/check_screenshot_provenance.py", "tests/test_screenshot_provenance.py"],
        "max_attempts": 2,
    },
]

TERMINAL = ("awaiting_review", "done", "blocked", "failed", "cancelled")
SUCCESS = ("awaiting_review", "done")
ACTIVE = ("queued", "assigned", "running", "verifying", "publishing", "interrupted")


class RoadmapError(ValueError):
    """Roadmap catalog is invalid."""


def campaign_status(task: dict, state_root: Path) -> str:
    """Judge a finished campaign from its evidence, never from its PR alone."""
    path = Path(state_root) / "evidence" / task["id"] / "evidence.json"
    if not path.is_file():
        return "pending"
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return "failed"
    results = {row.get("result") for row in evidence.get("tests", [])
               if isinstance(row, dict)}
    if "FAIL" in results:
        return "failed"
    if "BLOCKED" in results or "NOT RUN" in results:
        return "blocked"
    return "success"


def load(state_root: Path) -> list[dict]:
    """Honor an explicit roadmap.json; otherwise return the continuous list."""
    path = Path(state_root) / "roadmap.json"
    if not path.exists():
        return [dict(item) for item in CAMPAIGNS]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise RoadmapError("corrupt roadmap.json") from exc
    if not isinstance(data, list) or len(data) > 64:
        raise RoadmapError("roadmap.json must be a list of at most 64 tasks")
    return [dict(policy.validate_task(item)) for item in data]


def _attempt_number(campaign: str, existing: list[dict], state_root: Path) -> int | None:
    """Return next attempt number, or None when campaign is finished or paused."""
    attempts = [task for task in existing if task.get("campaign") == campaign]
    cap = next((item.get("max_attempts", 3) for item in CAMPAIGNS
                if item["id"] == campaign), 3)
    if len(attempts) >= cap:
        return None
    if any(task.get("status") in ACTIVE for task in attempts):
        return None
    outcomes = [campaign_status(task, state_root) for task in attempts]
    if "success" in outcomes or "blocked" in outcomes:
        return None
    return len(attempts) + 1


def generate(existing: list[dict], max_workers: int, *, protected=None,
             now: float | None = None, state_root: Path | None = None) -> list[dict]:
    """Refill the pipeline with the highest-priority eligible campaigns."""
    if not isinstance(max_workers, int) or max_workers < 1:
        raise RoadmapError("invalid worker limit")
    now = time.time() if now is None else now
    in_flight = [task for task in existing if task.get("status") not in TERMINAL]
    scopes = [task.get("scope", []) for task in in_flight]
    chosen = []
    used = set()
    for campaign in CAMPAIGNS:
        if len(in_flight) + len(chosen) >= max_workers:
            break
        campaign_id = campaign["id"]
        if campaign_id in used:
            continue
        number = _attempt_number(campaign_id, existing, state_root or Path("."))
        if number is None:
            continue
        attempts = [task for task in existing if task.get("campaign") == campaign_id]
        if attempts:
            wait = float(attempts[-1].get("next_attempt_at", 0))
            if now < wait:
                continue
        definition = dict(campaign)
        definition["id"] = f"{campaign_id}-attempt-{number}"
        definition["scope"] = [scope.replace("{n}", str(number))
                               for scope in campaign["scope"]]
        definition["branch"] = f"feat/canopy-supervisor-{definition['id']}"
        definition["campaign"] = campaign_id
        clean = policy.validate_task(definition, protected)
        if any(policy.scope_conflict(clean["scope"], scope) for scope in scopes):
            continue
        chosen.append(clean)
        used.add(campaign_id)
        scopes.append(clean["scope"])
    return chosen


def next_tasks(existing: list[dict], roadmap: list[dict], max_workers: int,
               protected=None) -> list[dict]:
    """Select from an explicit catalog (kept for custom roadmap.json files)."""
    if not isinstance(max_workers, int) or max_workers < 1:
        raise RoadmapError("invalid worker limit")
    in_flight = [task for task in existing if task.get("status") not in TERMINAL]
    ids = {task.get("id") for task in existing}
    scopes = [task.get("scope", []) for task in in_flight]
    by_id = {task.get("id"): task.get("status") for task in existing}
    chosen = []
    for item in roadmap:
        if len(in_flight) + len(chosen) >= max_workers:
            break
        definition = policy.validate_task(item, protected)
        if definition["id"] in ids or definition["scope"] in scopes:
            continue
        if any(dep not in by_id or by_id[dep] not in SUCCESS
               for dep in definition["depends_on"]):
            continue
        if any(policy.scope_conflict(definition["scope"], scope) for scope in scopes):
            continue
        chosen.append(definition)
        scopes.append(definition["scope"])
    return chosen


def select(existing: list[dict], max_workers: int, state_root: Path,
           *, protected=None, now: float | None = None) -> list[dict]:
    """Use explicit roadmap.json when supplied, else continuous campaigns."""
    path = Path(state_root) / "roadmap.json"
    if path.exists():
        return next_tasks(existing, load(state_root), max_workers, protected)
    return generate(existing, max_workers, protected=protected, now=now,
                    state_root=state_root)
