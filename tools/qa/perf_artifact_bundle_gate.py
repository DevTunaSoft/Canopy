#!/usr/bin/env python3
"""Bounded OFFLINE gate for a bundle of performance evidence artifacts.

A "bundle" is a JSON object carrying one or more snapshot artifacts (records
produced by ``PerformanceSnapshot.as_dict()``) and zero or more idle-evidence
reports. This module composes two already-tested offline validators --

``tools.qa.perf_snapshot_artifact_validator`` and
``tools.qa.perf_evidence_gate`` -- into one fail-closed gate. Each member is
checked by its owning validator; nothing is measured, executed or launched.
The aggregate report carries only fixed tokens plus hardcoded negative
claims.

This gate NEVER grants a release, Linux Mint, hardware or visual approval.
The optional SHA pins are only format-checked inputs forwarded to the idle
evidence gate; self-reported evidence is still not signed provenance. The
module reads no clocks, /proc state, sockets, processes or threads, and its
optional file reader is bounded and symlink-safe. A malformed, drifted,
unbounded or claim-flipped bundle raises :class:`BundleError` with a fixed
message; no caller value is echoed into an error or into the report.
"""
import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
import sys

# Support direct script execution (``python tools/qa/<this file>.py``) as well
# as package import (``from tools.qa import ...``) without duplicating either
# validator's logic. In package mode __package__ is "tools.qa" and no change
# to sys.path is needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.qa import perf_evidence_gate as evidence_gate
from tools.qa import perf_snapshot_artifact_validator as snapshot_validator

SCHEMA = 1
MAX_BUNDLE_BYTES = 65_536
MAX_SNAPSHOTS = 8
MAX_BASELINES = 8

TOP_KEYS = frozenset({
    "schema", "snapshots", "baselines", "source_sha", "binary_sha256",
})
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
BASELINE_STATUSES = frozenset({"PASS", "FAIL", "INSUFFICIENT_EVIDENCE"})


class BundleError(ValueError):
    """Invalid, drifted, unbounded or claim-flipped artifact bundle."""


@dataclass(frozen=True)
class BundleReport:
    """Frozen aggregate of already-validated offline evidence."""

    snapshot_count: int
    snapshot_evidence_counts: tuple
    baseline_count: int
    baseline_statuses: tuple

    def as_dict(self):
        """Return a fresh JSON-serializable copy with fixed negative claims.

        Every claim field is hardcoded here rather than stored on the record,
        so even a directly constructed (forged) record cannot emit an
        approval through the public serialization path.
        """
        return {
            "status": "VALID",
            "schema": SCHEMA,
            "snapshot_count": self.snapshot_count,
            "snapshot_evidence_counts": list(self.snapshot_evidence_counts),
            "baseline_count": self.baseline_count,
            "baseline_statuses": list(self.baseline_statuses),
            "release_approved": False,
            "linux_mint_acceptance_proven": False,
            "real_hardware_measured": False,
            "owner_visual_approval": False,
            "measurement_performed": False,
        }


def _int(value):
    if type(value) is not int:
        raise BundleError("bundle integer field has wrong type")
    return value


def _pin(value, pattern):
    """Accept None or a lowercase hex digest of the exact required length."""
    if value is None:
        return None
    if type(value) is not str or not pattern.fullmatch(value):
        raise BundleError("bundle SHA pin is malformed")
    return value


def evaluate_bundle(bundle):
    """Validate every member of a parsed bundle and return a frozen report.

    Fails closed with :class:`BundleError` before returning any record when
    the shape, bounds, pins or any member artifact is invalid. Sub-validator
    errors are translated to fixed bundle tokens; their detail is chained as
    the cause, never copied into the message.
    """
    if type(bundle) is not dict or frozenset(bundle) != TOP_KEYS:
        raise BundleError("bundle has an unexpected key set")
    if _int(bundle["schema"]) != SCHEMA:
        raise BundleError("bundle schema is unsupported")

    snapshots = bundle["snapshots"]
    if (type(snapshots) is not list
            or not 1 <= len(snapshots) <= MAX_SNAPSHOTS):
        raise BundleError("bundle snapshots are invalid or unbounded")
    baselines = bundle["baselines"]
    if type(baselines) is not list or len(baselines) > MAX_BASELINES:
        raise BundleError("bundle baselines are invalid or unbounded")

    source_sha = _pin(bundle["source_sha"], SHA40)
    binary_sha256 = _pin(bundle["binary_sha256"], SHA64)

    counts = []
    for artifact in snapshots:
        try:
            report = snapshot_validator.validate(artifact)
        except snapshot_validator.ArtifactError as exc:
            raise BundleError("bundle snapshot artifact rejected") from exc
        count = report["evidence_count"]
        if type(count) is not int or count < 0:
            raise BundleError("bundle snapshot count is invalid")
        counts.append(count)

    statuses = []
    for evidence in baselines:
        try:
            result = evidence_gate.assess(
                evidence, expected_source_sha=source_sha,
                expected_binary_sha256=binary_sha256,
            )
        except evidence_gate.EvidenceError as exc:
            raise BundleError("bundle idle evidence rejected") from exc
        status = result["status"]
        if type(status) is not str or status not in BASELINE_STATUSES:
            raise BundleError("bundle idle status is unsupported")
        statuses.append(status)

    return BundleReport(
        snapshot_count=len(snapshots),
        snapshot_evidence_counts=tuple(counts),
        baseline_count=len(baselines),
        baseline_statuses=tuple(statuses),
    )


def _nonfinite(token):
    raise BundleError("non-finite JSON number rejected")


def validate_bundle_json(text):
    """Decode bounded UTF-8 JSON text into a bundle and validate it."""
    if isinstance(text, bytes):
        data = text
    elif type(text) is str:
        try:
            data = text.encode("utf-8")
        except UnicodeError as exc:
            raise BundleError("bundle text cannot be encoded") from exc
    else:
        raise BundleError("bundle JSON must be text or bytes")
    if not data or len(data) > MAX_BUNDLE_BYTES:
        raise BundleError("bundle JSON is missing or oversized")
    try:
        parsed = json.loads(data.decode("utf-8"), parse_constant=_nonfinite)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BundleError("bundle JSON could not be parsed") from exc
    return evaluate_bundle(parsed)


def validate_bundle_file(path):
    """Read a bounded, symlink-safe regular file and validate its bundle."""
    p = Path(path)
    if not p.is_absolute():
        raise BundleError("absolute bundle path required")
    current = Path(p.anchor)
    for part in p.parts[1:]:
        current /= part
        if current.is_symlink():
            raise BundleError("symlinked bundle path rejected")
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        # POSIX allows os.open() on a directory and only fails at fdopen();
        # Windows fails at os.open() instead. Keep the whole read path inside
        # one OSError boundary so either host fails closed with BundleError.
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise BundleError("bundle path is not a regular file")
            data = handle.read(MAX_BUNDLE_BYTES + 1)
    except OSError as exc:
        raise BundleError("bundle file missing or unsafe") from exc
    if not data or len(data) > MAX_BUNDLE_BYTES:
        raise BundleError("bundle JSON is missing or oversized")
    return validate_bundle_json(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate_bundle_file(args.bundle).as_dict()
    except (BundleError, OSError) as exc:
        print("QT_PERF_BUNDLE_FAIL:", str(exc)[:150], file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
