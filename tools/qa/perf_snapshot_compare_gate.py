#!/usr/bin/env python3
"""Bounded OFFLINE gate comparing two validated performance snapshots.

A "comparison" pairs a baseline and a candidate snapshot artifact -- records
produced by ``PerformanceSnapshot.as_dict()`` (``canopy_features/performance``).
This module composes the already-tested offline validator
``tools.qa.perf_snapshot_artifact_validator``: BOTH members must validate
before any comparison is produced. It then computes a fixed allowlist of
bounded, deterministic *directional* comparisons (did each metric go higher,
lower or stay equal) for the metrics the artifacts carry.

Nothing is measured, executed or launched, and no numeric caller value is
copied into the report or an error: the report holds only fixed direction
tokens and fixed negative claims. A direction here is diagnostic only -- it is
never a performance pass/fail verdict. This gate NEVER grants a release,
Linux Mint, hardware or visual approval.

The file reader is bounded, absolute-path-only and symlink-safe (the whole
open/fdopen/fstat/read path sits inside one ``OSError`` boundary, with
``O_NOFOLLOW`` on the final component). Malformed, drifted, unbounded or
claim-flipped input raises :class:`CompareError` with a fixed message; no
caller value is echoed.
"""
import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import stat
import sys

# Support direct script execution (``python tools/qa/<this file>.py``) as well
# as package import (``from tools.qa import ...``) without duplicating the
# validator's logic. In package mode __package__ is "tools.qa" and no change
# to sys.path is needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.qa import perf_snapshot_artifact_validator as snapshot_validator

SCHEMA = 1
MAX_COMPARE_BYTES = 65_536
TOP_KEYS = frozenset({"schema", "baseline", "candidate"})

# Fixed allowlist of (report name, path into a validated artifact). No
# caller-supplied key can become a report field.
METRICS = (
    ("frame_mean_ms", ("frame_pacing", "mean_ms")),
    ("frame_p95_ms", ("frame_pacing", "p95_ms")),
    ("frame_p99_ms", ("frame_pacing", "p99_ms")),
    ("frame_dropped_rate", ("frame_pacing", "dropped_frame_rate")),
    ("memory_peak_kib", ("memory_growth", "peak_kib")),
    ("memory_delta_kib", ("memory_growth", "delta_kib")),
    ("launch_cold_mean_ms", ("launch_latency", "cold", "mean_ms")),
    ("launch_warm_mean_ms", ("launch_latency", "warm", "mean_ms")),
    ("pss_kib", ("pss_kib",)),
)
DIRECTIONS = frozenset({"higher", "lower", "equal", "not_available"})


class CompareError(ValueError):
    """Invalid, drifted, unbounded or claim-flipped comparison input."""


@dataclass(frozen=True)
class CompareReport:
    """Frozen directional comparison of two already-validated artifacts."""

    baseline_evidence_count: int
    candidate_evidence_count: int
    directions: tuple  # one fixed token per METRICS entry, in METRICS order

    def as_dict(self):
        """Return a fresh JSON-serializable copy with fixed negative claims.

        Every claim field is hardcoded here rather than stored on the record,
        so even a directly constructed (forged) record cannot emit an
        approval through the public serialization path. The directions map is
        rebuilt from the fixed METRICS allowlist, never from caller keys.
        """
        # Validate the token type BEFORE the frozenset membership test: an
        # unhashable wrong type (list, dict, bytearray) would otherwise leak a
        # raw TypeError from ``in`` instead of this fail-closed CompareError.
        if (type(self.directions) is not tuple
                or len(self.directions) != len(METRICS)
                or any(type(tok) is not str or tok not in DIRECTIONS
                       for tok in self.directions)):
            raise CompareError("comparison report directions are invalid")
        if (type(self.baseline_evidence_count) is not int
                or not 0 <= self.baseline_evidence_count <= len(METRICS)
                or type(self.candidate_evidence_count) is not int
                or not 0 <= self.candidate_evidence_count <= len(METRICS)):
            raise CompareError("comparison report counts are invalid")
        return {
            "status": "VALID",
            "schema": SCHEMA,
            "baseline_evidence_count": self.baseline_evidence_count,
            "candidate_evidence_count": self.candidate_evidence_count,
            "directions": {
                name: tok for (name, _), tok in zip(METRICS, self.directions)
            },
            "release_approved": False,
            "linux_mint_acceptance_proven": False,
            "real_hardware_measured": False,
            "owner_visual_approval": False,
            "measurement_performed": False,
        }


def _is_number(value):
    """True only for a finite non-bool number (a valid artifact value)."""
    if type(value) is bool:
        return False
    if type(value) is int:
        return True
    if type(value) is float:
        return math.isfinite(value)
    return False


def _direction(baseline, candidate, path):
    """Return one fixed token for a metric path across two validated dicts."""
    a, b = baseline, candidate
    for key in path:
        if not isinstance(a, dict) or not isinstance(b, dict):
            return "not_available"
        if key not in a or key not in b:
            return "not_available"
        a, b = a[key], b[key]
    if a is None or b is None or not _is_number(a) or not _is_number(b):
        return "not_available"
    if b > a:
        return "higher"
    if b < a:
        return "lower"
    return "equal"


def evaluate_compare(comparison):
    """Validate both members, then return a frozen directional report.

    Fails closed with :class:`CompareError` before returning any record when
    the shape, schema or either member artifact is invalid. Sub-validator
    errors are translated to fixed comparison tokens; their detail is chained
    as the cause, never copied into the message.
    """
    if type(comparison) is not dict or frozenset(comparison) != TOP_KEYS:
        raise CompareError("comparison has an unexpected key set")
    if type(comparison["schema"]) is not int or comparison["schema"] != SCHEMA:
        raise CompareError("comparison schema is unsupported")
    try:
        base_report = snapshot_validator.validate(comparison["baseline"])
    except snapshot_validator.ArtifactError as exc:
        raise CompareError("comparison baseline artifact rejected") from exc
    try:
        cand_report = snapshot_validator.validate(comparison["candidate"])
    except snapshot_validator.ArtifactError as exc:
        raise CompareError("comparison candidate artifact rejected") from exc

    baseline = comparison["baseline"]
    candidate = comparison["candidate"]
    directions = tuple(
        _direction(baseline, candidate, path) for _, path in METRICS
    )
    return CompareReport(
        baseline_evidence_count=base_report["evidence_count"],
        candidate_evidence_count=cand_report["evidence_count"],
        directions=directions,
    )


def _reject_constant(token):
    raise CompareError("comparison JSON contains a non-finite number")


def compare_json(text):
    """Decode bounded UTF-8 JSON text into a comparison and evaluate it."""
    if isinstance(text, bytes):
        data = text
    elif type(text) is str:
        try:
            data = text.encode("utf-8")
        except UnicodeError as exc:
            raise CompareError("comparison text cannot be encoded") from exc
    else:
        raise CompareError("comparison JSON must be text or bytes")
    if not data or len(data) > MAX_COMPARE_BYTES:
        raise CompareError("comparison JSON is missing or oversized")
    try:
        parsed = json.loads(
            data.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CompareError("comparison JSON could not be parsed") from exc
    return evaluate_compare(parsed)


def compare_file(path):
    """Read a bounded, symlink-safe regular file and compare its JSON."""
    p = Path(path)
    if not p.is_absolute():
        raise CompareError("absolute comparison path required")
    current = Path(p.anchor)
    for part in p.parts[1:]:
        current /= part
        if current.is_symlink():
            raise CompareError("symlinked comparison path rejected")
    # One OSError boundary for the whole descriptor path: on POSIX os.open()
    # accepts a directory and the failure only appears at fdopen()/read(), so
    # a narrow except around os.open() alone would leak a built-in on Ubuntu.
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise CompareError("comparison path is not a regular file")
            data = handle.read(MAX_COMPARE_BYTES + 1)
    except OSError as exc:
        raise CompareError("comparison file missing or unsafe") from exc
    if not data or len(data) > MAX_COMPARE_BYTES:
        raise CompareError("comparison JSON is missing or oversized")
    return compare_json(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comparison", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_file(args.comparison).as_dict()
    except (CompareError, OSError) as exc:
        print("QT_PERF_COMPARE_FAIL:", str(exc)[:150], file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
