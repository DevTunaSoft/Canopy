"""Offline idle-CPU percentage from monotonic, bounded cumulative samples.

Pure computation only. No polling, no background services, no file reads, no
privileged actions, no network or paid dependencies, and bounded memory.

Callers capture cumulative CPU counters elsewhere (for example /proc/stat on
Linux or a performance counter on Windows) and feed snapshots here. The two
snapshots of an interval must be monotonic in time and in each counter. A drop
in a cumulative counter is a reset, not a valid interval.
"""
import math
from collections import deque
from typing import NamedTuple

MAX_SAMPLES = 1024       # bounded history -> bounded memory
MAX_TICKS = 10 ** 15     # reject absurd cumulative counters
MAX_TIME_SECONDS = 10 ** 9  # ~31 years monotonic uptime


class SampleError(ValueError):
    """A sample or sample pair is invalid."""


class CounterResetError(SampleError):
    """A cumulative counter decreased between two samples."""


class ZeroDurationError(SampleError):
    """Two samples share a timestamp, so no interval elapsed."""


class CpuSample(NamedTuple):
    """One cumulative snapshot; total_ticks includes idle_ticks."""
    time_seconds: float
    idle_ticks: int
    total_ticks: int


def _validate(sample):
    if not isinstance(sample, CpuSample):
        raise SampleError("sample must be a CpuSample")
    t = sample.time_seconds
    if isinstance(t, bool) or not isinstance(t, (int, float)):
        raise SampleError("time_seconds must be a real number")
    if not math.isfinite(t) or t < 0.0 or t > MAX_TIME_SECONDS:
        raise SampleError("time_seconds out of bounded range")
    for name in ("idle_ticks", "total_ticks"):
        value = getattr(sample, name)
        if type(value) is not int or value < 0 or value > MAX_TICKS:
            raise SampleError(name + " out of bounded range")
    if sample.idle_ticks > sample.total_ticks:
        raise SampleError("idle_ticks cannot exceed total_ticks")
    return t


def idle_percentage(start, end):
    """Return idle percent between two monotonic cumulative snapshots.

    Result is in [0, 100]. Raises CounterResetError if a counter drops,
    ZeroDurationError if no time elapsed, and SampleError for other bad input.
    """
    _validate(start)
    _validate(end)
    if end.time_seconds < start.time_seconds:
        raise SampleError("sample time is not monotonic")
    if end.time_seconds == start.time_seconds:
        raise ZeroDurationError("zero duration between samples")
    if (end.idle_ticks < start.idle_ticks
            or end.total_ticks < start.total_ticks):
        raise CounterResetError("cumulative counter decreased")
    delta_total = end.total_ticks - start.total_ticks
    if delta_total == 0:
        raise SampleError("total_ticks did not advance")
    delta_idle = end.idle_ticks - start.idle_ticks
    # Monotonic inputs guarantee 0 <= delta_idle <= delta_total.
    return 100.0 * delta_idle / delta_total


class CpuIdleSamples:
    """Bounded rolling window of monotonic cumulative samples."""

    def __init__(self, max_samples=MAX_SAMPLES):
        if type(max_samples) is not int or not 2 <= max_samples <= MAX_SAMPLES:
            raise SampleError("max_samples must be between 2 and MAX_SAMPLES")
        self._samples = deque(maxlen=max_samples)

    def __len__(self):
        return len(self._samples)

    def add(self, sample):
        """Validate and append a sample, enforcing monotonic time and counters."""
        _validate(sample)
        if self._samples:
            last = self._samples[-1]
            if sample.time_seconds < last.time_seconds:
                raise SampleError("sample time is not monotonic")
            if (sample.idle_ticks < last.idle_ticks
                    or sample.total_ticks < last.total_ticks):
                raise CounterResetError("cumulative counter decreased")
        self._samples.append(sample)

    def reset(self):
        """Drop history after a counter reset starts a new counter epoch."""
        self._samples.clear()

    def latest_idle_percentage(self):
        """Idle percent for the two latest samples; needs at least two."""
        if len(self._samples) < 2:
            raise SampleError("at least two samples are required")
        return idle_percentage(self._samples[-2], self._samples[-1])
