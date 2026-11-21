"""Approved roadmap source and automatic wave selection.

The catalog is a small JSON file in the state root. One bounded task per
priority keeps at most ``max_workers`` tasks in flight. Selection is
deterministic: existing task ids and overlapping scopes are never repeated.
"""
from __future__ import annotations

from pathlib import Path
import json

from . import policy

# Follow-up tasks derived from the three approved Canopy priorities. They only
# write bounded documentation/evidence files; no artwork or Qt design changes.
DEFAULT_ROADMAP = [
    {
        "id": "qt-build-blockers-followup",
        "title": "Consolidate Qt and Mint blocker evidence",
        "objective": "Run read-only checks for Qt sources, build tools and Mint VM support on this host. Record exact commands and outputs with PASS/BLOCKED/NOT RUN. Do not fabricate compiled Qt runs or screenshots. Write only docs/QT_BUILD_BLOCKERS_FOLLOWUP.md.",
        "scope": ["docs/QT_BUILD_BLOCKERS_FOLLOWUP.md"],
    },
    {
        "id": "visual-evidence-gaps-followup",
        "title": "Record compiled-Qt visual evidence gaps",
        "objective": "Audit available screenshot validation tooling and report which checks are synthetic versus real compiled-Qt captures. State that owner visual signoff and real screenshots are absent on main. Do not change approved artwork or dock design. Write only docs/VISUAL_EVIDENCE_GAPS_FOLLOWUP.md.",
        "scope": ["docs/VISUAL_EVIDENCE_GAPS_FOLLOWUP.md"],
    },
    {
        "id": "performance-security-followup",
        "title": "Record performance and security gate gaps",
        "objective": "Read docs/QUALITY.md and docs/RELIABILITY_99_GATE_AUDIT.md. Run available offline gate tests with exact commands and output. Report five-minute CPU/PSS as NOT RUN and invent no figures. Write only docs/PERFORMANCE_SECURITY_FOLLOWUP.md.",
        "scope": ["docs/PERFORMANCE_SECURITY_FOLLOWUP.md"],
    },
    {
        "id": "ci-queue-audit",
        "title": "Audit CI and review queue ownership",
        "objective": "Inspect the existing read-only CI supervisor and workflow without editing them. Run its regression tests and record real output. Document that green CI is not merge authorization and that no workflow was duplicated. Write only docs/CI_QUEUE_AUDIT.md.",
        "scope": ["docs/CI_QUEUE_AUDIT.md"],
    },
    {
        "id": "recovery-evidence-followup",
        "title": "Document supervisor recovery evidence",
        "objective": "Read the supervisor verification document and record the exact launch, failure-recovery and draft-PR evidence with links. Do not claim release, visual or Mint approval. Write only docs/RECOVERY_EVIDENCE_FOLLOWUP.md.",
        "scope": ["docs/RECOVERY_EVIDENCE_FOLLOWUP.md"],
    },
    {
        "id": "roadmap-handoff-summary",
        "title": "Summarize autonomous wave handoff",
        "objective": "Summarize which bounded follow-up tasks completed, which remain BLOCKED and what human approvals are still required before any merge. No visual signoff or merge claim. Write only docs/ROADMAP_HANDOFF_SUMMARY.md.",
        "scope": ["docs/ROADMAP_HANDOFF_SUMMARY.md"],
    },
]

TERMINAL = ("awaiting_review", "done", "blocked", "failed", "cancelled")
SUCCESS = ("awaiting_review", "done")


class RoadmapError(ValueError):
    """Roadmap catalog is invalid."""


def load(state_root: Path) -> list[dict]:
    """Load and validate the roadmap file, falling back to the built-in list."""
    path = Path(state_root) / "roadmap.json"
    if not path.exists():
        return [dict(item) for item in DEFAULT_ROADMAP]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise RoadmapError("corrupt roadmap.json") from exc
    if not isinstance(data, list) or len(data) > 64:
        raise RoadmapError("roadmap.json must be a list of at most 64 tasks")
    return [dict(policy.validate_task(item)) for item in data]


def next_tasks(existing: list[dict], roadmap: list[dict], max_workers: int,
               protected=None) -> list[dict]:
    """Return validated tasks needed to refill the worker pipeline."""
    if not isinstance(max_workers, int) or max_workers < 1:
        raise RoadmapError("invalid worker limit")
    in_flight = [task for task in existing if task.get("status") not in TERMINAL]
    ids = {task.get("id") for task in existing}
    scopes = [task.get("scope", []) for task in in_flight]
    state_by_id = {task.get("id"): task.get("status") for task in existing}
    chosen = []
    for item in roadmap:
        if len(in_flight) + len(chosen) >= max_workers:
            break
        definition = policy.validate_task(item, protected)
        if definition["id"] in ids:
            continue
        if any(dep not in state_by_id or state_by_id[dep] not in SUCCESS
               for dep in definition["depends_on"]):
            continue
        if any(policy.scope_conflict(definition["scope"], scope) for scope in scopes):
            continue
        chosen.append(definition)
        scopes.append(definition["scope"])
    return chosen
