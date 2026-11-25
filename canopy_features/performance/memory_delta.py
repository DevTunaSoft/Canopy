"""Report memory growth across repeated app interactions from real samples.

The caller supplies real memory readings captured at interaction points (for
example /proc/<pid>/statm RSS on Linux or GetProcessMemoryInfo on Windows).
This module never samples memory, never polls, starts no services and invents
no numbers: it validates and summarizes only the readings it is given.

Growth is the signed difference between the last and the first reading.
Negative growth (memory released) is reported as-is, never clamped to zero.
Sample consumption is bounded, so an unbounded iterator cannot exhaust memory.
"""
from dataclasses import dataclass
from itertools import islice

MAX_SAMPLES = 1024
MAX_INTERACTION = 1_000_000
MAX_MEMORY_KIB = 2 ** 31 - 1  # sanity ceiling for a 32-bit KiB reading


class SampleError(ValueError):
    """Raised for missing, invalid or unbounded memory samples."""


@dataclass(frozen=True)
class MemorySample:
    """One real memory reading at a numbered interaction, in KiB."""
    interaction: int
    memory_kib: int


def _validate_sample(sample):
    if not isinstance(sample, MemorySample):
        raise SampleError("sample must be a MemorySample")
    if (type(sample.interaction) is not int
            or not 0 <= sample.interaction <= MAX_INTERACTION):
        raise SampleError("interaction index out of bounded range")
    if (type(sample.memory_kib) is not int
            or not 0 <= sample.memory_kib <= MAX_MEMORY_KIB):
        raise SampleError("memory_kib out of bounded range")
    return sample


def _percent(delta_kib, start_kib):
    if start_kib == 0:
        return None
    return round(100.0 * delta_kib / start_kib, 4)


def delta(start, end):
    """Signed growth between two real endpoint samples.

    A missing start or end sample is an error; growth is never guessed.
    """
    if start is None:
        raise SampleError("missing start sample")
    if end is None:
        raise SampleError("missing end sample")
    _validate_sample(start)
    _validate_sample(end)
    if end.interaction < start.interaction:
        raise SampleError("end interaction precedes start interaction")
    change = end.memory_kib - start.memory_kib
    return {
        "start_kib": start.memory_kib,
        "end_kib": end.memory_kib,
        "delta_kib": change,
        "delta_percent": _percent(change, start.memory_kib),
        "interactions": end.interaction - start.interaction,
    }


def report_growth(samples, *, max_samples=MAX_SAMPLES):
    """Summarize growth from a bounded sequence of real interaction samples."""
    if type(max_samples) is not int or not 2 <= max_samples <= MAX_SAMPLES:
        raise SampleError("max_samples out of bounded range")
    if samples is None:
        raise SampleError("missing start and end samples: no samples")
    try:
        buffered = list(islice(samples, max_samples + 1))
    except TypeError as exc:
        raise SampleError("samples must be an iterable of MemorySample") from exc
    if not buffered:
        raise SampleError("missing start and end samples: no samples")
    if len(buffered) > max_samples:
        raise SampleError("sample count exceeds bound")
    for sample in buffered:
        _validate_sample(sample)
    if len(buffered) < 2:
        raise SampleError("missing end sample: need a start and an end reading")
    result = delta(buffered[0], buffered[-1])
    readings = [sample.memory_kib for sample in buffered]
    span = result["interactions"]
    result["sample_count"] = len(buffered)
    result["peak_kib"] = max(readings)
    result["min_kib"] = min(readings)
    result["mean_growth_per_interaction_kib"] = (
        round(result["delta_kib"] / span, 4) if span else result["delta_kib"]
    )
    result["status"] = "ok"
    return result
