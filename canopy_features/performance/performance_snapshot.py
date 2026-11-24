"""Bounded, read-only composition of offline performance evidence.

This module combines the outputs of four already-tested, pure offline parsers
(``frame_pacing``, ``memory_delta``, ``launch_latency`` and ``pss_samples``)
into one deterministic, immutable record suitable for a diagnostic or CI
evidence artifact.

It never measures anything: no clock reads, no sampling, no /proc reads, no
process launch, no sockets, no threads, no polling and no visual-code imports.
Callers pass the parser outputs they already computed. The record carries
explicit negative claims so a snapshot can never be mistaken for proof of real
hardware measurement, Linux Mint acceptance or owner visual approval.

Every projected field is validated and copied into a fixed, allowlisted schema:
caller-supplied keys cannot become output fields, and no live alias to a caller
container is retained. Invalid or oversized evidence fails closed with
:class:`SnapshotError`.
"""
from dataclasses import asdict, dataclass
import math
from types import MappingProxyType

from canopy_features.performance.frame_pacing import (
    FramePacingReport, MEASUREMENT_SOURCE,
)
from canopy_features.performance.launch_latency import SCHEMA as LAUNCH_SCHEMA

SCHEMA = 1
EVIDENCE_KINDS = ("frame_pacing", "memory_growth", "launch_latency", "pss")

MAX_PROVENANCE_VALUES = 128
MAX_EXCLUDED = 256
MAX_PSS_KIB = 2 ** 31 - 1
MAX_DELTA_KIB = 2 ** 31 - 1

NOT_ESTABLISHED = "NOT_ESTABLISHED"
MEMORY_STATUSES = frozenset({"ok"})

MEMORY_INT_KEYS = (
    "start_kib", "end_kib", "delta_kib", "interactions", "sample_count",
    "peak_kib", "min_kib",
)
MEMORY_FLOAT_KEYS = ("delta_percent", "mean_growth_per_interaction_kib")
MEMORY_ALL_KEYS = MEMORY_INT_KEYS + MEMORY_FLOAT_KEYS + ("status",)

LAUNCH_TOP_KEYS = ("schema", "cold", "warm", "provenance")
LAUNCH_STAT_KEYS = ("count", "min_ms", "max_ms", "mean_ms", "median_ms")
LAUNCH_PROV_INT_KEYS = ("sample_count", "included_count", "excluded_count")
LAUNCH_PROV_LIST_KEYS = ("clocks", "sources", "source_sha256", "warnings")
LAUNCH_EXCLUDED_KEYS = ("kind", "reason", "source", "clock")
LAUNCH_PROV_KEYS = LAUNCH_PROV_INT_KEYS + LAUNCH_PROV_LIST_KEYS + ("excluded",)


class SnapshotError(ValueError):
    """Invalid, unbounded or structurally unsafe evidence input."""


def _int(value, label, *, minimum=None, maximum=None):
    if type(value) is not int:
        raise SnapshotError(label + " must be an integer")
    if minimum is not None and value < minimum:
        raise SnapshotError(label + " is below its bound")
    if maximum is not None and value > maximum:
        raise SnapshotError(label + " exceeds its bound")
    return value


def _float_or_none(value, label):
    if value is None:
        return None
    if type(value) is not float or not math.isfinite(value):
        raise SnapshotError(label + " must be a finite float or None")
    return value


def _number_or_none(value, label):
    """Accept a finite number or None, rejecting bool and unbounded ints.

    ``memory_delta`` emits a float for most derived fields but an int for the
    mean when the interaction span is zero; both are valid outputs of the
    already-tested parser and must survive projection unchanged.
    """
    if value is None:
        return None
    if type(value) is float:
        if not math.isfinite(value):
            raise SnapshotError(label + " must be a finite number or None")
        return value
    if type(value) is int:
        if not -MAX_DELTA_KIB <= value <= MAX_DELTA_KIB:
            raise SnapshotError(label + " exceeds its bound")
        return value
    raise SnapshotError(label + " must be a finite number or None")


def _text_tuple(values, label, cap):
    if type(values) not in (list, tuple):
        raise SnapshotError(label + " must be a list or tuple")
    if len(values) > cap:
        raise SnapshotError(label + " exceeds its bound")
    for item in values:
        if type(item) is not str:
            raise SnapshotError(label + " entries must be strings")
    return tuple(values)


def _require_dict(value, label):
    if not isinstance(value, dict):
        raise SnapshotError(label + " must be a mapping")
    return value


def _project_memory(value):
    source = _require_dict(value, "memory growth evidence")
    for key in MEMORY_ALL_KEYS:
        if key not in source:
            raise SnapshotError("incomplete memory growth evidence: " + key)
    projected = {}
    for key in MEMORY_INT_KEYS:
        if key == "delta_kib":
            # Signed by design: memory_delta reports released memory as-is.
            projected[key] = _int(
                source[key], "memory " + key,
                minimum=-MAX_DELTA_KIB, maximum=MAX_DELTA_KIB)
        else:
            projected[key] = _int(source[key], "memory " + key, minimum=0)
    for key in MEMORY_FLOAT_KEYS:
        projected[key] = _number_or_none(source[key], "memory " + key)
    status = source["status"]
    if type(status) is not str or status not in MEMORY_STATUSES:
        raise SnapshotError("unsupported memory growth status")
    projected["status"] = status
    return MappingProxyType(projected)


def _project_stat(value, label):
    source = _require_dict(value, label)
    projected = {}
    for key in LAUNCH_STAT_KEYS:
        if key not in source:
            raise SnapshotError("incomplete " + label + ": " + key)
    projected["count"] = _int(source["count"], label + " count", minimum=0)
    for key in ("min_ms", "max_ms", "mean_ms", "median_ms"):
        projected[key] = _float_or_none(source[key], label + " " + key)
    return MappingProxyType(projected)


def _project_excluded(values):
    if type(values) not in (list, tuple):
        raise SnapshotError("excluded evidence must be a list or tuple")
    if len(values) > MAX_EXCLUDED:
        raise SnapshotError("excluded evidence exceeds its bound")
    projected = []
    for item in values:
        entry = _require_dict(item, "excluded evidence entry")
        record = {}
        for key in LAUNCH_EXCLUDED_KEYS:
            if key not in entry or type(entry[key]) is not str:
                raise SnapshotError("malformed excluded evidence entry")
            record[key] = entry[key]
        projected.append(MappingProxyType(record))
    return tuple(projected)


def _project_provenance(value):
    source = _require_dict(value, "launch provenance")
    for key in LAUNCH_PROV_KEYS:
        if key not in source:
            raise SnapshotError("incomplete launch provenance: " + key)
    projected = {}
    for key in LAUNCH_PROV_INT_KEYS:
        projected[key] = _int(source[key], "provenance " + key, minimum=0)
    for key in LAUNCH_PROV_LIST_KEYS:
        projected[key] = _text_tuple(source[key], "provenance " + key,
                                     MAX_PROVENANCE_VALUES)
    projected["excluded"] = _project_excluded(source["excluded"])
    return MappingProxyType(projected)


def _project_launch(value):
    source = _require_dict(value, "launch latency evidence")
    for key in LAUNCH_TOP_KEYS:
        if key not in source:
            raise SnapshotError("incomplete launch latency evidence: " + key)
    if _int(source["schema"], "launch schema") != LAUNCH_SCHEMA:
        raise SnapshotError("unsupported launch evidence schema")
    projected = {
        "schema": LAUNCH_SCHEMA,
        "cold": _project_stat(source["cold"], "cold stats"),
        "warm": _project_stat(source["warm"], "warm stats"),
        "provenance": _project_provenance(source["provenance"]),
    }
    return MappingProxyType(projected)


def _project_frame(value):
    """Validate the embedded report's measurement claims and flags.

    ``FramePacingReport`` is a frozen dataclass whose constructor does not
    validate, so a caller can bypass ``parse_frame_times`` and supply a report
    claiming a real GPU capture. The snapshot's negative claims are absolute;
    embedded evidence that asserts the opposite is a contradictory
    passing/failing flag pair and a false performance-safe claim. Re-derive
    the two claim fields from the caller's real report rather than trusting
    an overridable ``as_dict()`` method, and fail closed on disagreement.
    """
    if not isinstance(value, FramePacingReport):
        raise SnapshotError("frame pacing evidence must be a FramePacingReport")
    try:
        claim = value.real_gpu_measurement
        source = value.measurement_source
    except (AttributeError, TypeError) as exc:
        raise SnapshotError("frame pacing evidence is structurally unsafe") from exc
    if claim is not False:
        raise SnapshotError("frame pacing real-measurement flag contradicts snapshot")
    if type(source) is not str or source != MEASUREMENT_SOURCE:
        raise SnapshotError("frame pacing source label contradicts offline snapshot")
    # Freeze the validated projection now: as_dict() must never call back into
    # a caller-overridable method or re-read a field that could change.
    return MappingProxyType(asdict(value))


def _thaw(value):
    """Return a fresh JSON-friendly copy with no live alias to the record."""
    if isinstance(value, MappingProxyType):
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class PerformanceSnapshot:
    """One frozen, deterministic record of offline performance evidence."""

    schema: int
    evidence_kinds: tuple
    evidence_count: int
    frame_pacing: object
    frame_pacing_view: object
    memory_growth: object
    launch_latency: object
    pss_kib: object
    measurement_performed: bool
    real_hardware_measured: bool
    linux_mint_acceptance: str
    owner_visual_approval: str

    def as_dict(self):
        """Return a fresh, JSON-serializable copy of this record."""
        return {
            "schema": self.schema,
            "evidence_kinds": list(self.evidence_kinds),
            "evidence_count": self.evidence_count,
            "frame_pacing": _thaw(self.frame_pacing_view),
            "memory_growth": _thaw(self.memory_growth),
            "launch_latency": _thaw(self.launch_latency),
            "pss_kib": self.pss_kib,
            "measurement_performed": self.measurement_performed,
            "real_hardware_measured": self.real_hardware_measured,
            "linux_mint_acceptance": self.linux_mint_acceptance,
            "owner_visual_approval": self.owner_visual_approval,
        }


def compose_snapshot(*, frame_pacing=None, memory_growth=None,
                     launch_latency=None, pss_kib=None):
    """Compose already-computed parser outputs into one frozen record.

    Each keyword is optional; omitted evidence is recorded as ``None``. The
    negative-claim fields are hardcoded and cannot be supplied by the caller.
    """
    frame = None if frame_pacing is None else _project_frame(frame_pacing)
    if pss_kib is not None:
        _int(pss_kib, "pss_kib", minimum=0, maximum=MAX_PSS_KIB)
    memory = None if memory_growth is None else _project_memory(memory_growth)
    launch = None if launch_latency is None else _project_launch(launch_latency)
    evidence = (frame_pacing, memory, launch, pss_kib)
    return PerformanceSnapshot(
        schema=SCHEMA,
        evidence_kinds=EVIDENCE_KINDS,
        evidence_count=sum(item is not None for item in evidence),
        frame_pacing=frame_pacing,
        frame_pacing_view=frame,
        memory_growth=memory,
        launch_latency=launch,
        pss_kib=pss_kib,
        measurement_performed=False,
        real_hardware_measured=False,
        linux_mint_acceptance=NOT_ESTABLISHED,
        owner_visual_approval=NOT_ESTABLISHED,
    )
