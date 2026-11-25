"""Offline parser for Linux ``/proc`` proportional set size evidence.

Consumes already-collected ``/proc/<pid>/smaps_rollup`` or
``/proc/<pid>/smaps`` text. A missing, malformed, ambiguous or vanished
observation is reported as a status with ``pss_kib=None``. The module never
substitutes zero, a previous value or any other estimate.

Reads are bounded and single-shot. There is no polling, background service,
privileged action, network access or process launch.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re

MAX_SMAPS_BYTES = 2 * 1024 * 1024
MAX_PSS_KIB = (1 << 63) - 1

OK = "ok"
MISSING = "missing"
MALFORMED = "malformed"
CONFLICT = "conflict"
PROCESS_GONE = "process_gone"
UNREADABLE = "unreadable"

_PSS_LINE = re.compile(r"Pss:\s+(\d+)\s+kB\s*\Z")
_VALID_PID = re.compile(r"[1-9]\d*\Z")

__all__ = [
    "MAX_SMAPS_BYTES", "MAX_PSS_KIB",
    "OK", "MISSING", "MALFORMED", "CONFLICT", "PROCESS_GONE", "UNREADABLE",
    "PssSample", "parse_rollup_pss", "parse_smaps_pss", "read_snapshot",
]


@dataclass(frozen=True)
class PssSample:
    """One measured PSS observation, or the reason no value is available."""

    status: str
    pss_kib: Optional[int] = None
    sample_count: int = 0
    reason: str = ""
    source: str = ""

    @property
    def is_measured(self):
        return self.status == OK and self.pss_kib is not None


def _pss_values(text):
    """Return (measured_values, malformed_lines); no value is invented."""
    values = []
    bad = []
    for line in text.splitlines():
        if not line.startswith("Pss:"):
            continue
        match = _PSS_LINE.fullmatch(line)
        if match is None:
            bad.append(line)
            continue
        value = int(match.group(1))
        if value > MAX_PSS_KIB:
            bad.append(line)
            continue
        values.append(value)
    return values, bad


def _bounded_text(text, source):
    if not isinstance(text, str):
        return PssSample(MALFORMED, reason="evidence must be text", source=source)
    if len(text) > MAX_SMAPS_BYTES:
        return PssSample(MALFORMED, reason="evidence exceeds byte bound", source=source)
    return None


def parse_rollup_pss(text, *, source=""):
    """Parse the single ``Pss:`` total from ``smaps_rollup`` text.

    Absent, malformed, overflowing or duplicate totals yield a non-OK sample
    with ``pss_kib=None``. No total is inferred from Rss or other fields.
    """
    invalid = _bounded_text(text, source)
    if invalid is not None:
        return invalid
    values, bad = _pss_values(text)
    if bad:
        return PssSample(MALFORMED, reason="malformed Pss total", source=source)
    if not values:
        return PssSample(MISSING, reason="no Pss total present", source=source)
    if len(values) != 1:
        return PssSample(CONFLICT, reason="multiple Pss totals",
                         sample_count=len(values), source=source)
    return PssSample(OK, pss_kib=values[0], sample_count=1, source=source)


def parse_smaps_pss(text, *, source=""):
    """Sum the ``Pss:`` values present in full ``smaps`` text.

    Only lines the kernel actually supplied are added. One malformed value
    rejects the whole total rather than being skipped or estimated.
    """
    invalid = _bounded_text(text, source)
    if invalid is not None:
        return invalid
    values, bad = _pss_values(text)
    if bad:
        return PssSample(MALFORMED, reason="malformed Pss mapping value", source=source)
    if not values:
        return PssSample(MISSING, reason="no Pss mapping values present", source=source)
    total = 0
    for value in values:
        total += value
        if total > MAX_PSS_KIB:
            return PssSample(MALFORMED, reason="Pss sum overflow", source=source)
    return PssSample(OK, pss_kib=total, sample_count=len(values), source=source)


def _pid_text(pid):
    if isinstance(pid, bool):
        raise ValueError("invalid pid")
    if isinstance(pid, int) and pid > 0:
        return str(pid)
    if isinstance(pid, str) and _VALID_PID.fullmatch(pid):
        return pid
    raise ValueError("invalid pid")


def read_snapshot(pid, *, proc_root="/proc", rollup=True):
    """Read one bounded PSS snapshot for ``pid`` under ``proc_root``.

    ``proc_root`` may point at a synthetic tree in offline tests. A process
    that vanished or has no such file yields ``PROCESS_GONE``; an access or
    I/O failure yields ``UNREADABLE``. Neither produces a value.
    """
    name = "smaps_rollup" if rollup else "smaps"
    path = Path(proc_root) / _pid_text(pid) / name
    source = str(path)
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_SMAPS_BYTES + 1)
    except (FileNotFoundError, ProcessLookupError, NotADirectoryError):
        return PssSample(PROCESS_GONE, source=source)
    except OSError as exc:
        return PssSample(UNREADABLE, reason=type(exc).__name__, source=source)
    if len(data) > MAX_SMAPS_BYTES:
        return PssSample(MALFORMED, reason="evidence file exceeds byte bound", source=source)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return PssSample(MALFORMED, reason="evidence not UTF-8", source=source)
    parser = parse_rollup_pss if rollup else parse_smaps_pss
    return parser(text, source=source)
