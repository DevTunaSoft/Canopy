#!/usr/bin/env python3
"""Bounded OFFLINE gate for Qt memory/CPU evidence, never a benchmark runner.

Existing 5-second headless Qt baselines are deliberately classified as
INSUFFICIENT_EVIDENCE for the five-minute Linux Mint release targets.
A future long-idle sampler may produce schema 2 with raw tick and PSS
observations. Self-reported data is NOT a signed guest provenance record.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

MAX_REPORT_BYTES = 65_536
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_MEMORY_KIB = 204_800  # <=200 MiB shell-owned PSS
MAX_CPU_ONE_CORE = 1.0  # <=1% of one logical CPU
MIN_IDLE_SECONDS = 300.0


class EvidenceError(ValueError):
    pass


def _real(value):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise EvidenceError("numeric evidence must be finite")
    return float(value)


def _int(value, minimum=0):
    if type(value) is not int or value < minimum or value > 10**13:
        raise EvidenceError("invalid bounded integer evidence")
    return value


def _nonfinite(token):
    raise EvidenceError("non-finite JSON number rejected")


def _real_file(path):
    p = Path(path)
    if not p.is_absolute():
        raise EvidenceError("absolute evidence path required")
    current = Path(p.anchor)
    for part in p.parts[1:]:
        current /= part
        if current.is_symlink():
            raise EvidenceError("symlinked evidence path rejected")
    # O_NOFOLLOW closes the final-component symlink race between checking
    # the path and opening the report. No writes or network calls.
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise EvidenceError("evidence report missing or unsafe") from exc
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise EvidenceError("non-regular report file")
        data = f.read(MAX_REPORT_BYTES + 1)
    if not data or len(data) > MAX_REPORT_BYTES:
        raise EvidenceError("report missing or oversized")
    try:
        parsed = json.loads(data.decode("utf-8"), parse_constant=_nonfinite)
    except (UnicodeError, ValueError) as exc:
        raise EvidenceError("invalid report JSON") from exc
    if type(parsed) is not dict:
        raise EvidenceError("performance report must be an object")
    return parsed


def assess(evidence, *, expected_source_sha=None, expected_binary_sha256=None):
    """Return an auditable metric classification; never grant release approval."""
    if type(evidence) is not dict:
        raise EvidenceError("performance evidence must be a JSON object")
    if (evidence.get("schema") == 1 and
        evidence.get("kind") == "short-headless-baseline-not-mint-acceptance"):
        expected = {
            "schema", "kind", "duration_seconds", "cpu_percent_one_core",
            "pss_kib_start", "pss_kib_end", "backend",
        }
        if set(evidence) != expected:
            raise EvidenceError("unknown short-baseline schema")
        if (_int(evidence["schema"]) != 1 or
            not 1 <= _real(evidence["duration_seconds"]) <= 30 or
            not 0 <= _real(evidence["cpu_percent_one_core"]) <= 1600 or
            type(evidence["backend"]) is not str or
            not 1 <= len(evidence["backend"]) <= 40):
            raise EvidenceError("short-baseline fields invalid")
        _int(evidence["pss_kib_start"])
        _int(evidence["pss_kib_end"])
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "headless observation below five-minute Mint idle requirement",
            "release_approved": False,
            "linux_mint_guest_proven": False,
        }

    expected = {
        "schema", "kind", "environment", "measurement_method", "source_sha",
        "binary_sha256", "backend", "duration_seconds", "sample_count",
        "cpu_ticks_start", "cpu_ticks_end", "clock_ticks_per_second",
        "pss_kib_start", "pss_kib_end", "pss_kib_peak",
    }
    if set(evidence) != expected or evidence.get("schema") != 2 or type(evidence["schema"]) is not int:
        raise EvidenceError("unrecognized long-idle evidence schema")
    if not (isinstance(expected_source_sha, str) and SHA40.fullmatch(expected_source_sha)
            and isinstance(expected_binary_sha256, str)
            and SHA64.fullmatch(expected_binary_sha256)):
        raise EvidenceError("long-idle evidence requires external source and binary SHA pins")
    if (evidence["source_sha"] != expected_source_sha
            or evidence["binary_sha256"] != expected_binary_sha256
            or evidence["kind"] != "five-minute-idle-linux-qt"
            or evidence["environment"] != "linuxmint"
            or evidence["measurement_method"] != "proc-smaps-rollup-and-stat"
            or evidence["backend"] not in ("software", "opengl", "vulkan", "default")):
        raise EvidenceError("unverified measurement method or provenance mismatch")
    elapsed = _real(evidence["duration_seconds"])
    sample_count = _int(evidence["sample_count"], 1)
    start_ticks = _int(evidence["cpu_ticks_start"])
    end_ticks = _int(evidence["cpu_ticks_end"])
    hz = _int(evidence["clock_ticks_per_second"], 1)
    pss_start = _int(evidence["pss_kib_start"])
    pss_end = _int(evidence["pss_kib_end"])
    pss_peak = _int(evidence["pss_kib_peak"])
    if (not 0 < elapsed <= 86_400 or
            not 1 <= sample_count <= min(100_000, elapsed * 20) or
            end_ticks < start_ticks or not 10 <= hz <= 10_000 or
            not 0 <= pss_start <= pss_peak or
            not 0 <= pss_end <= pss_peak):
        raise EvidenceError("impossible or unbounded process observation")
    if elapsed < MIN_IDLE_SECONDS or sample_count < 60:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "need >=300 seconds and >=60 idle PSS/CPU samples",
            "release_approved": False,
            "linux_mint_guest_proven": False,
        }
    cpu = 100.0 * (end_ticks - start_ticks) / (hz * elapsed)
    within_targets = cpu <= MAX_CPU_ONE_CORE and pss_peak <= MAX_MEMORY_KIB
    return {
        "status": "PASS" if within_targets else "FAIL",
        "scope": "self-reported numeric idle targets only",
        "measured_seconds": elapsed,
        "observations": sample_count,
        "cpu_percent_one_core_calculated": round(cpu, 4),
        "pss_kib_peak": pss_peak,
        "cpu_target_percent_one_core": MAX_CPU_ONE_CORE,
        "memory_target_kib": MAX_MEMORY_KIB,
        "release_approved": False,
        "linux_mint_guest_proven": False,
        "visual_approval": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--expected-binary-sha256")
    args = parser.parse_args(argv)
    try:
        data = _real_file(args.report)
        result = assess(data, expected_source_sha=args.expected_source_sha,
                        expected_binary_sha256=args.expected_binary_sha256)
    except (EvidenceError, OSError) as exc:
        print("QT_PERF_GATE_FAIL:", str(exc)[:150], file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return {"PASS": 0, "FAIL": 1, "INSUFFICIENT_EVIDENCE": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
