#!/usr/bin/env python3
"""Bounded OFFLINE validator for performance snapshot JSON artifacts.

A "snapshot artifact" is the JSON-serializable record produced by
``PerformanceSnapshot.as_dict()`` (``canopy_features/performance``). This
module validates such a record *structurally* and refuses to accept anything
that could be mistaken for a stronger claim than the artifact itself makes.

It is deliberately self-contained: it does not import the snapshot producer
(or any Qt/visual/measurement code), so it can run in an offline CI gate on
any checkout. Validation is fail-closed: a malformed, schema-drifted,
oversized or claim-flipped artifact raises :class:`ArtifactError` with a fixed
message. No caller value, key or file content is ever echoed into an error or
into the returned report.

This validator NEVER grants a release, Mint, hardware or visual approval. Its
report hardcodes the same negative claims as the producer. It reads no
clocks, /proc state, sockets, processes or threads; a file read is bounded and
symlink-safe.
"""
import argparse
import ast
import json
import math
import os
from pathlib import Path
import stat
import sys

SCHEMA = 1
EVIDENCE_KINDS = ("frame_pacing", "memory_growth", "launch_latency", "pss")
NOT_ESTABLISHED = "NOT_ESTABLISHED"
MEMORY_STATUSES = frozenset({"ok"})

MAX_ARTIFACT_BYTES = 65_536
MAX_EVIDENCE_KINDS = 4
MAX_TEXT = 256
MAX_BACKEND = 128
MAX_SAMPLES = 10_000
MAX_FRAME_MS = 10_000.0
MAX_PSS_KIB = 2 ** 31 - 1
MAX_DELTA_KIB = 2 ** 31 - 1
MAX_PROVENANCE_VALUES = 128
MAX_EXCLUDED = 256

TOP_KEYS = frozenset({
    "schema", "evidence_kinds", "evidence_count", "frame_pacing",
    "memory_growth", "launch_latency", "pss_kib", "measurement_performed",
    "real_hardware_measured", "linux_mint_acceptance",
    "owner_visual_approval",
})
FRAME_KEYS = frozenset({
    "backend", "backend_known", "refresh_hz", "frame_budget_ms",
    "samples_total", "samples_valid", "samples_dropped", "dropped_frames",
    "dropped_frame_rate", "min_ms", "max_ms", "mean_ms", "p50_ms", "p95_ms",
    "p99_ms", "measurement_source", "real_gpu_measurement",
})
MEMORY_KEYS = frozenset({
    "start_kib", "end_kib", "delta_kib", "interactions", "sample_count",
    "peak_kib", "min_kib", "delta_percent",
    "mean_growth_per_interaction_kib", "status",
})
LAUNCH_KEYS = frozenset({"schema", "cold", "warm", "provenance"})
STAT_KEYS = frozenset({"count", "min_ms", "max_ms", "mean_ms", "median_ms"})
PROV_KEYS = frozenset({
    "sample_count", "included_count", "excluded_count", "clocks", "sources",
    "source_sha256", "warnings", "excluded",
})
EXCLUDED_KEYS = frozenset({"kind", "reason", "source", "clock"})


class ArtifactError(ValueError):
    """Invalid, drifted, unbounded or claim-flipped snapshot artifact."""


def _int(value, minimum=None, maximum=None):
    if type(value) is not int:
        raise ArtifactError("artifact integer field has wrong type")
    if minimum is not None and value < minimum:
        raise ArtifactError("artifact integer field is below its bound")
    if maximum is not None and value > maximum:
        raise ArtifactError("artifact integer field exceeds its bound")
    return value


def _number(value):
    """Finite float or bounded non-bool int (both are valid parser outputs)."""
    if type(value) is float:
        if not math.isfinite(value):
            raise ArtifactError("artifact numeric field is not finite")
        return value
    if type(value) is int:
        if not -MAX_DELTA_KIB <= value <= MAX_DELTA_KIB:
            raise ArtifactError("artifact numeric field exceeds its bound")
        return value
    raise ArtifactError("artifact numeric field has wrong type")


def _float_or_none(value):
    if value is None:
        return None
    if type(value) is not float or not math.isfinite(value):
        raise ArtifactError("artifact float field must be finite or null")
    return value


def _text(value, cap=MAX_TEXT):
    if type(value) is not str or not 0 <= len(value) <= cap:
        raise ArtifactError("artifact text field is invalid")
    return value


def _text_list(value, cap=MAX_PROVENANCE_VALUES):
    if type(value) is not list or len(value) > cap:
        raise ArtifactError("artifact text list is invalid or unbounded")
    for item in value:
        _text(item)
    return value


def _exact_dict(value, keys):
    if type(value) is not dict or frozenset(value) != keys:
        raise ArtifactError("artifact mapping has an unexpected key set")
    return value


def _bool(value):
    if type(value) is not bool:
        raise ArtifactError("artifact boolean field has wrong type")
    return value


def _validate_frame(value):
    s = _exact_dict(value, FRAME_KEYS)
    _text(s["backend"], MAX_BACKEND)
    _bool(s["backend_known"])
    _int(s["refresh_hz"], 1, 240)
    frame_budget = _float_or_none(s["frame_budget_ms"])
    if frame_budget is None or not 0 < frame_budget <= 1000.0:
        raise ArtifactError("artifact frame budget is out of range")
    for key in ("samples_total", "samples_valid", "samples_dropped",
                "dropped_frames"):
        _int(s[key], 0, MAX_SAMPLES)
    if s["samples_valid"] + s["samples_dropped"] != s["samples_total"]:
        raise ArtifactError("artifact frame sample counts are inconsistent")
    rate = _float_or_none(s["dropped_frame_rate"])
    if rate is None or not 0.0 <= rate <= 1.0:
        raise ArtifactError("artifact dropped frame rate is out of range")
    times = {}
    for key in ("min_ms", "max_ms", "mean_ms", "p50_ms", "p95_ms", "p99_ms"):
        val = _float_or_none(s[key])
        if val is None or not 0 < val <= MAX_FRAME_MS:
            raise ArtifactError("artifact frame time is out of range")
        times[key] = val
    if not (times["min_ms"] <= times["p50_ms"] <= times["p95_ms"]
            <= times["p99_ms"] <= times["max_ms"]):
        raise ArtifactError("artifact frame percentiles are unordered")
    _text(s["measurement_source"], MAX_BACKEND)
    # The offline parser always emits this as a hardcoded negative claim.
    if _bool(s["real_gpu_measurement"]) is not False:
        raise ArtifactError("artifact claims real GPU measurement")


def _validate_memory(value):
    s = _exact_dict(value, MEMORY_KEYS)
    for key in ("start_kib", "end_kib", "interactions", "sample_count",
                "peak_kib", "min_kib"):
        _int(s[key], 0)
    _int(s["delta_kib"], -MAX_DELTA_KIB, MAX_DELTA_KIB)
    _number(s["delta_percent"])
    _number(s["mean_growth_per_interaction_kib"])
    if type(s["status"]) is not str or s["status"] not in MEMORY_STATUSES:
        raise ArtifactError("artifact memory status is unsupported")


def _validate_stat(value):
    s = _exact_dict(value, STAT_KEYS)
    _int(s["count"], 0)
    for key in ("min_ms", "max_ms", "mean_ms", "median_ms"):
        _float_or_none(s[key])


def _validate_excluded(value):
    if type(value) is not list or len(value) > MAX_EXCLUDED:
        raise ArtifactError("artifact excluded evidence is unbounded")
    for entry in value:
        s = _exact_dict(entry, EXCLUDED_KEYS)
        for key in EXCLUDED_KEYS:
            _text(s[key])


def _validate_provenance(value):
    s = _exact_dict(value, PROV_KEYS)
    for key in ("sample_count", "included_count", "excluded_count"):
        _int(s[key], 0)
    for key in ("clocks", "sources", "source_sha256", "warnings"):
        _text_list(s[key])
    _validate_excluded(s["excluded"])


def _validate_launch(value):
    s = _exact_dict(value, LAUNCH_KEYS)
    if _int(s["schema"]) != SCHEMA:
        raise ArtifactError("artifact launch evidence schema is unsupported")
    _validate_stat(s["cold"])
    _validate_stat(s["warm"])
    _validate_provenance(s["provenance"])


def validate(value):
    """Validate a parsed snapshot artifact; return a fixed negative-claim report.

    The returned report contains only fixed tokens and hardcoded negative
    claims. It never echoes any caller value, and never affirms release,
    Mint, hardware or visual approval.
    """
    s = _exact_dict(value, TOP_KEYS)
    if _int(s["schema"]) != SCHEMA:
        raise ArtifactError("artifact snapshot schema is unsupported")

    kinds = s["evidence_kinds"]
    if (type(kinds) is not list or len(kinds) > MAX_EVIDENCE_KINDS
            or any(type(k) is not str for k in kinds)
            or tuple(kinds) != EVIDENCE_KINDS):
        raise ArtifactError("artifact evidence kinds are invalid")

    present = []
    if s["frame_pacing"] is not None:
        _validate_frame(s["frame_pacing"])
        present.append("frame_pacing")
    if s["memory_growth"] is not None:
        _validate_memory(s["memory_growth"])
        present.append("memory_growth")
    if s["launch_latency"] is not None:
        _validate_launch(s["launch_latency"])
        present.append("launch_latency")
    if s["pss_kib"] is not None:
        _int(s["pss_kib"], 0, MAX_PSS_KIB)
        present.append("pss")

    if (_int(s["evidence_count"], 0, MAX_EVIDENCE_KINDS) != len(present)):
        raise ArtifactError("artifact evidence count is inconsistent")

    # Hardcoded negative claims: a bool must be exactly False, never 0/None.
    if _bool(s["measurement_performed"]) is not False:
        raise ArtifactError("artifact claims a measurement was performed")
    if _bool(s["real_hardware_measured"]) is not False:
        raise ArtifactError("artifact claims real hardware measurement")
    if s["linux_mint_acceptance"] != NOT_ESTABLISHED or type(
            s["linux_mint_acceptance"]) is not str:
        raise ArtifactError("artifact claims Linux Mint acceptance")
    if s["owner_visual_approval"] != NOT_ESTABLISHED or type(
            s["owner_visual_approval"]) is not str:
        raise ArtifactError("artifact claims owner visual approval")

    return {
        "status": "VALID",
        "schema": SCHEMA,
        "evidence_count": len(present),
        "release_approved": False,
        "linux_mint_acceptance_proven": False,
        "real_hardware_measured": False,
        "owner_visual_approval": False,
        "measurement_performed": False,
    }


def _reject_constant(token):
    raise ArtifactError("non-finite JSON number rejected")


def validate_json(text):
    """Decode bounded UTF-8 JSON text into a parsed artifact and validate it."""
    if isinstance(text, bytes):
        data = text
    elif type(text) is str:
        try:
            data = text.encode("utf-8")
        except UnicodeError as exc:
            raise ArtifactError("artifact text cannot be encoded") from exc
    else:
        raise ArtifactError("artifact JSON must be text or bytes")
    if not data or len(data) > MAX_ARTIFACT_BYTES:
        raise ArtifactError("artifact JSON is missing or oversized")
    try:
        parsed = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ArtifactError("artifact JSON could not be parsed") from exc
    return validate(parsed)


def validate_file(path):
    """Read a bounded, symlink-safe regular file and validate its JSON."""
    p = Path(path)
    if not p.is_absolute():
        raise ArtifactError("absolute artifact path required")
    current = Path(p.anchor)
    for part in p.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ArtifactError("symlinked artifact path rejected")
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ArtifactError("artifact file missing or unsafe") from exc
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ArtifactError("artifact path is not a regular file")
        data = handle.read(MAX_ARTIFACT_BYTES + 1)
    if not data or len(data) > MAX_ARTIFACT_BYTES:
        raise ArtifactError("artifact JSON is missing or oversized")
    return validate_json(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate_file(args.artifact)
    except (ArtifactError, OSError) as exc:
        print("QT_PERF_SNAPSHOT_FAIL:", str(exc)[:150], file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
