#!/usr/bin/env python3
"""Bounded OFFLINE merge-order gate for a stacked Pull Request snapshot.

The integrator merges verified PRs in dependency order. This module consumes a
JSON snapshot of open PRs plus a dependency map (for example the real
``{"377": 375}`` hold) and computes a deterministic, fail-closed merge-order
report. It closes the stacked-PR hazard where a PR is merged while its
prerequisite is still open or unmerged.

Inputs are already-collected facts: this module makes NO network request,
opens no process, runs no git command and reads no repository state. It
accepts a bounded, absolute, symlink-safe JSON file for offline CI use.

A PR is held when any of these fixed conditions applies:
  * ``DEPENDENCY_HOLD`` -- its prerequisite PR is present but not MERGED;
  * ``MISSING_PREREQUISITE`` -- its prerequisite PR is absent entirely;
  * ``UNMET_SHA_CHECKS`` -- a required check is not SUCCESS at the PR's exact
    ``headRefOid``;
  * ``FORBIDDEN_BASE`` -- its base branch is not the allowed integration branch;
  * ``NOT_OPEN`` -- its state is not OPEN;
  * ``RELEASE_HOLD`` / ``VISUAL_HOLD`` -- host-supplied global holds.

A cyclic dependency map is malformed: it is refused with DependencyGateError
rather than producing a merge order.

Error and report messages contain only fixed tokens and validated bounded
integers. No branch name, SHA, check name, PR title or other caller text is
ever echoed. This gate NEVER approves a release, a Linux Mint acceptance, an
owner visual approval or a merge: those claims are hardcoded false.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA = 1
MAX_SNAPSHOT_BYTES = 262_144
MAX_PRS = 64
MAX_CHECKS = 16
MAX_PR_NUMBER = 1_000_000
MAX_TEXT = 128

TOP_KEYS = frozenset({
    "schema", "integration_branch", "pulls", "dependencies",
    "release_hold", "visual_hold",
})
PULL_KEYS = frozenset({
    "number", "state", "baseRefName", "headRefOid", "statusCheckRollup",
})
CHECK_KEYS = frozenset({"name", "state", "conclusion", "headSha"})

ALLOWED_BASES = frozenset({"integration/canopy-classic-20261123"})
PR_STATES = frozenset({"OPEN", "CLOSED", "MERGED"})
CHECK_STATES = frozenset({"PENDING", "COMPLETED"})
CHECK_CONCLUSIONS = frozenset({
    "SUCCESS", "FAILURE", "NEUTRAL", "CANCELLED", "SKIPPED", "TIMED_OUT",
    "ACTION_REQUIRED", "STALE",
})
REQUIRED_CHECKS = frozenset({"foundation", "qt-evidence"})

HOLD_TOKENS = frozenset({
    "DEPENDENCY_HOLD", "MISSING_PREREQUISITE", "UNMET_SHA_CHECKS",
    "FORBIDDEN_BASE", "NOT_OPEN", "RELEASE_HOLD", "VISUAL_HOLD",
})
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
DECIMAL = re.compile(r"[0-9]{1,7}\Z")


class DependencyGateError(ValueError):
    """Malformed, unbounded or unrecognized PR dependency snapshot."""


def _bounded_int(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise DependencyGateError("snapshot " + label + " is invalid or unbounded")
    return value


def _bool(value, label):
    if type(value) is not bool:
        raise DependencyGateError("snapshot " + label + " must be boolean")
    return value


def _token(value, allowed, label):
    # Type-check before membership so unhashable wrong types cannot leak a
    # raw TypeError past this fail-closed boundary (item 11 contract class).
    if type(value) is not str or value not in allowed:
        raise DependencyGateError("snapshot " + label + " token is unsupported")
    return value


def _sha(value, label):
    if type(value) is not str or not SHA40.fullmatch(value):
        raise DependencyGateError("snapshot " + label + " SHA is malformed")
    return value


def _reject_constant(token):
    raise DependencyGateError("snapshot JSON contains a non-finite number")


def _unique_object(pairs):
    """Reject duplicate JSON object keys instead of letting the last one win."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise DependencyGateError("snapshot JSON contains a duplicate key")
        result[key] = value
    return result


def _validated_pulls(snapshot):
    raw = snapshot["pulls"]
    if type(raw) is not list or len(raw) > MAX_PRS:
        raise DependencyGateError("snapshot pulls are invalid or unbounded")
    pulls, seen = [], set()
    for entry in raw:
        if type(entry) is not dict or frozenset(entry) != PULL_KEYS:
            raise DependencyGateError("snapshot pull has an unexpected key set")
        number = _bounded_int(
            entry["number"], "pull number", 1, MAX_PR_NUMBER)
        if number in seen:
            raise DependencyGateError("snapshot pull number is duplicated")
        seen.add(number)
        state = _token(entry["state"], PR_STATES, "pull state")
        base = entry["baseRefName"]
        if type(base) is not str or not base or len(base) > MAX_TEXT:
            raise DependencyGateError("snapshot base branch is invalid")
        # The base is validated (not echoed); only its allowlist membership
        # reaches the report as a fixed FORBIDDEN_BASE token.
        head = _sha(entry["headRefOid"], "pull head")
        checks = entry["statusCheckRollup"]
        if type(checks) is not list or len(checks) > MAX_CHECKS:
            raise DependencyGateError("snapshot check rollup is invalid or unbounded")
        met, check_names = set(), set()
        for check in checks:
            if type(check) is not dict or frozenset(check) != CHECK_KEYS:
                raise DependencyGateError("snapshot check has an unexpected key set")
            name = check["name"]
            if type(name) is not str or not name or len(name) > MAX_TEXT:
                raise DependencyGateError("snapshot check name is invalid")
            check_names.add(name)
            check_state = _token(check["state"], CHECK_STATES, "check state")
            conclusion = check["conclusion"]
            if conclusion is not None:
                _token(conclusion, CHECK_CONCLUSIONS, "check conclusion")
            check_sha = _sha(check["headSha"], "check head")
            if (name in REQUIRED_CHECKS and check_state == "COMPLETED"
                    and conclusion == "SUCCESS" and check_sha == head):
                met.add(name)
        pulls.append({
            "number": number,
            "state": state,
            "base_allowed": base in ALLOWED_BASES,
            "checks_met": met >= REQUIRED_CHECKS,
            "check_names": check_names,
        })
    return pulls


def _validated_dependencies(snapshot, known_numbers):
    raw = snapshot["dependencies"]
    if type(raw) is not dict or len(raw) > MAX_PRS:
        raise DependencyGateError("snapshot dependencies are invalid or unbounded")
    result = {}
    for key, value in raw.items():
        if type(key) is not str or not DECIMAL.fullmatch(key):
            raise DependencyGateError("snapshot dependency key is malformed")
        dependent = int(key)
        if not 1 <= dependent <= MAX_PR_NUMBER:
            raise DependencyGateError("snapshot dependency key is out of range")
        prerequisite = _bounded_int(
            value, "dependency prerequisite", 1, MAX_PR_NUMBER)
        if dependent == prerequisite:
            raise DependencyGateError("self dependency is refused")
        # Only known PRs may declare a prerequisite, so an unknown key cannot
        # smuggle a hold into the report.
        if dependent not in known_numbers:
            raise DependencyGateError("dependency references an unknown PR")
        if dependent in result:
            raise DependencyGateError("duplicate dependency is refused")
        result[dependent] = prerequisite
    # Each dependent has at most one prerequisite, so the map is a functional
    # graph: follow every chain at most once (bounded by MAX_PRS) and refuse a
    # cycle. A cyclic map recorded with one member already MERGED used to emit
    # a zero-hold merge_order for the other member: a false PASS for a graph
    # that could never have been built in dependency order.
    settled = set()
    for start in result:
        if start in settled:
            continue
        path = set()
        node = start
        while node in result:
            if node in path:
                raise DependencyGateError("dependency cycle is refused")
            if node in settled:
                break
            path.add(node)
            node = result[node]
        settled.update(path)
    return result


def evaluate(snapshot):
    """Validate a snapshot and return a frozen-like fixed-token report dict."""
    if type(snapshot) is not dict or frozenset(snapshot) != TOP_KEYS:
        raise DependencyGateError("snapshot has an unexpected key set")
    _bounded_int(snapshot["schema"], "schema", SCHEMA, SCHEMA)
    integration = snapshot["integration_branch"]
    if (type(integration) is not str or not integration
            or len(integration) > MAX_TEXT
            or integration not in ALLOWED_BASES):
        raise DependencyGateError("snapshot integration branch is unsupported")
    release_hold = _bool(snapshot["release_hold"], "release hold")
    visual_hold = _bool(snapshot["visual_hold"], "visual hold")

    pulls = _validated_pulls(snapshot)
    numbers = {pull["number"] for pull in pulls}
    dependencies = _validated_dependencies(snapshot, numbers)
    states = {pull["number"]: pull["state"] for pull in pulls}

    held, ready, reasons = [], [], set()
    for pull in pulls:
        number = pull["number"]
        if pull["state"] == "MERGED":
            # A merged prerequisite is terminal: not a hold and not a
            # candidate for another merge.
            continue
        local = set()
        if pull["state"] != "OPEN":
            local.add("NOT_OPEN")
        if not pull["base_allowed"]:
            local.add("FORBIDDEN_BASE")
        if not pull["checks_met"]:
            local.add("UNMET_SHA_CHECKS")
        if number in dependencies:
            prerequisite = dependencies[number]
            if prerequisite not in states:
                local.add("MISSING_PREREQUISITE")
            elif states[prerequisite] != "MERGED":
                local.add("DEPENDENCY_HOLD")
        if release_hold:
            local.add("RELEASE_HOLD")
        if visual_hold:
            local.add("VISUAL_HOLD")
        if local:
            held.append(number)
            reasons.update(local)
        else:
            ready.append(number)

    return {
        "status": "MERGE_ORDER_COMPUTED",
        "schema": SCHEMA,
        "pr_count": len(pulls),
        "held_count": len(held),
        "ready_count": len(ready),
        "held_pr_numbers": tuple(sorted(held)),
        "merge_order": tuple(sorted(ready)),
        "hold_reasons": tuple(sorted(reasons)),
        "release_approved": False,
        "linux_mint_acceptance_proven": False,
        "owner_visual_approval": False,
        "merge_performed": False,
        "network_accessed": False,
        "process_launched": False,
    }


def evaluate_json(text):
    """Decode bounded UTF-8 JSON text and evaluate the snapshot."""
    if isinstance(text, bytes):
        data = text
    elif type(text) is str:
        try:
            data = text.encode("utf-8")
        except UnicodeError as exc:
            raise DependencyGateError("snapshot text cannot be encoded") from exc
    else:
        raise DependencyGateError("snapshot JSON must be text or bytes")
    if not data or len(data) > MAX_SNAPSHOT_BYTES:
        raise DependencyGateError("snapshot JSON is missing or oversized")
    try:
        parsed = json.loads(
            data.decode("utf-8"), parse_constant=_reject_constant,
            object_pairs_hook=_unique_object)
    except DependencyGateError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DependencyGateError("snapshot JSON could not be parsed") from exc
    return evaluate(parsed)


def evaluate_file(path):
    """Read a bounded, symlink-safe regular file and evaluate its JSON."""
    p = Path(path)
    if not p.is_absolute():
        raise DependencyGateError("absolute snapshot path required")
    current = Path(p.anchor)
    for part in p.parts[1:]:
        current /= part
        if current.is_symlink():
            raise DependencyGateError("symlinked snapshot path rejected")
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise DependencyGateError("snapshot path is not a regular file")
            data = handle.read(MAX_SNAPSHOT_BYTES + 1)
    except OSError as exc:
        raise DependencyGateError("snapshot file missing or unsafe") from exc
    if not data or len(data) > MAX_SNAPSHOT_BYTES:
        raise DependencyGateError("snapshot JSON is missing or oversized")
    return evaluate_json(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate_file(args.snapshot)
    except (DependencyGateError, OSError) as exc:
        print("QT_PR_DEPENDENCY_FAIL:", str(exc)[:150], file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
