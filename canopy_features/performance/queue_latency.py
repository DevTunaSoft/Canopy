"""Offline analyzer for bounded event-queue latency evidence.

Consumes an in-memory trace of enqueue/dequeue observations from a bounded
shell event queue. Pure, deterministic computation: no Qt, OS event capture,
polling, threads, network, privileged calls or file I/O. Input size and every
numeric field are hard-bounded, and the report keeps only scalar metrics, so
analysis never retains the trace.

A sample is a dict with exactly four fields:
  sequence    int, unique event sequence number
  enqueued_ns int, monotonic enqueue timestamp in nanoseconds
  dequeued_ns int, monotonic dequeue timestamp in nanoseconds
  depth       int, queue depth at enqueue (must not exceed capacity)

Trace order need not follow timestamp order. The analyzer sorts by
(enqueued_ns, sequence) before computing the latency distribution and reports
how many input steps ran backwards in enqueue time.
"""
from dataclasses import dataclass

SCHEMA_VERSION = 1
MAX_SAMPLES = 4096
MAX_TIMESTAMP_NS = 10**18
MAX_LATENCY_NS = 10**15
MAX_SEQUENCE = 10**13
REQUIRED_FIELDS = frozenset({"sequence", "enqueued_ns", "dequeued_ns", "depth"})


class LatencyEvidenceError(ValueError):
    """Invalid, unbounded or impossible queue latency evidence."""


@dataclass(frozen=True)
class LatencyReport:
    schema: int
    capacity: int
    status: str
    sample_count: int
    out_of_order_steps: int
    min_ns: int
    max_ns: int
    mean_ns: float
    median_ns: int
    p95_ns: int
    p99_ns: int
    peak_depth: int
    saturated_samples: int


def _bounded_int(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise LatencyEvidenceError("invalid bounded value for " + name)
    return value


def _nearest_rank(sorted_values, percent):
    """Return nearest-rank percentile; integer math avoids interpolation drift."""
    rank = -(-percent * len(sorted_values) // 100)
    return sorted_values[max(0, rank - 1)]


def analyze(trace, *, capacity, budget_ns=None):
    """Validate a bounded trace and return its latency distribution.

    status is NO_DATA for an empty trace, PASS/FAIL against an optional
    p99 budget, or MEASURED when no budget is supplied. A MEASURED result is
    not a performance pass and implies no Mint, Qt or visual acceptance.
    """
    capacity = _bounded_int(capacity, "capacity", 1, MAX_SAMPLES)
    if budget_ns is not None:
        _bounded_int(budget_ns, "budget_ns", 1, MAX_LATENCY_NS)
    if type(trace) not in (list, tuple):
        raise LatencyEvidenceError("trace must be a list or tuple")
    if len(trace) > MAX_SAMPLES:
        raise LatencyEvidenceError("trace exceeds sample bound")

    records = []
    sequences = set()
    out_of_order_steps = 0
    previous_enqueued = None
    for sample in trace:
        if type(sample) is not dict or set(sample) != REQUIRED_FIELDS:
            raise LatencyEvidenceError("sample must contain exactly four fields")
        sequence = _bounded_int(sample["sequence"], "sequence", 0, MAX_SEQUENCE)
        enqueued = _bounded_int(sample["enqueued_ns"], "enqueued_ns",
                                0, MAX_TIMESTAMP_NS)
        dequeued = _bounded_int(sample["dequeued_ns"], "dequeued_ns",
                                0, MAX_TIMESTAMP_NS)
        depth = _bounded_int(sample["depth"], "depth", 0, capacity)
        latency = dequeued - enqueued
        if latency < 0 or latency > MAX_LATENCY_NS:
            raise LatencyEvidenceError("impossible or unbounded queue latency")
        if sequence in sequences:
            raise LatencyEvidenceError("duplicate event sequence")
        sequences.add(sequence)
        if previous_enqueued is not None and enqueued < previous_enqueued:
            out_of_order_steps += 1
        previous_enqueued = enqueued
        records.append((enqueued, sequence, latency, depth))

    if not records:
        return LatencyReport(SCHEMA_VERSION, capacity, "NO_DATA", 0,
                             out_of_order_steps, 0, 0, 0.0, 0, 0, 0, 0, 0)

    records.sort(key=lambda row: (row[0], row[1]))
    latencies = sorted(row[2] for row in records)
    p99 = _nearest_rank(latencies, 99)
    status = "MEASURED"
    if budget_ns is not None:
        status = "PASS" if p99 <= budget_ns else "FAIL"
    return LatencyReport(
        schema=SCHEMA_VERSION,
        capacity=capacity,
        status=status,
        sample_count=len(records),
        out_of_order_steps=out_of_order_steps,
        min_ns=latencies[0],
        max_ns=latencies[-1],
        mean_ns=round(sum(latencies) / len(latencies), 3),
        median_ns=_nearest_rank(latencies, 50),
        p95_ns=_nearest_rank(latencies, 95),
        p99_ns=p99,
        peak_depth=max(row[3] for row in records),
        saturated_samples=sum(1 for row in records if row[3] == capacity),
    )
