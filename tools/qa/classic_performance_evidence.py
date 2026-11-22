#!/usr/bin/env python3
"""Offline validator for the real five-minute Classic CI-host idle report.

This tool only PARSES a report produced elsewhere (``tools/measure_qt.py``).
It never starts Qt, samples a process, waits, or generates a measurement.

Reported PR #151 CI artifact (Ubuntu GitHub Actions, Xvfb,
QT_QUICK_BACKEND=software): 300-second idle CPU 0.003% of one core, PSS
57372 -> 60486 KiB. Those figures come from the uploaded CI artifact; they
are NOT Linux Mint acceptance, compositor evidence, or visual signoff.

Reuse ``tools.qa.perf_evidence_gate`` for bounded/symlink-safe reading and for
the separate Mint schema. This module adds only the CI-host classification so
a green Ubuntu number cannot be presented as Mint or release acceptance.
"""
import argparse
import json
import math
from pathlib import Path
import sys

if __package__:
    from tools.qa import perf_evidence_gate as base
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.qa import perf_evidence_gate as base

CI_HOST = "ubuntu-github-actions"
RUNNERS = (CI_HOST, "ubuntu-22.04-github-actions",
           "ubuntu-24.04-github-actions")
REPORT_KEYS = frozenset({
    "schema", "kind", "duration_seconds", "cpu_percent_one_core",
    "pss_kib_start", "pss_kib_end", "backend",
})
REPORT_KIND = "short-headless-baseline-not-mint-acceptance"
BACKENDS = frozenset({"default", "software", "opengl", "vulkan"})
MIN_IDLE_SECONDS = 300.0
MAX_IDLE_SECONDS = 3600.0
MAX_PSS_KIB = base.MAX_MEMORY_KIB
MAX_CPU_PERCENT = base.MAX_CPU_ONE_CORE


def _finite(value, field):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise base.EvidenceError(field + " must be a finite number")
    return float(value)


def _bounded_int(value, field, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise base.EvidenceError(field + " outside safe bounds")
    return value


def _pins(source_sha, binary_sha256):
    if not isinstance(source_sha, str) or not base.SHA40.fullmatch(source_sha):
        raise base.EvidenceError("external source SHA pin is required")
    if (not isinstance(binary_sha256, str)
            or not base.SHA64.fullmatch(binary_sha256)):
        raise base.EvidenceError("external binary SHA-256 pin is required")


def validate(report, *, expected_source_sha, expected_binary_sha256,
             runner=CI_HOST):
    """Classify a measured report; never grant Mint or release acceptance."""
    if type(report) is not dict:
        raise base.EvidenceError("idle report must be a JSON object")
    if frozenset(report) != REPORT_KEYS:
        raise base.EvidenceError("unexpected or missing idle report fields")
    if type(report["schema"]) is not int or report["schema"] != 1:
        raise base.EvidenceError("unsupported idle report schema")
    if report["kind"] != REPORT_KIND:
        raise base.EvidenceError("unsupported idle report kind")
    if runner not in RUNNERS or "mint" in runner.lower():
        raise base.EvidenceError(
            "Mint acceptance requires perf_evidence_gate with independent guest evidence")
    _pins(expected_source_sha, expected_binary_sha256)

    duration = _finite(report["duration_seconds"], "duration_seconds")
    if not MIN_IDLE_SECONDS <= duration <= MAX_IDLE_SECONDS:
        raise base.EvidenceError("not a five-minute idle observation")
    cpu = _finite(report["cpu_percent_one_core"], "cpu_percent_one_core")
    if not 0.0 <= cpu <= 100.0:
        raise base.EvidenceError("impossible CPU percentage")
    pss_start = _bounded_int(report["pss_kib_start"], "pss_kib_start",
                             1, MAX_PSS_KIB * 10)
    pss_end = _bounded_int(report["pss_kib_end"], "pss_kib_end",
                           1, MAX_PSS_KIB * 10)
    backend = report["backend"]
    if not isinstance(backend, str) or backend not in BACKENDS:
        raise base.EvidenceError("unsupported Qt backend")

    within_targets = (cpu <= MAX_CPU_PERCENT
                      and max(pss_start, pss_end) <= MAX_PSS_KIB)
    return {
        "status": "CI_HOST_EVIDENCE_ONLY",
        "numeric_targets_met": within_targets,
        "runner": runner,
        "measurement": "headless-qt-five-minute-idle",
        "duration_seconds": duration,
        "cpu_percent_one_core": cpu,
        "pss_kib_start": pss_start,
        "pss_kib_end": pss_end,
        "pss_growth_kib": pss_end - pss_start,
        "backend": backend,
        "linux_mint_acceptance": False,
        "release_approved": False,
        "visual_approval": False,
        "scope": "CI-host headless observation; not Mint, compositor or visual acceptance",
        "source": "parsed local report only; no measurement generated",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--runner", default=CI_HOST)
    args = parser.parse_args(argv)
    try:
        report = base._real_file(args.report)
        result = validate(
            report,
            expected_source_sha=args.expected_source_sha,
            expected_binary_sha256=args.expected_binary_sha256,
            runner=args.runner,
        )
    except (base.EvidenceError, OSError) as exc:
        print("CLASSIC_CI_EVIDENCE_FAIL:", str(exc)[:150], file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    # Exit 0 means the report parsed and classified; it is NOT acceptance.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
