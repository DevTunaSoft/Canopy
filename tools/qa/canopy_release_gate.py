#!/usr/bin/env python3
"""Bounded OFFLINE release-readiness gate. NO release approval is granted.

This module composes two already-produced RECORDS (it imports neither
producer, so it works before either is merged):

* a PR dependency-order report (``tools/qa/pr_dependency_gate`` output), and
* an offline acceptance verdict (gate statuses R047/R050/R066/R073/R074/R078/
  R086 plus integrity and a self-reported ``release_ready`` flag).

It emits a deterministic, fail-closed blocker report. ``release_ready`` is
hardcoded False on the output: a self-reported acceptance claim is never
trusted, and an untrusted ``release_ready: true`` on input is itself a blocker
token. Only fixed tokens and bounded integers reach the output; no gate name,
PR number list detail, source path, SHA or other caller text is echoed.

No network, process launch, git command, file discovery or repository state is
used. Duplicate JSON object keys are rejected before evaluation, so a repeated
``acceptance_verdict``, gate id, count or ``release_ready`` field cannot let the
last copy erase a hold or an untrusted release claim. The optional file reader
is bounded, absolute-path-only and symlink-safe with the whole descriptor
path inside one ``OSError`` boundary (POSIX-safe).
"""
import argparse
import json
import os
from pathlib import Path
import stat
import sys

SCHEMA = 1
MAX_SNAPSHOT_BYTES = 262_144
MAX_COUNT = 10_000

TOP_KEYS = frozenset({"schema", "dependency_report", "acceptance_verdict"})

DEP_KEYS = frozenset({
    "status", "schema", "pr_count", "held_count", "ready_count",
    "held_pr_numbers", "merge_order", "hold_reasons", "release_approved",
    "linux_mint_acceptance_proven", "owner_visual_approval",
    "merge_performed", "network_accessed", "process_launched",
})
DEP_NEGATIVES = frozenset({
    "release_approved", "linux_mint_acceptance_proven", "owner_visual_approval",
    "merge_performed", "network_accessed", "process_launched",
})
DEP_HOLD_TOKENS = frozenset({
    "DEPENDENCY_HOLD", "MISSING_PREREQUISITE", "UNMET_SHA_CHECKS",
    "FORBIDDEN_BASE", "NOT_OPEN", "RELEASE_HOLD", "VISUAL_HOLD",
})
VERDICT_KEYS = frozenset({
    "schema", "verdict", "integrity", "release_ready", "gates",
})
VERDICT_TOKENS = frozenset({
    "PASS", "PASS_SCOPED", "PARTIAL_SCOPED", "FAIL", "BLOCKED", "NOT_RUN",
})
INTEGRITY_TOKENS = frozenset({"PASS", "FAIL", "UNVERIFIED"})
GATE_IDS = frozenset({"R047", "R050", "R066", "R073", "R074", "R078", "R086"})
GATE_STATUSES = frozenset({
    "PASS", "PASS_SCOPED", "PASS_NUMERIC_SCOPED", "PARTIAL_SCOPED",
    "NOT_RUN", "BLOCKED", "UNVERIFIED", "FAIL",
})
FULL_PASS = frozenset({"PASS"})
BLOCKER_TOKENS = frozenset({
    "STACKED_PR_HOLD", "VISUAL_HOLD", "MINT_HOLD", "RUNNER_HOLD",
    "R086_HOLD", "P0_HOLD", "INTEGRITY_HOLD",
    "UNTRUSTED_RELEASE_CLAIM",
})
MINT_GATES = ("R073", "R074")
RUNNER_GATES = ("R086",)


class ReleaseGateError(ValueError):
    """Malformed, unbounded or unrecognized release-readiness input."""


def _bounded_int(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ReleaseGateError("snapshot " + label + " is invalid or unbounded")
    return value


def _bool(value, label):
    if type(value) is not bool:
        raise ReleaseGateError("snapshot " + label + " must be boolean")
    return value


def _token(value, allowed, label):
    # Type-check before membership so unhashable wrong types cannot leak a
    # raw TypeError past this fail-closed boundary (item 11 contract class).
    if type(value) is not str or value not in allowed:
        raise ReleaseGateError("snapshot " + label + " token is unsupported")
    return value


def _false(value, label):
    if value is not False:
        raise ReleaseGateError("snapshot " + label + " negative claim is not False")


def _int_tuple(value, label, maximum=MAX_COUNT):
    # JSON round-tripping turns tuples into lists; accept both bounded shapes.
    if type(value) not in (list, tuple) or len(value) > maximum:
        raise ReleaseGateError("snapshot " + label + " is invalid or unbounded")
    result = []
    for item in value:
        if type(item) is not int or not 0 <= item <= maximum:
            raise ReleaseGateError("snapshot " + label + " is invalid or unbounded")
        result.append(item)
    return tuple(result)


def _check_dependency(report):
    if type(report) is not dict or frozenset(report) != DEP_KEYS:
        raise ReleaseGateError("dependency report has an unexpected key set")
    _token(report["status"], frozenset({"MERGE_ORDER_COMPUTED"}),
           "dependency report status")
    _bounded_int(report["schema"], "dependency schema", SCHEMA, SCHEMA)
    for key in ("pr_count", "held_count", "ready_count"):
        _bounded_int(report[key], key, 0, MAX_COUNT)
    if report["held_count"] + report["ready_count"] > MAX_COUNT:
        raise ReleaseGateError("dependency counts are inconsistent")
    _int_tuple(report["held_pr_numbers"], "held PR numbers")
    _int_tuple(report["merge_order"], "merge order")
    reasons = report["hold_reasons"]
    if (type(reasons) not in (list, tuple)
            or len(reasons) > len(DEP_HOLD_TOKENS)
            or any(_token(item, DEP_HOLD_TOKENS, "dependency hold") is None
                   for item in reasons)):
        raise ReleaseGateError("dependency hold reasons are invalid")
    for key in DEP_NEGATIVES:
        _false(report[key], "dependency " + key)
    return report


def _check_verdict(verdict):
    if type(verdict) is not dict or frozenset(verdict) != VERDICT_KEYS:
        raise ReleaseGateError("acceptance verdict has an unexpected key set")
    _bounded_int(verdict["schema"], "verdict schema", SCHEMA, SCHEMA)
    _token(verdict["verdict"], VERDICT_TOKENS, "verdict")
    _token(verdict["integrity"], INTEGRITY_TOKENS, "integrity")
    self_reported = _bool(verdict["release_ready"], "release ready")
    gates = verdict["gates"]
    if type(gates) is not dict or frozenset(gates) != GATE_IDS:
        raise ReleaseGateError("acceptance gates have an unexpected key set")
    for gate_id in GATE_IDS:
        _token(gates[gate_id], GATE_STATUSES, "gate " + gate_id)
    return self_reported, gates


def evaluate(snapshot):
    """Validate both records and return a fixed-token blocker report."""
    if type(snapshot) is not dict or frozenset(snapshot) != TOP_KEYS:
        raise ReleaseGateError("snapshot has an unexpected key set")
    _bounded_int(snapshot["schema"], "schema", SCHEMA, SCHEMA)
    dependency = _check_dependency(snapshot["dependency_report"])
    self_reported, gates = _check_verdict(snapshot["acceptance_verdict"])

    blockers = set()
    if dependency["held_count"] or dependency["hold_reasons"]:
        blockers.add("STACKED_PR_HOLD")
    if gates["R078"] not in FULL_PASS:
        blockers.add("VISUAL_HOLD")
    if any(gates[name] not in FULL_PASS for name in MINT_GATES):
        blockers.add("MINT_HOLD")
    if any(gates[name] not in FULL_PASS for name in RUNNER_GATES):
        blockers.add("RUNNER_HOLD")
        blockers.add("R086_HOLD")
    if any(value not in FULL_PASS for value in gates.values()):
        blockers.add("P0_HOLD")
    if snapshot["acceptance_verdict"]["integrity"] != "PASS":
        blockers.add("INTEGRITY_HOLD")
    if self_reported:
        # A self-reported release claim is never trusted; it is a blocker,
        # not an input that could turn release_ready true.
        blockers.add("UNTRUSTED_RELEASE_CLAIM")

    return {
        "status": "RELEASE_READINESS_REPORTED",
        "schema": SCHEMA,
        "release_ready": False,
        "blocker_count": len(blockers),
        "blocker_tokens": tuple(sorted(blockers)),
        "dependency_hold_reasons": tuple(sorted(set(dependency["hold_reasons"]))),
        "held_pr_count": dependency["held_count"],
        "gates_checked": len(GATE_IDS),
        "release_approved": False,
        "linux_mint_acceptance_proven": False,
        "owner_visual_approval": False,
        "real_mint_run_proven": False,
        "runner_proven": False,
        "merge_performed": False,
        "network_accessed": False,
        "process_launched": False,
    }


def _unique_object(pairs):
    """Reject duplicate JSON object keys; the last-wins default can erase a hold."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseGateError("snapshot JSON contains a duplicate key")
        result[key] = value
    return result


def _reject_constant(token):
    raise ReleaseGateError("snapshot JSON contains a non-finite number")


def evaluate_json(text):
    """Decode bounded UTF-8 JSON text and evaluate the snapshot."""
    if isinstance(text, bytes):
        data = text
    elif type(text) is str:
        try:
            data = text.encode("utf-8")
        except UnicodeError as exc:
            raise ReleaseGateError("snapshot text cannot be encoded") from exc
    else:
        raise ReleaseGateError("snapshot JSON must be text or bytes")
    if not data or len(data) > MAX_SNAPSHOT_BYTES:
        raise ReleaseGateError("snapshot JSON is missing or oversized")
    try:
        parsed = json.loads(
            data.decode("utf-8"), parse_constant=_reject_constant,
            object_pairs_hook=_unique_object)
    except ReleaseGateError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ReleaseGateError("snapshot JSON could not be parsed") from exc
    return evaluate(parsed)


def evaluate_file(path):
    """Read a bounded, symlink-safe regular file and evaluate its JSON."""
    p = Path(path)
    if not p.is_absolute():
        raise ReleaseGateError("absolute snapshot path required")
    current = Path(p.anchor)
    for part in p.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ReleaseGateError("symlinked snapshot path rejected")
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ReleaseGateError("snapshot path is not a regular file")
            data = handle.read(MAX_SNAPSHOT_BYTES + 1)
    except OSError as exc:
        raise ReleaseGateError("snapshot file missing or unsafe") from exc
    if not data or len(data) > MAX_SNAPSHOT_BYTES:
        raise ReleaseGateError("snapshot JSON is missing or oversized")
    return evaluate_json(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate_file(args.snapshot)
    except (ReleaseGateError, OSError) as exc:
        print("CANOPY_RELEASE_GATE_FAIL:", str(exc)[:150], file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
