#!/usr/bin/env python3
"""Read-only, dependency-free Linux /proc resource measurement helpers.

This module never starts, stops, signals or modifies a process. It reads a
bounded set of bytes from a caller-supplied proc root (``/proc`` by default)
and returns plain JSON-serialisable dictionaries. On a non-Linux host the
caller can point it at a synthetic fixture tree; those results are labelled
``SYNTHETIC`` by :func:`measure` and are not real desktop evidence.
"""
from pathlib import Path
import argparse
import json
import math
import os
import re
import sys
import time

MAX_PROC_FILE_BYTES = 1 << 20
MAX_PID = 1 << 22
MAX_PIDS = 32
MAX_INTERVAL_SECONDS = 300.0
MAX_CLOCK_TICKS_PER_SECOND = 1_000_000
MAX_STARTUP_SECONDS = 86_400.0
MAX_SCOPE_TEXT = 128
STARTUP_PHASES = ("launch_request", "process_spawn", "first_frame", "ready")

_KIB_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]+([0-9]+)[ \t]+kB[ \t]*$")

# Real smaps_rollup output mixes "N kB" memory counters with fields that carry
# no unit: THPeligible is unitless on some kernels, and ProtectionKey/VmFlags
# are never kB values. These names are known non-memory fields; skip them so a
# genuine modern rollup parses, while every other line still has to be a
# strict, bounded "name: N kB" record.
_NON_KIB_FIELDS = frozenset(("THPeligible", "ProtectionKey", "VmFlags"))


class MeasurementError(ValueError):
    """Fail-closed domain error for invalid or unreadable measurement input."""


def _require_pid(pid):
    if type(pid) is not int or not 0 < pid <= MAX_PID:
        raise MeasurementError(f"invalid pid: {pid!r}")
    return pid


def _read_bounded(path, proc_root=None):
    """Read one bounded regular proc file, rejecting symlink path escapes.

    ``proc_root`` is the trusted base. When supplied, every component between
    it and ``path`` is checked for symlinks: checking only the final component
    lets a symlinked pid directory redirect the read outside the proc tree.
    """
    path = Path(path)
    if proc_root is not None:
        root = Path(proc_root)
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise MeasurementError("proc path outside proc root") from exc
        cursor = root
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise MeasurementError(f"symlink in proc path: {part}")
    try:
        if path.is_symlink() or not path.is_file():
            raise MeasurementError(f"not a regular proc file: {path.name}")
        with path.open("rb") as handle:
            data = handle.read(MAX_PROC_FILE_BYTES + 1)
    except OSError as exc:
        raise MeasurementError(f"unreadable proc file: {path.name}") from exc
    if len(data) > MAX_PROC_FILE_BYTES:
        raise MeasurementError(f"proc file too large: {path.name}")
    # Normalise CRLF proc dumps: on Windows a fixture written with Path.write_text
    # gains carriage returns, which must not change field parsing semantics.
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise MeasurementError(f"invalid utf-8 in proc file: {path.name}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _kib_fields(text):
    fields = {}
    for line in text.splitlines():
        name, colon, _unused = line.partition(":")
        if colon and name in _NON_KIB_FIELDS:
            continue
        match = _KIB_LINE.fullmatch(line)
        if match is None:
            raise MeasurementError("malformed proc memory line")
        name, value = match.group(1), int(match.group(2))
        if value > MAX_PROC_FILE_BYTES:
            raise MeasurementError("proc memory value out of range")
        fields[name] = value
    return fields


def _kib_field(line, name):
    """Return the value of an exact ``name: N kB`` line, or None if unrelated."""
    if not line.startswith(name + ":"):
        return None
    match = _KIB_LINE.fullmatch(line)
    if match is None or match.group(1) != name:
        raise MeasurementError(f"malformed proc memory field: {name}")
    value = int(match.group(2))
    if value > MAX_PROC_FILE_BYTES:
        raise MeasurementError("proc memory value out of range")
    return value


def read_memory(pid, proc_root=Path("/proc")):
    """Return one process's PSS/RSS in KiB from a bounded proc snapshot.

    ``pss_kib`` is null (not zero) when the kernel exposes no PSS counter;
    a null must never be silently converted into a target comparison.
    """
    pid = _require_pid(pid)
    root = Path(proc_root)
    pid_dir = root / str(pid)

    rollup = pid_dir / "smaps_rollup"
    fields = {}
    if rollup.exists():
        fields = _kib_fields(_read_bounded(rollup, root))

    if "Rss" in fields:
        return {"pid": pid, "pss_kib": fields.get("Pss"),
                "rss_kib": fields["Rss"], "source": "smaps_rollup"}

    text = _read_bounded(pid_dir / "smaps", root)
    pss = rss = 0
    for line in text.splitlines():
        value = _kib_field(line, "Pss")
        if value is not None:
            pss += value
            continue
        value = _kib_field(line, "Rss")
        if value is not None:
            rss += value
    return {"pid": pid, "pss_kib": pss if pss else None, "rss_kib": rss,
            "source": "smaps"}


def _finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MeasurementError(f"invalid {label}: {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise MeasurementError(f"nonfinite {label}")
    return number


def _nonnegative_int(text, label):
    if not text.isdigit():
        raise MeasurementError(f"malformed {label} in proc stat")
    return int(text)


def validate_interval(seconds):
    """Accept only a finite, strictly positive, bounded measurement interval."""
    value = _finite_number(seconds, "interval seconds")
    if not 0 < value <= MAX_INTERVAL_SECONDS:
        raise MeasurementError("interval seconds out of bounds")
    return value


def read_cpu_ticks(pid, proc_root=Path("/proc")):
    """Read cumulative scheduler ticks and the process start tick from stat."""
    pid = _require_pid(pid)
    root = Path(proc_root)
    text = _read_bounded(root / str(pid) / "stat", root)
    close = text.rfind(")")
    if close < 0 or not text.startswith(f"{pid} ("):
        raise MeasurementError("malformed proc stat command field")
    fields = text[close + 1:].split()
    if len(fields) < 20:
        raise MeasurementError("short proc stat record")
    return {
        "pid": pid,
        "ticks": (_nonnegative_int(fields[11], "utime")
                  + _nonnegative_int(fields[12], "stime")),
        "start_time_ticks": _nonnegative_int(fields[19], "starttime"),
    }


def compute_cpu(start_samples, end_samples, clock_ticks_per_second,
                elapsed_seconds, interval_seconds):
    """Convert two bounded stat snapshots into percent of one CPU core."""
    validate_interval(interval_seconds)
    elapsed = _finite_number(elapsed_seconds, "elapsed seconds")
    if not 0 < elapsed <= MAX_INTERVAL_SECONDS + 1.0:
        raise MeasurementError("elapsed seconds out of bounds")
    ticks_per_second = _finite_number(clock_ticks_per_second, "clock ticks per second")
    if not 0 < ticks_per_second <= MAX_CLOCK_TICKS_PER_SECOND:
        raise MeasurementError("clock ticks per second out of bounds")
    if (not isinstance(start_samples, (list, tuple))
            or not isinstance(end_samples, (list, tuple))
            or len(start_samples) > MAX_PIDS
            or len(end_samples) > MAX_PIDS):
        raise MeasurementError("invalid CPU sample set")

    by_pid = {}
    for sample in start_samples:
        if not isinstance(sample, dict) or type(sample.get("pid")) is not int:
            raise MeasurementError("invalid start CPU sample")
        by_pid[sample["pid"]] = sample
    processes = []
    for end in end_samples:
        if not isinstance(end, dict) or type(end.get("pid")) is not int:
            raise MeasurementError("invalid end CPU sample")
        pid = end["pid"]
        start = by_pid.pop(pid, None)
        if start is None:
            raise MeasurementError("CPU sample PID sets differ")
        if (type(start.get("ticks")) is not int or type(end.get("ticks")) is not int
                or type(start.get("start_time_ticks")) is not int
                or type(end.get("start_time_ticks")) is not int):
            raise MeasurementError("non-integer CPU counter")
        if start["start_time_ticks"] != end["start_time_ticks"]:
            raise MeasurementError("PID reused between CPU samples")
        delta = end["ticks"] - start["ticks"]
        if delta < 0:
            raise MeasurementError("CPU tick counter regressed")
        percent = round(delta / ticks_per_second / elapsed * 100.0, 6)
        processes.append({
            "pid": pid, "ticks_start": start["ticks"], "ticks_end": end["ticks"],
            "delta_ticks": delta, "percent_of_one_core": percent,
        })
    if by_pid:
        raise MeasurementError("CPU sample PID sets differ")
    processes.sort(key=lambda item: item["pid"])
    total = round(sum(item["percent_of_one_core"] for item in processes), 6)
    return {
        "interval_seconds": round(interval_seconds, 6),
        "elapsed_seconds": round(elapsed, 6),
        "clock_ticks_per_second": ticks_per_second,
        "processes": processes,
        "total_percent_of_one_core": total,
    }


def _read_optional(path, proc_root=None):
    return _read_bounded(path, proc_root) if path.exists() else None


def _numeric_field(text, name):
    if text is None:
        return None
    pattern = re.compile(
        r"^[ \t]*" + re.escape(name) + r"[ \t]*:[ \t]*([0-9]+)[ \t]*$",
        re.MULTILINE,
    )
    matches = pattern.findall(text)
    if not matches:
        return None
    if len(matches) != 1:
        raise MeasurementError(f"duplicate proc field: {name}")
    value = int(matches[0])
    if value > MAX_PROC_FILE_BYTES:
        raise MeasurementError(f"proc field out of range: {name}")
    return value


def read_wakeups(pid, proc_root=Path("/proc")):
    """Read the optional ``nr_wakeups`` counter from ``/proc/pid/sched``."""
    pid = _require_pid(pid)
    root = Path(proc_root)
    text = _read_optional(root / str(pid) / "sched", root)
    return _numeric_field(text, "nr_wakeups")


def _context_switches(pid, proc_root):
    root = Path(proc_root)
    text = _read_optional(root / str(pid) / "status", root)
    voluntary = _numeric_field(text, "voluntary_ctxt_switches")
    nonvoluntary = _numeric_field(text, "nonvoluntary_ctxt_switches")
    if voluntary is None or nonvoluntary is None:
        return None
    return {"pid": pid, "voluntary": voluntary, "nonvoluntary": nonvoluntary}


def build_wakeups(pids, proc_root=Path("/proc")):
    """Collect wakeups where the kernel exposes them, never by proxy."""
    if not isinstance(pids, (list, tuple)) or len(pids) > MAX_PIDS:
        raise MeasurementError("invalid wakeup PID set")
    for pid in pids:
        _require_pid(pid)
    if len(set(pids)) != len(pids):
        raise MeasurementError("duplicate wakeup PID")
    processes = []
    switches = []
    for pid in pids:
        pid = _require_pid(pid)
        wakeups = read_wakeups(pid, proc_root)
        context = _context_switches(pid, proc_root)
        processes.append({
            "pid": pid, "wakeups": wakeups,
            "source": "sched.nr_wakeups" if wakeups is not None else "not_available",
        })
        if context is not None:
            switches.append(context)
    available = any(item["wakeups"] is not None for item in processes)
    return {
        "status": "AVAILABLE" if available else "NOT_AVAILABLE",
        "processes": processes,
        "context_switches": switches,
        "note": ("Context switches are not scheduler wakeups; a null wakeup "
                 "value is NOT_RUN, never a zero or an inferred count."),
    }


def build_startup_timings(timestamps):
    """Convert caller-supplied monotonic timestamps into phase deltas.

    The tool does not instrument the launcher and cannot attest where the
    timestamps came from, so the report records the supply basis explicitly.
    """
    if not isinstance(timestamps, dict) or len(timestamps) > len(STARTUP_PHASES):
        raise MeasurementError("invalid startup timestamp set")
    for key in timestamps:
        if not isinstance(key, str) or key not in STARTUP_PHASES:
            raise MeasurementError("unknown startup phase")
    if "launch_request" not in timestamps:
        raise MeasurementError("missing launch_request timestamp")

    values = {}
    for name in STARTUP_PHASES:
        if name not in timestamps:
            continue
        value = _finite_number(timestamps[name], f"{name} timestamp")
        if not 0 <= value <= MAX_STARTUP_SECONDS:
            raise MeasurementError("startup timestamp out of bounds")
        values[name] = value
    ordered = [values[name] for name in STARTUP_PHASES if name in values]
    if any(later < earlier for earlier, later in zip(ordered, ordered[1:])):
        raise MeasurementError("startup phases are not monotonic")

    base = values["launch_request"]
    phases_ms = {
        name: round((value - base) * 1000.0, 3) for name, value in values.items()
    }
    return {
        "status": "AVAILABLE",
        "basis": "caller-supplied monotonic timestamps (not instrumented by this tool)",
        "phases_ms": phases_ms,
        "total_ready_ms": phases_ms.get("ready"),
    }


def _scope_text(value, field):
    if (not isinstance(value, str) or not value or len(value) > MAX_SCOPE_TEXT
            or not value.isprintable() or value != value.strip()):
        raise MeasurementError(f"invalid scope {field}")
    return value


def _scope_list(values, name):
    if not isinstance(values, (list, tuple)) or len(values) > MAX_PIDS:
        raise MeasurementError(f"invalid {name} process list")
    entries = []
    seen = set()
    for entry in values:
        if not isinstance(entry, dict) or set(entry) != {"pid", "label", "reason"}:
            raise MeasurementError(f"invalid {name} process entry")
        pid = _require_pid(entry["pid"])
        if pid in seen:
            raise MeasurementError(f"duplicate {name} pid")
        seen.add(pid)
        entries.append({
            "pid": pid,
            "label": _scope_text(entry["label"], "label"),
            "reason": _scope_text(entry["reason"], "reason"),
        })
    entries.sort(key=lambda item: item["pid"])
    return entries


def validate_scope(included, excluded):
    """Validate the explicit included/excluded process declaration."""
    included_entries = _scope_list(included, "included")
    excluded_entries = _scope_list(excluded, "excluded")
    included_pids = {entry["pid"] for entry in included_entries}
    excluded_pids = {entry["pid"] for entry in excluded_entries}
    if included_pids & excluded_pids:
        raise MeasurementError("pid appears in both scope lists")
    return {
        "included_processes": included_entries,
        "excluded_processes": excluded_entries,
        "basis": "explicit caller declaration; not kernel-verified",
    }


SOURCES = ("fixture", "proc")
SESSIONS = ("fixture", "xvfb", "linux-host", "linux-mint-guest-unverified")


def _kib_total(samples, field):
    values = [sample[field] for sample in samples]
    present = [value for value in values if value is not None]
    if not present:
        return None, "NOT_AVAILABLE"
    if len(present) != len(values):
        return sum(present), "PARTIAL"
    return sum(present), "AVAILABLE"


def _memory_summary(start, end):
    pss_start, start_status = _kib_total(start, "pss_kib")
    pss_end, end_status = _kib_total(end, "pss_kib")
    rss_start, _ = _kib_total(start, "rss_kib")
    rss_end, _ = _kib_total(end, "rss_kib")
    pss_values = [value for value in (pss_start, pss_end) if value is not None]
    rss_values = [value for value in (rss_start, rss_end) if value is not None]
    if "NOT_AVAILABLE" in (start_status, end_status):
        pss_status = "NOT_AVAILABLE" if not pss_values else "PARTIAL"
    elif "PARTIAL" in (start_status, end_status):
        pss_status = "PARTIAL"
    else:
        pss_status = "AVAILABLE"
    return {
        "samples": {"start": start, "end": end},
        "totals": {
            "pss_kib_start": pss_start,
            "pss_kib_end": pss_end,
            "pss_kib_peak": max(pss_values) if pss_values else None,
            "rss_kib_start": rss_start,
            "rss_kib_end": rss_end,
            "rss_kib_peak": max(rss_values) if rss_values else None,
            "pss_status": pss_status,
        },
        "measurement_method": (
            "read-only /proc smaps_rollup or smaps plus stat; "
            "no Windows working-set substitution"
        ),
    }


def _default_clock_ticks():
    sysconf = getattr(os, "sysconf", None)
    if sysconf is None:
        return 100
    try:
        value = sysconf("SC_CLK_TCK")
    except (OSError, ValueError):
        return 100
    return int(value) if isinstance(value, int) and value > 0 else 100


def measure(pids, *, proc_root=Path("/proc"), source="fixture", session="fixture",
            interval_seconds=5.0, clock_ticks_per_second=None,
            startup_timestamps=None, included=None, excluded=None,
            clock=None, sleep=None):
    """Take one bounded, read-only proc snapshot pair and label it honestly."""
    if source not in SOURCES or session not in SESSIONS:
        raise MeasurementError("unsupported source or session")
    validate_interval(interval_seconds)
    if not isinstance(pids, (list, tuple)) or len(pids) > MAX_PIDS:
        raise MeasurementError("invalid measurement PID set")
    for pid in pids:
        _require_pid(pid)
    if len(set(pids)) != len(pids):
        raise MeasurementError("duplicate measurement PID")
    pids = sorted(pids)

    scope = validate_scope(included or [], excluded or [])
    included_pids = {entry["pid"] for entry in scope["included_processes"]}
    if set(pids) - included_pids:
        raise MeasurementError("measured PID is not in the included scope")

    if clock_ticks_per_second is None:
        clock_ticks_per_second = _default_clock_ticks()
    _finite_number(clock_ticks_per_second, "clock ticks per second")
    tick = clock if clock is not None else time.monotonic
    nap = sleep if sleep is not None else time.sleep

    start_clock = _finite_number(tick(), "start clock reading")
    memory_start = [read_memory(pid, proc_root) for pid in pids]
    cpu_start = [read_cpu_ticks(pid, proc_root) for pid in pids]
    nap(interval_seconds)
    end_clock = _finite_number(tick(), "end clock reading")
    memory_end = [read_memory(pid, proc_root) for pid in pids]
    cpu_end = [read_cpu_ticks(pid, proc_root) for pid in pids]

    cpu = compute_cpu(cpu_start, cpu_end, clock_ticks_per_second,
                      end_clock - start_clock, interval_seconds)
    startup = (build_startup_timings(startup_timestamps)
               if startup_timestamps is not None else {
                   "status": "NOT_RUN",
                   "basis": "no timestamps supplied",
                   "phases_ms": {},
                   "total_ready_ms": None,
               })
    return {
        "schema": 1,
        "tool": "linux_resource_probe",
        "source": source,
        "session": session,
        "environment_attested": False,
        "evidence_class": "SYNTHETIC" if source == "fixture" else "LINUX_PROC_SCOPED",
        "scope": scope,
        "memory": _memory_summary(memory_start, memory_end),
        "cpu": cpu,
        "wakeups": build_wakeups(pids, proc_root),
        "startup": startup,
        "targets": {
            "pss_mib": 200,
            "cpu_percent_of_one_core": 1.0,
            "status": "TARGETS_NOT_ACHIEVEMENTS",
            "windows_working_set_substitution": "NOT_USED",
            "basis": "docs/QUALITY.md engineering targets, not measured achievements",
        },
        "acceptance": {
            "linux_mint": "NOT_RUN",
            "screen_reader": "NOT_RUN",
            "visual": "NOT_RUN",
            "release_ready": False,
            "reason": ("This tool reads only the supplied proc root; it cannot "
                       "attest a Mint guest, desktop session, visual state or "
                       "accessibility behavior."),
        },
    }


def _load_json(path):
    text = _read_bounded(Path(path))

    def no_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise MeasurementError("duplicate JSON key in input")
            result[key] = value
        return result

    try:
        document = json.loads(text, object_pairs_hook=no_duplicate_keys)
    except MeasurementError:
        raise
    except (ValueError, TypeError) as exc:
        raise MeasurementError("invalid JSON input") from exc
    if not isinstance(document, dict):
        raise MeasurementError("JSON input must be an object")
    return document


def main(argv=None):
    """CLI: read a proc root and write a labelled JSON report."""
    parser = argparse.ArgumentParser(
        description="Read-only Linux PSS/RSS, CPU, wakeup and startup probe"
    )
    parser.add_argument("--pid", action="append", type=int, dest="pids", required=True)
    parser.add_argument("--proc-root", default="/proc")
    parser.add_argument("--source", choices=SOURCES, required=True)
    parser.add_argument("--session", choices=SESSIONS, default="fixture")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--clock-ticks-per-second", type=float, default=None)
    parser.add_argument("--scope", required=True, help="JSON with included/excluded process lists")
    parser.add_argument("--startup", help="optional JSON with startup timestamps")
    parser.add_argument("--output", help="report path; stdout when omitted")
    args = parser.parse_args(argv)

    try:
        scope = _load_json(args.scope)
        if set(scope) != {"included_processes", "excluded_processes"}:
            raise MeasurementError("scope JSON has unexpected keys")
        startup = _load_json(args.startup) if args.startup else None
        output = Path(args.output).resolve() if args.output else None
        if output is not None and output.is_relative_to(Path(args.proc_root).resolve()):
            raise MeasurementError("output must not be inside the proc root")
        report = measure(
            args.pids, proc_root=Path(args.proc_root), source=args.source,
            session=args.session, interval_seconds=args.interval,
            clock_ticks_per_second=args.clock_ticks_per_second,
            startup_timestamps=startup,
            included=scope["included_processes"],
            excluded=scope["excluded_processes"],
        )
        text = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if output is None:
            sys.stdout.write(text)
        else:
            output.write_text(text, encoding="utf-8", newline="\n")
    except (MeasurementError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
