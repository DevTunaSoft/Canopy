"""Offline, bounded parser for frame-time distributions.

This module does not measure anything. It parses frame-time samples supplied
by a caller and summarizes the distribution. It never opens sockets, starts
threads, polls, reads GPU state, or launches processes. A backend value is a
label from the caller, not proof that a real GPU was measured. Every report is
a diagnostic aid, not a smoothness, release, or Mint-acceptance approval.
"""
from dataclasses import asdict, dataclass
import math

MAX_SAMPLES = 10_000
MAX_FRAME_MS = 10_000.0
MIN_REFRESH_HZ = 1
MAX_REFRESH_HZ = 240
KNOWN_BACKENDS = frozenset({"software", "opengl", "vulkan", "default"})
MEASUREMENT_SOURCE = "caller-supplied-frame-times-offline-parse"


class FramePacingError(ValueError):
    """Invalid, unbounded, or unsupported frame-time input."""


@dataclass(frozen=True)
class FramePacingReport:
    """Bounded summary of one caller-supplied frame-time distribution."""

    backend: str
    backend_known: bool
    refresh_hz: int
    frame_budget_ms: float
    samples_total: int
    samples_valid: int
    samples_dropped: int
    dropped_frames: int
    dropped_frame_rate: float
    min_ms: float
    max_ms: float
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    measurement_source: str
    real_gpu_measurement: bool

    def as_dict(self):
        """Return a JSON-serializable copy of this report."""
        return asdict(self)


def _usable(value):
    """Return True only for a finite, positive, physically plausible sample."""
    if type(value) not in (int, float):
        return False
    return 0.0 < value <= MAX_FRAME_MS and math.isfinite(value)


def _percentile(sorted_values, fraction):
    """Nearest-rank percentile; deterministic for a sorted sample sequence."""
    rank = math.ceil(fraction * len(sorted_values))
    rank = max(1, min(rank, len(sorted_values)))
    return sorted_values[rank - 1]


def parse_frame_times(samples, *, refresh_hz=60, backend="default"):
    """Summarize frame times in milliseconds without claiming GPU measurement.

    Invalid observations are counted as ``samples_dropped`` and excluded.
    Valid observations slower than one refresh budget are ``dropped_frames``.
    """
    if type(backend) is not str:
        raise FramePacingError("backend label must be a string")
    if (type(refresh_hz) is not int
            or not MIN_REFRESH_HZ <= refresh_hz <= MAX_REFRESH_HZ):
        raise FramePacingError("unsupported refresh rate")
    if type(samples) not in (list, tuple):
        raise FramePacingError("frame times must be a bounded list or tuple")
    if len(samples) > MAX_SAMPLES:
        raise FramePacingError("frame-time sample count exceeds bound")

    valid = [float(value) for value in samples if _usable(value)]
    if not valid:
        raise FramePacingError("no valid frame-time samples")

    dropped = len(samples) - len(valid)
    ordered = sorted(valid)
    budget = 1000.0 / refresh_hz
    slow = sum(1 for value in valid if value > budget)

    return FramePacingReport(
        backend=backend,
        backend_known=backend in KNOWN_BACKENDS,
        refresh_hz=refresh_hz,
        frame_budget_ms=round(budget, 4),
        samples_total=len(samples),
        samples_valid=len(valid),
        samples_dropped=dropped,
        dropped_frames=slow,
        dropped_frame_rate=round(slow / len(valid), 4),
        min_ms=round(ordered[0], 4),
        max_ms=round(ordered[-1], 4),
        mean_ms=round(sum(ordered) / len(ordered), 4),
        p50_ms=round(_percentile(ordered, 0.50), 4),
        p95_ms=round(_percentile(ordered, 0.95), 4),
        p99_ms=round(_percentile(ordered, 0.99), 4),
        measurement_source=MEASUREMENT_SOURCE,
        real_gpu_measurement=False,
    )
