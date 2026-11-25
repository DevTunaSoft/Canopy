#!/usr/bin/env python3
"""Read-only, offline verifier for an EXISTING Linux Mint Qt smoke report.

This checks internal consistency of an evidence directory made by
tools/mint_classic_qt_smoke.py. It NEVER runs Qt, claims real Mint execution,
approves visuals, installs packages, or changes an OS session. The report's
"environment: linuxmint" is self-reported; independent guest provenance
remains a separate manual acceptance gate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from tools import mint_classic_qt_smoke as qt

MAX_REPORT_BYTES = 128_000
# The smoke runner counts every SELF_TEST_PASS detail line, not just the
# required marker prefixes. Authentic compiled Qt emitted 21 per resolution
# for the real Mint report; prior scoped runs emitted 19 and 23. The cap is
# well above those bounded, documented outputs but still rejects implausible
# counts that cannot come from the self-test runner.
MAX_MARKER_LINES = 64
SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")
BINARY_SHA = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_SIZES = {(f"{width}x{height}", width, height) for width, height in qt.SIZES}
FIXED_KEYS = {
    "schema_version", "environment", "qt_smoke", "mint_guest_acceptance",
    "real_application_launch", "compositor_session_switching",
    "visual_owner_approval", "declared_source_sha",
    "verified_binary_sha256", "framing_review", "tests",
}
ROW_KEYS = {
    "resolution", "status", "screenshot", "screenshot_sha256",
    "exit_code", "markers_observed",
}


class EvidenceError(ValueError):
    """Evidence cannot be proven from this read-only directory."""


def _reject_nonstandard(value):
    raise EvidenceError("non-finite JSON number rejected")


def _reject_duplicate_keys(pairs):
    """Reject ambiguous objects before json.loads keeps only the last key."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("duplicate JSON key in report")
        result[key] = value
    return result


def _report(directory):
    root = qt.safe_resource(directory, "evidence directory", directory=True)
    report_path = root / "report.json"
    # Prevent following symlinked report files (including hard-to-see aliases).
    with qt._open_regular_file(report_path) as source:
        raw = source.read(MAX_REPORT_BYTES + 1)
    if not raw or len(raw) > MAX_REPORT_BYTES:
        raise EvidenceError("report missing or oversized")
    try:
        report = json.loads(raw.decode("utf-8"),
                            parse_constant=_reject_nonstandard,
                            object_pairs_hook=_reject_duplicate_keys)
    except EvidenceError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise EvidenceError("invalid report JSON") from exc
    if type(report) is not dict or set(report) != FIXED_KEYS:
        raise EvidenceError("unrecognized report schema")
    return root, report


def validate(directory, *, expected_source_sha, expected_binary_sha256):
    """Return bounded, non-acceptance status after independently reading PNGs."""
    if not isinstance(expected_source_sha, str) or not SOURCE_SHA.fullmatch(expected_source_sha):
        raise EvidenceError("explicit expected source commit SHA required")
    if not isinstance(expected_binary_sha256, str) or not BINARY_SHA.fullmatch(expected_binary_sha256):
        raise EvidenceError("explicit expected compiled binary SHA required")
    if not isinstance(directory, (str, os.PathLike)) or isinstance(directory, (bytes, bytearray)):
        raise EvidenceError("evidence directory must be a path")
    root, report = _report(directory)
    if (type(report["schema_version"]) is not int or report["schema_version"] != 1
            or report["environment"] != "linuxmint"
            or report["qt_smoke"] != "PASS"
            or report["mint_guest_acceptance"] != "PARTIAL_SMOKE_ONLY"
            or report["real_application_launch"] != "NOT_RUN"
            or report["compositor_session_switching"] != "NOT_RUN"
            or report["visual_owner_approval"] != "NOT_RUN"
            or type(report["framing_review"]) is not bool
            or report["declared_source_sha"] != expected_source_sha
            or report["verified_binary_sha256"] != expected_binary_sha256):
        raise EvidenceError("source/binary/status or report provenance mismatch")
    rows = report["tests"]
    if type(rows) is not list or len(rows) != len(qt.SIZES):
        raise EvidenceError("required three-resolution matrix incomplete")
    seen = set()
    marker_counts = set()
    # A runner PASS requires each mandatory marker exactly once; duplicates or
    # wrong names keep the report at FAIL. This gate cannot see marker names
    # in the fixed schema, so it bounds the recorded line count instead.
    required_markers = len(qt.REQUIRED_MARKERS) + (1 if report["framing_review"] else 0)
    checks = 0
    for row in rows:
        if type(row) is not dict or set(row) != ROW_KEYS:
            raise EvidenceError("unknown per-resolution schema")
        size = row["resolution"]
        if type(size) is not str:
            raise EvidenceError("invalid screenshot resolution")
        match = next(((w, h) for label, w, h in EXPECTED_SIZES if label == size), None)
        if match is None or size in seen:
            raise EvidenceError("duplicate or unsupported resolution")
        seen.add(size)
        width, height = match
        name = f"qt-{size}.png"
        if (row["screenshot"] != name or row["status"] != "PASS"
                or type(row["exit_code"]) is not int or row["exit_code"] != 0
                or type(row["screenshot_sha256"]) is not str
                or not BINARY_SHA.fullmatch(row["screenshot_sha256"])):
            raise EvidenceError("invalid PASS row, marker or screenshot name")
        observed = row["markers_observed"]
        if type(observed) is not int:
            raise EvidenceError("self-test marker count must be an integer")
        if observed < required_markers:
            raise EvidenceError("missing required self-test markers")
        if observed > MAX_MARKER_LINES:
            raise EvidenceError("implausible self-test marker count")
        marker_counts.add(observed)
        if len(marker_counts) != 1:
            raise EvidenceError("inconsistent self-test marker counts across resolutions")
        path = root / name
        try:
            actual = qt.png_size(path)  # CRC, zlib, bounds, visible variation
            digest = qt.file_sha256(path)  # O_NOFOLLOW + regular-file guard
        except (OSError, qt.MintSmokeError) as exc:
            raise EvidenceError("missing or corrupt screenshot evidence") from exc
        if actual != (width, height) or digest != row["screenshot_sha256"]:
            raise EvidenceError("screenshot dimensions or SHA-256 mismatch")
        checks += 1
    if seen != {label for label, _, _ in EXPECTED_SIZES}:
        raise EvidenceError("missing required screen size")
    return {
        "status": "PASS",
        "kind": "offline-screenshot-evidence-integrity",
        "screenshots_verified": checks,
        "sha256_verified": True,
        "linux_mint_execution_independently_proven": False,
        "mint_guest_acceptance": "NOT_ESTABLISHED",
        "owner_visual_approval": "NOT_ESTABLISHED",
        "session_and_compositor_acceptance": "NOT_ESTABLISHED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    options = parser.parse_args(argv)
    try:
        result = validate(
            options.evidence_dir,
            expected_source_sha=options.expected_source_sha,
            expected_binary_sha256=options.expected_binary_sha256,
        )
    except (EvidenceError, qt.MintSmokeError, OSError) as exc:
        print("MINT_EVIDENCE_GATE_FAIL:", str(exc)[:160], file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
