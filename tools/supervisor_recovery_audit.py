#!/usr/bin/env python3
"""Read-only audit of preserved supervisor campaigns for safe recovery.

The tool never commits, pushes, edits state or opens PRs. It replays the
supervisor's artifact verifier against the real evidence and worktree, runs
the authored unit tests only when explicitly asked, and reports which
campaigns can be safely published for human review.

Usage:
    python tools/supervisor_recovery_audit.py --state-root <dir> [--run-tests]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MAX_TASKS = 256
MAX_PATHS = 128
MAX_EVIDENCE_BYTES = 1_000_000
TEST_TIMEOUT_SECONDS = 120

MODULE_PATH = re.compile(r"^canopy_features/[a-z_]+/[a-z0-9_]+\.py$")
TEST_PATH = re.compile(r"^tests/test_c100_[a-z0-9_]+\.py$")
PACKAGE_INIT = re.compile(r"^(?:canopy_features(?:/[a-z_]+)*|tests)/__init__\.py$")
VISUAL_PATH = re.compile(
    r"(?i)(assets?/|wallpaper|artwork|\.png$|\.svg$|\.qml$|\.cpp$|\.h$|"
    r"dock_geometry|prototype/|\.github/workflows/)")
HAZARD_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(?:subprocess|socket|threading|multiprocessing|"
    r"time|requests|urllib|PyQt|PySide)\b")
IMPORT_MODULE = re.compile(r"^\s*(?:import|from)\s+([A-Za-z0-9_.]+)")
SAFE_MINT_MODULE = re.compile(r"^canopy_features/mint/[a-z0-9_]+\.py$")


def hazard_imports(path: str, source: str) -> list[str]:
    """Flag risky imports, allowing safe parsers and read-only Mint argv probes.

    urllib.parse is a pure parser, and Mint dependency probes may call a fixed
    argv with a timeout and no shell. Network, timer, thread and generic shell
    imports remain rejected everywhere.
    """
    hits = []
    for line in source.splitlines():
        if not HAZARD_IMPORT.match(line):
            continue
        match = IMPORT_MODULE.match(line)
        module = match.group(1) if match else ""
        if module == "urllib.parse":
            continue
        if module == "subprocess" and SAFE_MINT_MODULE.match(path) \
                and "shell=True" not in source and "shell = True" not in source:
            continue
        hits.append(line.strip())
    return sorted(set(hits))


def normalize_worktree(raw: object) -> Path:
    """Normalize doubled backslashes found in historical task state."""
    if not isinstance(raw, str) or not raw:
        raise ValueError("invalid worktree path")
    return Path(raw.replace("\\\\", "/").replace("\\", "/"))


def _git_lines(args: list[str], cwd: Path) -> list[str]:
    try:
        proc = subprocess.run(["git", "-C", str(cwd), *args],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode:
        return []
    return [line for line in proc.stdout.splitlines() if line]


def worktree_paths(worktree: Path) -> list[str]:
    """List tracked changes plus every individual untracked file."""
    if not worktree.is_dir():
        return []
    found = set(_git_lines(["ls-files", "--others", "--exclude-standard"], worktree))
    found.update(_git_lines(["diff", "--name-only", "HEAD"], worktree))
    for base in ("07853e9566d466e48ac01b8bbf6332357a45f119",):
        found.update(_git_lines(["diff", "--name-only", base], worktree))
    return sorted(found)[:MAX_PATHS]


def _read_evidence(state_root: Path, task_id: str) -> dict:
    path = state_root / "evidence" / task_id / "evidence.json"
    if not path.is_file() or path.stat().st_size > MAX_EVIDENCE_BYTES:
        raise ValueError("missing or oversized evidence")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("evidence must be an object")
    return data


def _replay_tests(worktree: Path, evidence: dict) -> dict:
    command = next((row.get("command", "") for row in evidence.get("tests", [])
                    if isinstance(row, dict) and row.get("result") == "PASS"), "")
    module = next((part for part in command.split() if part.startswith("tests.")), None)
    if not module or not re.fullmatch(r"tests\.[A-Za-z0-9_.]+", module):
        return {"status": "NOT RUN", "module": "", "detail": "no safe test module"}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", module, "-q"],
            cwd=worktree, capture_output=True, text=True,
            timeout=TEST_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "FAIL", "module": module, "detail": str(exc)[:200]}
    text = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-5:])
    return {"status": "PASS" if proc.returncode == 0 else "FAIL",
            "module": module, "detail": text[:600]}


def _verify_digest(path: Path, reported: object) -> None:
    """Fail-closed, case-insensitive SHA-256 check independent of supervisor state."""
    if not isinstance(reported, str):
        raise ValueError("invalid artifact SHA-256")
    try:
        expected = bytes.fromhex(reported.strip())
    except ValueError as exc:
        raise ValueError("invalid artifact SHA-256") from exc
    if len(expected) != 32:
        raise ValueError("invalid artifact SHA-256")
    if hashlib.sha256(path.read_bytes()).digest() != expected:
        raise ValueError("artifact SHA-256 mismatch")


def audit_task(task: dict, state_root: Path, *, run_tests: bool = False) -> dict:
    """Return a fail-closed audit verdict for one historical task."""
    result = {"id": task.get("id", ""), "branch": task.get("branch", ""),
              "status": "", "paths": [], "problems": [], "disclosed": [],
              "actual_shas": {}, "test_replay": {"status": "NOT RUN"}}
    problems: list[str] = []
    try:
        worktree = normalize_worktree(task.get("worktree"))
        evidence = _read_evidence(state_root, result["id"])
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        result["problems"].append("missing_inputs:" + str(exc)[:120])
        result["status"] = "missing_inputs"
        return result

    results = {row.get("result") for row in evidence.get("tests", [])
               if isinstance(row, dict)}
    if results - {"PASS"}:
        result["disclosed"].append("evidence_result_" +
                                   ",".join(sorted(str(x) for x in results - {"PASS"})))
    paths = worktree_paths(worktree)
    result["paths"] = paths
    if not paths:
        problems.append("no_changed_paths")
    for path in paths:
        if MODULE_PATH.match(path) or TEST_PATH.match(path) or PACKAGE_INIT.match(path):
            continue  # allowlisted pure-Python paths cannot be visual assets
        if VISUAL_PATH.search(path):
            problems.append("visual_path:" + path)
        problems.append("out_of_scope:" + path)

    for artifact in evidence.get("artifacts", []):
        if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
            problems.append("invalid_artifact_entry")
            continue
        relative = artifact["path"]
        if not MODULE_PATH.match(relative) and not TEST_PATH.match(relative):
            problems.append("artifact_out_of_scope:" + relative)
            continue
        artifact_path = worktree / relative
        if not artifact_path.is_file():
            problems.append("missing_artifact:" + relative)
            continue
        result["actual_shas"][relative] = hashlib.sha256(
            artifact_path.read_bytes()).hexdigest()
        try:
            _verify_digest(artifact_path, artifact.get("sha256"))
        except ValueError as exc:
            problems.append("artifact_verification:" + str(exc))

    for path in paths:
        if not MODULE_PATH.match(path):
            continue
        source = (worktree / path).read_text(encoding="utf-8", errors="replace")
        hits = hazard_imports(path, source)
        if hits:
            problems.append("hazard_import:" + path + ":" + ",".join(hits))

    if run_tests:
        result["test_replay"] = _replay_tests(worktree, evidence)
        if result["test_replay"]["status"] != "PASS":
            problems.append("test_replay_" + result["test_replay"]["status"])

    result["problems"] = problems
    result["status"] = "recoverable" if not problems else "rejected"
    return result


def audit_all(state_root: Path, *, run_tests: bool = False,
              limit: int = MAX_TASKS) -> list[dict]:
    path = state_root / "tasks.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data["tasks"] if isinstance(data, dict) else data
    if not isinstance(tasks, list):
        raise ValueError("tasks.json must contain a task list")
    if not 1 <= limit <= MAX_TASKS:
        raise ValueError("limit out of range")
    return [audit_task(task, state_root, run_tests=run_tests)
            for task in tasks[:limit] if isinstance(task, dict)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--run-tests", action="store_true",
                        help="execute authored unit tests in each worktree (bounded timeout)")
    parser.add_argument("--limit", type=int, default=MAX_TASKS)
    args = parser.parse_args(argv)
    try:
        rows = audit_all(args.state_root, run_tests=args.run_tests, limit=args.limit)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("RECOVERY_AUDIT_BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    payload = json.dumps(rows, indent=1, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print("RECOVERY_AUDIT " + json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
