"""Offline cold/warm startup latency summaries with explicit provenance.

Pure functions only: no process launch, no clock reads, no I/O, no polling,
no threads, no background services and no privileged access. Callers supply
timestamps they captured earlier; this module never observes the system
clock, so a given input set always produces the same summary.

Every input sample is either aggregated or excluded with a stated reason.
The returned summary records which clocks, marker sources and source SHAs
contributed, and which samples were rejected and why, so the numbers carry
their own provenance. This module does not measure a running desktop and is
not evidence that any Qt application starts quickly.
"""
from dataclasses import dataclass
import re
from statistics import median

SCHEMA = 1
COLD = "cold"
WARM = "warm"
KINDS = (COLD, WARM)

MONOTONIC_CLOCKS = frozenset({"monotonic", "monotonic_raw"})
KNOWN_CLOCKS = MONOTONIC_CLOCKS | {"realtime"}

MAX_SAMPLES = 10_000
MAX_SOURCE_BYTES = 128
MAX_CLOCK_BYTES = 32
# One hour. A larger gap between a start and ready marker is a clock
# discontinuity, not a launch, so it is excluded rather than aggregated.
MAX_LATENCY_NS = 3_600_000_000_000

_SOURCE_SHA = re.compile(r"[0-9a-f]{64}\Z")


class LatencyError(ValueError):
    """Invalid caller contract: bad sample type, field or input size."""


@dataclass(frozen=True)
class LaunchSample:
    """One captured launch. Timestamps are monotonic nanoseconds.

    ``start_ns`` is the launch request marker and ``ready_ns`` the first
    window-ready marker. Either may be None when a capture was incomplete.
    ``source`` names the capture channel (for example
    ``measure_qt:CANOPY_CLASSIC_WINDOW_READY``) and ``source_sha256``, when
    supplied, pins the source/binary that produced the markers.
    """
    kind: str
    start_ns: object
    ready_ns: object
    source: str
    clock: str = "monotonic"
    source_sha256: object = None


def _check_contract(samples):
    if type(samples) not in (list, tuple):
        raise LatencyError("samples must be a list or tuple")
    if len(samples) > MAX_SAMPLES:
        raise LatencyError("sample count exceeds bound")
    for sample in samples:
        if not isinstance(sample, LaunchSample):
            raise LatencyError("each sample must be a LaunchSample")
        if sample.kind not in KINDS:
            raise LatencyError("sample kind must be cold or warm")
        if (type(sample.clock) is not str
                or not 1 <= len(sample.clock) <= MAX_CLOCK_BYTES
                or sample.clock not in KNOWN_CLOCKS):
            raise LatencyError("unsupported or oversized clock")
        if (type(sample.source) is not str
                or not 1 <= len(sample.source.encode("utf-8")) <= MAX_SOURCE_BYTES):
            raise LatencyError("invalid or oversized marker source")
        if sample.source_sha256 is not None:
            sha = sample.source_sha256
            if type(sha) is not str or not _SOURCE_SHA.fullmatch(sha):
                raise LatencyError("source_sha256 must be 64 lowercase hex digits")


def _classify(sample):
    """Return ``(latency_ns, reason)``; exactly one entry is non-None."""
    start, ready = sample.start_ns, sample.ready_ns
    if start is None or ready is None:
        return None, "missing_timestamp"
    # bool is an int subclass but is never a valid timestamp.
    if (type(start) is not int or type(ready) is not int
            or start < 0 or ready < 0):
        return None, "invalid_timestamp"
    if ready < start:
        return None, "backward_clock_jump"
    latency = ready - start
    if latency > MAX_LATENCY_NS:
        return None, "forward_clock_jump"
    return latency, None


def _stats(latencies_ns):
    if not latencies_ns:
        return {"count": 0, "min_ms": None, "max_ms": None,
                "mean_ms": None, "median_ms": None}
    return {
        "count": len(latencies_ns),
        "min_ms": round(min(latencies_ns) / 1_000_000, 3),
        "max_ms": round(max(latencies_ns) / 1_000_000, 3),
        "mean_ms": round(sum(latencies_ns) / len(latencies_ns) / 1_000_000, 3),
        "median_ms": round(median(latencies_ns) / 1_000_000, 3),
    }


def summarize(samples):
    """Summarize captured launches. Never mutates ``samples``.

    Returns a JSON-friendly dict. Invalid individual observations are listed
    under ``provenance.excluded`` with a reason instead of skewing the
    aggregates; structural contract violations raise :class:`LatencyError`.
    """
    _check_contract(samples)

    included = {kind: [] for kind in KINDS}
    clocks, sources, shas = set(), set(), set()
    excluded = []

    for sample in samples:
        latency, reason = _classify(sample)
        if reason is not None:
            excluded.append({
                "kind": sample.kind,
                "reason": reason,
                "source": sample.source,
                "clock": sample.clock,
            })
            continue
        included[sample.kind].append(latency)
        clocks.add(sample.clock)
        sources.add(sample.source)
        if sample.source_sha256 is not None:
            shas.add(sample.source_sha256)

    warnings = []
    if "realtime" in clocks:
        warnings.append("wall_clock_timestamps")
    if len(clocks) > 1:
        warnings.append("mixed_clocks")
    for kind in KINDS:
        if not included[kind]:
            warnings.append("no_" + kind + "_samples")

    return {
        "schema": SCHEMA,
        "cold": _stats(included[COLD]),
        "warm": _stats(included[WARM]),
        "provenance": {
            "clocks": sorted(clocks),
            "sources": sorted(sources),
            "source_sha256": sorted(shas),
            "sample_count": len(samples),
            "included_count": sum(len(v) for v in included.values()),
            "excluded_count": len(excluded),
            "excluded": excluded,
            "warnings": warnings,
        },
    }
