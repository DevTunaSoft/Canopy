"""Continuous roadmap source for the Canopy supervisor.

The backlog is the 100-task engineering catalog in tools/canopy_backlog_100.py.
It is implementation/test work, not a fixed number of documentation waves.
Campaign completion is judged from evidence; BLOCKED and NOT RUN never count
as successful completion.
"""
from __future__ import annotations

import json
from pathlib import Path
import time

from . import policy

TERMINAL = ("awaiting_review", "done", "blocked", "failed", "cancelled")
SUCCESS = ("awaiting_review", "done")
ACTIVE = ("queued", "assigned", "running", "verifying", "publishing", "interrupted")


class RoadmapError(ValueError):
    """Roadmap catalog is invalid."""


def _backlog():
    from tools import canopy_backlog_100

    return canopy_backlog_100.tasks()


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
    notes = str(evidence.get("notes", "")).upper()
    if "BLOCKED" in notes or "NOT RUN" in notes:
        return "blocked"
    return "success"


def load(state_root: Path) -> list[dict]:
    """Honor an explicit roadmap.json; otherwise return the 100-task backlog."""
    path = Path(state_root) / "roadmap.json"
    if not path.exists():
        return [dict(item) for item in _backlog()]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise RoadmapError("corrupt roadmap.json") from exc
    if not isinstance(data, list) or len(data) > 128:
        raise RoadmapError("roadmap.json must be a list of at most 128 tasks")
    return [dict(policy.validate_task(item)) for item in data]


def _campaign(task: dict) -> str:
    return str(task.get("campaign") or task.get("id"))


def _attempt_number(campaign: str, existing: list[dict], state_root: Path) -> int | None:
    """Return next attempt number, or None when campaign is finished or paused."""
    attempts = [task for task in existing if _campaign(task) == campaign]
    cap = 2
    if attempts and isinstance(attempts[0].get("max_attempts"), int):
        cap = attempts[0]["max_attempts"]
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
    """Refill the pipeline with the highest-priority eligible backlog tasks."""
    if not isinstance(max_workers, int) or max_workers < 1:
        raise RoadmapError("invalid worker limit")
    now = time.time() if now is None else now
    state_root = state_root or Path(".")
    in_flight = [task for task in existing if task.get("status") not in TERMINAL]
    scopes = [task.get("scope", []) for task in in_flight]
    chosen = []
    used_campaigns = set()
    for item in _backlog():
        if len(in_flight) + len(chosen) >= max_workers:
            break
        campaign = item.get("campaign", item["id"])
        if campaign in used_campaigns:
            continue
        number = _attempt_number(campaign, existing, state_root)
        if number is None:
            continue
        attempts = [task for task in existing if _campaign(task) == campaign]
        if attempts:
            wait = float(attempts[-1].get("next_attempt_at", 0))
            if now < wait:
                continue
        definition = dict(item)
        if number > 1:
            definition["id"] = f"{definition['id']}-attempt-{number}"
            definition["branch"] = f"feat/canopy-supervisor-{definition['id']}"
            definition["scope"] = [
                scope.replace("{n}", str(number)) for scope in definition["scope"]
            ]
        definition["campaign"] = campaign
        clean = policy.validate_task(definition, protected)
        if any(policy.scope_conflict(clean["scope"], scope) for scope in scopes):
            continue
        chosen.append(clean)
        used_campaigns.add(campaign)
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
        if definition["id"] in ids:
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
    """Use explicit roadmap.json when supplied, otherwise the 100-task backlog."""
    path = Path(state_root) / "roadmap.json"
    if path.exists():
        return next_tasks(existing, load(state_root), max_workers, protected)
    return generate(existing, max_workers, protected=protected, now=now,
                    state_root=state_root)
