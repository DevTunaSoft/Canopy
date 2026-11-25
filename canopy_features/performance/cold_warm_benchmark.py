#!/usr/bin/env python3
"""Bounded OFFLINE summary of recorded Canopy Classic Qt cold/warm startup runs.

This component is a summarizer, not a benchmark runner. It never starts a
process, polls, reads /proc, uses a network/paid API, or starts a background
service. It consumes run records that an external, real runner already
collected (for example time-to-CANOPY_CLASSIC_WINDOW_READY) and returns an
auditable summary with the environment metadata of those runs.

It never grants release approval and never claims a real Linux Mint guest or
compiled Qt was tested. Self-reported performance claims inside a record are
rejected by the strict schema. Recorded metadata such as ``distro=linuxmint``
is data, not proof of a guest run.

Future integration still needed: wire a real startup runner to emit these
records; this module alone does not prove a working desktop shell.
"""
import math
import re
import statistics

MAX_RUNS = 256
MAX_STARTUP_MS = 3_600_000.0  # one hour; generous but bounded
MAX_TEXT_LEN = 200
SCHEMA = 1

KINDS = ("cold", "warm")
BACKENDS = ("software", "opengl", "vulkan", "default")
MEASUREMENT_METHODS = (
    "qelapsedtimer-to-window-ready",
    "elapsed-to-CANOPY_CLASSIC_WINDOW_READY",
)
ENVIRONMENT_FIELDS = (
    "distro", "kernel", "session_type", "qt_version", "backend",
    "cpu", "gpu", "driver",
)
RUN_FIELDS = frozenset({
    "schema", "kind", "startup_ms", "environment", "source_sha",
    "binary_sha256", "measurement_method",
})
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")


class RunError(ValueError):
    """Raised for an invalid, unbounded or self-reported run record."""


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise RunError(f"{name} must be a finite number")
    return float(value)


def _text(value, name):
    if type(value) is not str or not 1 <= len(value) <= MAX_TEXT_LEN:
        raise RunError(f"{name} must be bounded text")
    return value


def _sha(value, pattern, name):
    if type(value) is not str or not pattern.fullmatch(value):
        raise RunError(f"{name} must be a lowercase hex digest")
    return value


def _environment(value):
    if type(value) is not dict or set(value) != set(ENVIRONMENT_FIELDS):
        raise RunError("environment metadata must carry exactly the required fields")
    return {field: _text(value[field], f"environment.{field}")
            for field in ENVIRONMENT_FIELDS}


def _validate_run(run):
    if type(run) is not dict:
        raise RunError("startup run must be an object")
    # Strict key set: extra fields such as 'claim', 'release_approved' or
    # 'linux_mint_proven' are self-reported performance claims, rejected here.
    if set(run) != RUN_FIELDS:
        raise RunError("unknown or self-reported claim field in startup run")
    if type(run["schema"]) is not int or run["schema"] != SCHEMA:
        raise RunError("unrecognized startup run schema")
    if run["kind"] not in KINDS or type(run["kind"]) is not str:
        raise RunError("invalid startup run kind")
    startup_ms = _finite(run["startup_ms"], "startup_ms")
    if not 0 < startup_ms <= MAX_STARTUP_MS:
        raise RunError("startup_ms must be positive and bounded")
    if run["measurement_method"] not in MEASUREMENT_METHODS:
        raise RunError("unverified measurement method")
    return {
        "schema": SCHEMA,
        "kind": run["kind"],
        "startup_ms": startup_ms,
        "environment": _environment(run["environment"]),
        "source_sha": _sha(run["source_sha"], _SHA40, "source_sha"),
        "binary_sha256": _sha(run["binary_sha256"], _SHA64, "binary_sha256"),
        "measurement_method": run["measurement_method"],
    }


def _signature(run):
    env = run["environment"]
    return (tuple(env[field] for field in ENVIRONMENT_FIELDS)
            + (run["source_sha"], run["binary_sha256"],
               run["measurement_method"]))


def _stats(values):
    values = sorted(values)
    return {
        "count": len(values),
        "min_ms": round(values[0], 3),
        "median_ms": round(statistics.median(values), 3),
        "max_ms": round(values[-1], 3),
        "mean_ms": round(sum(values) / len(values), 3),
    }


def summarize(runs, *, expected_source_sha=None, expected_binary_sha256=None):
    """Summarize recorded cold/warm runs; pair only matching builds/environments.

    ``runs`` is an iterable of run records. A run is paired only when the same
    environment signature has at least one cold and one warm record. Unpaired
    runs are reported, never silently compared. The result is a bounded,
    offline observation and contains no release or Mint acceptance claim.
    """
    if type(runs) in (dict, str, bytes):
        raise RunError("runs must be a sequence of run records")
    if expected_source_sha is not None:
        _sha(expected_source_sha, _SHA40, "expected_source_sha")
    if expected_binary_sha256 is not None:
        _sha(expected_binary_sha256, _SHA64, "expected_binary_sha256")

    grouped = {}
    count = 0
    for run in runs:
        count += 1
        if count > MAX_RUNS:
            raise RunError(f"more than {MAX_RUNS} startup runs rejected")
        clean = _validate_run(run)
        if expected_source_sha is not None and clean["source_sha"] != expected_source_sha:
            raise RunError("run source SHA does not match external pin")
        if (expected_binary_sha256 is not None
                and clean["binary_sha256"] != expected_binary_sha256):
            raise RunError("run binary SHA does not match external pin")
        grouped.setdefault(_signature(clean), []).append(clean)

    environments = []
    unpaired_run_count = 0
    for signature in sorted(grouped):
        records = grouped[signature]
        cold = [r["startup_ms"] for r in records if r["kind"] == "cold"]
        warm = [r["startup_ms"] for r in records if r["kind"] == "warm"]
        paired = bool(cold and warm)
        if not paired:
            unpaired_run_count += len(records)
        env = dict(zip(ENVIRONMENT_FIELDS, signature[:len(ENVIRONMENT_FIELDS)]))
        entry = {
            "environment": env,
            "source_sha": signature[-3],
            "binary_sha256": signature[-2],
            "measurement_method": signature[-1],
            "cold": _stats(cold) if cold else None,
            "warm": _stats(warm) if warm else None,
            "paired": paired,
            "unpaired_reason": None if paired else (
                "no_warm_run" if cold else "no_cold_run"),
            "comparison": None,
        }
        if paired:
            cold_median = statistics.median(cold)
            warm_median = statistics.median(warm)
            entry["comparison"] = {
                "cold_median_ms": round(cold_median, 3),
                "warm_median_ms": round(warm_median, 3),
                "warm_minus_cold_ms": round(warm_median - cold_median, 3),
                "warm_faster": warm_median < cold_median,
                "scope": "observation of recorded runs only",
            }
        environments.append(entry)

    paired_count = len(environments) - sum(1 for e in environments if not e["paired"])
    return {
        "schema": SCHEMA,
        "scope": "offline summary of externally recorded startup runs",
        "run_count": count,
        "environment_count": len(environments),
        "paired_environment_count": paired_count,
        "unpaired_environment_count": len(environments) - paired_count,
        "unpaired_run_count": unpaired_run_count,
        "environments": environments,
        "source_sha_pinned": expected_source_sha is not None,
        "binary_sha256_pinned": expected_binary_sha256 is not None,
        "release_approved": False,
        "linux_mint_guest_proven": False,
        "compiled_qt_proven": False,
        "visual_approval": False,
    }
