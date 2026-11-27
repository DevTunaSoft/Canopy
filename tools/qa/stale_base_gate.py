#!/usr/bin/env python3
"""Pure-Python stale-base / sibling-coverage gate for PR heads (PE-112).

The gate consumes a bounded JSON snapshot of already-collected facts. It makes
no network request, opens no process, runs no git command, reads no repository
state and performs no source mutation. Git blob input is collected by the
test-only adapter in ``tests/stale_base_gate_adapter.py``.

A head FAILS when either condition holds:

  * ``STALE_BASE`` -- its merge base with the current integration tip is not
    that tip. A PR branched before a sibling test merged looks clean in a
    three-dot diff yet silently drops coverage; this catches it.
  * ``SIBLING_ABSENT`` / ``SIBLING_CHANGED`` -- a declared sibling test blob is
    missing from the head, or its byte-derived SHA-256 differs from the digest
    at the integration tip. Comparing head bytes to tip bytes (not the diff)
    catches a test that never existed at the branch point.

All inputs are fail-closed: wrong types, unknown keys, duplicate JSON keys,
unsafe sibling paths and oversized snapshots raise ``StaleBaseGateError``.
Report strings contain only fixed tokens and validated paths/SHAs. This gate
never approves a merge, release, Mint acceptance or visual change.
"""
import argparse
import json
import os
import re
import sys

SCHEMA = 1
MAX_SNAPSHOT_BYTES = 131_072
MAX_SIBLINGS = 256
MAX_PATH_CHARS = 200

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
PATH_CHARS = re.compile(r"[A-Za-z0-9._/\-]+\Z")

TOP_KEYS = frozenset({"schema", "integration_tip", "head", "merge_base", "siblings"})
SIBLING_KEYS = frozenset({"path", "tip_blob", "head_blob"})
FINDING_CODES = ("SIBLING_ABSENT", "SIBLING_CHANGED", "STALE_BASE")
MALFORMED = "MALFORMED_SNAPSHOT"


class StaleBaseGateError(ValueError):
    """Malformed, unbounded or unrecognized gate snapshot."""


def _bounded_int(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise StaleBaseGateError(MALFORMED + ": " + label)
    return value


def _sha(value, pattern, label, allow_none=False):
    if value is None and allow_none:
        return None
    if type(value) is not str or not pattern.fullmatch(value):
        raise StaleBaseGateError(MALFORMED + ": " + label)
    return value


def _sibling_path(value):
    if type(value) is not str or not 1 <= len(value) <= MAX_PATH_CHARS:
        raise StaleBaseGateError(MALFORMED + ": sibling path")
    if not value.startswith("tests/") or not value.endswith(".py"):
        raise StaleBaseGateError(MALFORMED + ": sibling path scope")
    if "\\" in value or "//" in value:
        raise StaleBaseGateError(MALFORMED + ": sibling path separator")
    if any(segment in ("", ".", "..") for segment in value.split("/")):
        raise StaleBaseGateError(MALFORMED + ": sibling path traversal")
    if not PATH_CHARS.fullmatch(value):
        raise StaleBaseGateError(MALFORMED + ": sibling path characters")
    return value


def _validated_siblings(raw):
    if type(raw) is not list or len(raw) > MAX_SIBLINGS:
        raise StaleBaseGateError(MALFORMED + ": siblings")
    result, seen = [], set()
    for item in raw:
        if type(item) is not dict or frozenset(item) != SIBLING_KEYS:
            raise StaleBaseGateError(MALFORMED + ": sibling keys")
        path = _sibling_path(item["path"])
        if path in seen:
            raise StaleBaseGateError(MALFORMED + ": duplicate sibling path")
        seen.add(path)
        result.append({
            "path": path,
            "tip_blob": _sha(item["tip_blob"], SHA64, "tip blob"),
            "head_blob": _sha(item["head_blob"], SHA64, "head blob", allow_none=True),
        })
    return result


def evaluate(snapshot):
    """Validate ``snapshot`` and return a deterministic verdict report."""
    if type(snapshot) is not dict or frozenset(snapshot) != TOP_KEYS:
        raise StaleBaseGateError(MALFORMED + ": top-level keys")
    _bounded_int(snapshot["schema"], "schema", SCHEMA, SCHEMA)

    tip = _sha(snapshot["integration_tip"], SHA40, "integration tip")
    head = _sha(snapshot["head"], SHA40, "head")
    merge_base = _sha(snapshot["merge_base"], SHA40, "merge base", allow_none=True)
    siblings = _validated_siblings(snapshot["siblings"])

    head_current = merge_base == tip
    findings = []
    if not head_current:
        findings.append({"code": "STALE_BASE", "path": None})
    for sibling in siblings:
        if sibling["head_blob"] is None:
            findings.append({"code": "SIBLING_ABSENT", "path": sibling["path"]})
        elif sibling["head_blob"] != sibling["tip_blob"]:
            findings.append({"code": "SIBLING_CHANGED", "path": sibling["path"]})
    findings.sort(key=lambda finding: (finding["code"], finding["path"] or ""))

    counts = {code: 0 for code in FINDING_CODES}
    for finding in findings:
        counts[finding["code"]] += 1

    return {
        "schema": SCHEMA,
        "integration_tip": tip,
        "head_sha": head,
        "merge_base": merge_base,
        "head_current": head_current,
        "sibling_count": len(siblings),
        "findings": findings,
        "counts": counts,
        "verdict": "FAIL" if findings else "PASS",
        "approvals": {
            "merge": False, "release": False, "visual": False, "mint": False,
        },
    }


def _reject_constant(token):
    raise StaleBaseGateError(MALFORMED + ": non-finite number")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StaleBaseGateError(MALFORMED + ": duplicate key")
        result[key] = value
    return result


def load_snapshot(path):
    """Read and parse a bounded, absolute, non-symlink snapshot file."""
    try:
        raw_path = os.fspath(path)
    except TypeError as exc:
        raise StaleBaseGateError(MALFORMED + ": path type") from exc
    if type(raw_path) is not str or not os.path.isabs(raw_path):
        raise StaleBaseGateError(MALFORMED + ": path must be absolute")
    if os.path.islink(raw_path) or not os.path.isfile(raw_path):
        raise StaleBaseGateError(MALFORMED + ": path must be a regular file")
    try:
        size = os.stat(raw_path).st_size
    except OSError as exc:
        raise StaleBaseGateError(MALFORMED + ": unreadable path") from exc
    if size > MAX_SNAPSHOT_BYTES:
        raise StaleBaseGateError(MALFORMED + ": oversized snapshot")
    try:
        with open(raw_path, "rb") as handle:
            raw = handle.read(MAX_SNAPSHOT_BYTES + 1)
    except OSError as exc:
        raise StaleBaseGateError(MALFORMED + ": unreadable snapshot") from exc
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise StaleBaseGateError(MALFORMED + ": oversized snapshot")
    try:
        text = raw.decode("utf-8")
        parsed = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise StaleBaseGateError(MALFORMED + ": invalid JSON") from exc
    if type(parsed) is not dict:
        raise StaleBaseGateError(MALFORMED + ": snapshot must be an object")
    return parsed


def main(argv=None):
    """CLI entry point: 0 PASS, 1 findings, 2 malformed snapshot/usage."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", required=True, help="absolute bounded JSON snapshot path")
    args = parser.parse_args(argv)
    try:
        report = evaluate(load_snapshot(args.snapshot))
    except StaleBaseGateError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
