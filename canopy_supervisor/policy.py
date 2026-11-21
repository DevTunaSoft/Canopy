"""Static safety policy for Canopy supervisor tasks.

Protected paths cover owner-approved Classic artwork, the approved Qt GUI
implementation and the established CI workflow. A task may not edit them and
may not claim scope that overlaps another active worker's scope.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,48}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{7,40}$")
BRANCH = re.compile(r"^(feat|feature|fix|docs|qa|test)/[a-z0-9][a-z0-9._/-]{2,70}$")
RESULT = ("PASS", "FAIL", "BLOCKED", "NOT RUN")

# Paths whose visual/engineering approval is owned by the human owner.
# Update only with explicit owner approval, never from a worker task.
PROTECTED_PATHS = (
    "canopy/assets/*",
    "canopy/*wallpaper*",
    "canopy/*dock*",
    "canopy/classic_gtk.py",
    "canopy/classic_model.py",
    ".github/workflows/review-supervisor.yml",
    "AGENTS.md",
    "tools/review_supervisor.py",
)


class PolicyError(ValueError):
    """Task or evidence violates a safety rule."""


def norm(path: object) -> str:
    """Normalize a path for case-insensitive, separator-agnostic matching."""
    if not isinstance(path, str) or not path.strip():
        raise PolicyError("path must be a non-empty string")
    text = path.strip().replace("\\", "/").lower()
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("/") or re.match(r"^[a-z]:", text):
        raise PolicyError(f"absolute path not allowed: {path!r}")
    parts = text.split("/")
    if ".." in parts:
        raise PolicyError(f"parent traversal not allowed: {path!r}")
    return "/".join(part for part in parts if part not in ("", "."))


def covers(a: str, b: str) -> bool:
    """True when normalized pattern a covers path or pattern b."""
    a, b = norm(a), norm(b)
    if a == b:
        return True
    if a.endswith("/*"):
        root = a[:-2]
        return b == root or b.startswith(root + "/")
    if b.endswith("/*"):
        return covers(b, a)
    return fnmatch.fnmatchcase(b, a) or fnmatch.fnmatchcase(a, b)


def validate_scope(scope: object) -> list[str]:
    if not isinstance(scope, list) or not scope:
        raise PolicyError("scope must be a non-empty list of relative paths")
    result = []
    for item in scope:
        path = norm(item)
        if path not in result:
            result.append(path)
    return result


def protected_violations(scope: object, protected: object = None) -> list[str]:
    """List protected patterns touched by the proposed scope."""
    paths = validate_scope(scope)
    patterns = PROTECTED_PATHS if protected is None else protected
    if not isinstance(patterns, (list, tuple)):
        raise PolicyError("protected_paths must be a list")
    hits = []
    for pattern in patterns:
        if any(covers(pattern, path) for path in paths):
            hits.append(str(pattern))
    return hits


def scope_conflict(scope_a: object, scope_b: object) -> bool:
    """True when two tasks would own overlapping files."""
    left, right = validate_scope(scope_a), validate_scope(scope_b)
    return any(covers(a, b) for a in left for b in right)


def validate_task(task: object, protected: object = None) -> dict:
    """Validate and return a normalized task definition."""
    if not isinstance(task, dict):
        raise PolicyError("task must be an object")
    required = ("id", "title", "objective", "scope")
    missing = [key for key in required if key not in task]
    if missing:
        raise PolicyError("missing task fields: " + ", ".join(missing))
    task_id = task["id"]
    if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
        raise PolicyError("invalid task id")
    if not isinstance(task["title"], str) or not 3 <= len(task["title"]) <= 140:
        raise PolicyError("title must be 3-140 characters")
    objective = task["objective"]
    if not isinstance(objective, str) or not 10 <= len(objective) <= 4000:
        raise PolicyError("objective must be 10-4000 characters")
    scope = validate_scope(task["scope"])
    hits = protected_violations(scope, protected)
    if hits:
        raise PolicyError("scope overlaps protected paths: " + ", ".join(hits))
    deps = task.get("depends_on", [])
    if not isinstance(deps, list) or any(not isinstance(d, str) or not TASK_ID.fullmatch(d)
                                         for d in deps):
        raise PolicyError("depends_on must be a list of valid task ids")
    base = task.get("base", "main")
    if base != "main" and not BRANCH.fullmatch(base):
        raise PolicyError("invalid base ref")
    branch = task.get("branch", f"feat/canopy-supervisor-{task_id}")
    if not BRANCH.fullmatch(branch):
        raise PolicyError("invalid branch name")
    extra = {}
    for key in ("campaign", "kind", "publish", "artifacts"):
        if key in task:
            extra[key] = task[key]
    if task.get("kind") == "implementation" and not task.get("artifacts"):
        raise PolicyError("implementation tasks require verifiable artifacts")
    return {
        "id": task_id,
        "title": task["title"],
        "objective": objective,
        "scope": scope,
        "depends_on": list(deps),
        "base": base,
        "branch": branch,
        "tests_required": bool(task.get("tests_required", True)),
        **extra,
    }


def validate_evidence(evidence: object, task: dict, changed_files: object,
                      pending_allowed: bool = False) -> dict:
    """Check worker-reported evidence before any publish action.

    Evidence is a claim, not proof. The supervisor still inspects the real
    worktree diff and git state after this structural check.
    """
    if not isinstance(evidence, dict):
        raise PolicyError("evidence must be an object")
    if evidence.get("task_id") != task["id"]:
        raise PolicyError("evidence task_id mismatch")
    if evidence.get("branch") != task["branch"]:
        raise PolicyError("evidence branch mismatch")
    sha = evidence.get("commit_sha")
    if pending_allowed and sha == "PENDING":
        pass
    elif not isinstance(sha, str) or not COMMIT_SHA.fullmatch(sha):
        raise PolicyError("evidence commit_sha is missing or invalid")
    tests = evidence.get("tests")
    if not isinstance(tests, list) or not tests:
        raise PolicyError("evidence must list executed tests")
    passed = False
    for row in tests:
        if not isinstance(row, dict):
            raise PolicyError("invalid test row")
        command = row.get("command")
        result = row.get("result")
        if not isinstance(command, str) or not command.strip():
            raise PolicyError("test command required")
        if result not in RESULT:
            raise PolicyError("invalid test result")
        if result == "FAIL":
            raise PolicyError("worker reported a failing test")
        passed |= result == "PASS"
    if not passed or not bool(evidence.get("draft")):
        raise PolicyError("evidence requires at least one PASS test and a draft PR intent")
    if not isinstance(changed_files, list) or not changed_files:
        raise PolicyError("no changed files found in worktree")
    expected = validate_scope(task["scope"])
    for path in changed_files:
        if not any(covers(pattern, path) for pattern in expected):
            raise PolicyError(f"changed file outside task scope: {path}")
    return evidence
