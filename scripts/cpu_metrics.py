"""Measure CPU use for one owned Linux test process using /proc.

A standard-library helper, not a service or a full system benchmark. A Linux
process can use more than one core; values may therefore exceed 100%.
"""
import argparse
import json
import os
from pathlib import Path
import time


def parse_proc_stat(value):
    """Return (CPU ticks, start ticks) without splitting spaces in comm."""
    close = value.rfind(") ")
    open_ = value.find("(")
    if open_ < 0 or close < open_:
        raise ValueError("Malformed /proc stat command field")
    fields = value[close + 2:].split()
    # fields[0] is state (field 3); utime=14, stime=15, starttime=22.
    if len(fields) < 20:
        raise ValueError("Incomplete /proc stat")
    try:
        utime, stime, start = (int(fields[i]) for i in (11, 12, 19))
    except ValueError as error:
        raise ValueError("Invalid /proc CPU counters") from error
    if min(utime, stime, start) < 0:
        raise ValueError("Negative /proc CPU counters")
    return utime + stime, start


def read_ticks(pid, *, proc_root=Path("/proc"), uid=None):
    if type(pid) is not int or pid <= 0:
        raise ValueError("PID must be a positive integer")
    path = proc_root / str(pid)
    expected_uid = os.getuid() if uid is None else uid
    if path.stat().st_uid != expected_uid:
        raise PermissionError("Only the current user's test process may be sampled")
    return parse_proc_stat((path / "stat").read_text(encoding="ascii", errors="replace"))


def measure(pid, *, interval=1.0, reader=read_ticks, clock=time.monotonic,
            sleep=time.sleep, ticks_per_second=None):
    if not isinstance(interval, (float, int)) or not 0 < interval <= 30:
        raise ValueError("Sampling interval must be greater than 0 and at most 30 seconds")
    hz = os.sysconf("SC_CLK_TCK") if ticks_per_second is None else ticks_per_second
    if type(hz) not in (float, int) or hz <= 0:
        raise ValueError("Invalid clock tick frequency")
    t0 = clock()
    initial, initial_start = reader(pid)
    sleep(interval)
    latest, latest_start = reader(pid)
    elapsed = clock() - t0
    if latest_start != initial_start:
        raise RuntimeError("Process PID was reused during measurement")
    if latest < initial or elapsed <= 0:
        raise RuntimeError("Invalid CPU sample or nonpositive elapsed time")
    return {"pid": pid, "elapsed_seconds": round(elapsed, 5),
            "cpu_seconds": round((latest - initial) / hz, 5),
            "cpu_percent_one_core": round(100 * (latest - initial) / hz / elapsed, 3),
            "interpretation": "Percent of one logical CPU, may exceed 100%; not system total"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure CPU use of one owned Linux PID")
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--interval", default=1.0, type=float)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = measure(args.pid, interval=args.interval)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, PermissionError, RuntimeError, ValueError) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print("Process CPU sample recorded; not a full benchmark")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
