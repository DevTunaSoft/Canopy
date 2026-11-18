"""Bounded Linux /proc sampling for a test-owned Canopy process.

No root privileges, arbitrary execution or system-wide enumeration.
"""
import argparse
import json
import os
from pathlib import Path
import time


def parse_status(contents):
    values = {}
    for line in contents.splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            key, tail = line.split(":", 1)
            parts = tail.split()
            if len(parts) != 2 or parts[1] != "kB" or not parts[0].isdigit():
                raise ValueError("Unexpected /proc memory format")
            values[key.lower() + "_kib"] = int(parts[0])
    return values


def read_memory(pid, *, proc_root=Path("/proc"), uid=None):
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError("PID must be positive")
    path = proc_root / str(pid)
    expected_uid = os.getuid() if uid is None else uid
    if path.stat().st_uid != expected_uid:
        raise PermissionError("Only the current user's test processes may be sampled")
    return parse_status((path / "status").read_text(encoding="ascii", errors="replace"))


def sample(pid, *, samples=5, interval=0.2, reader=read_memory, sleep=time.sleep):
    if not 1 <= samples <= 120 or not 0 <= interval <= 10:
        raise ValueError("Invalid sampling bounds")
    observations = []
    for index in range(samples):
        try:
            observations.append(reader(pid))
        except (FileNotFoundError, ProcessLookupError):
            break
        if index < samples - 1:
            sleep(interval)
    if not observations:
        raise RuntimeError("Process ended before the first sample")
    rss = [item["vmrss_kib"] for item in observations if "vmrss_kib" in item]
    peaks = [item["vmhwm_kib"] for item in observations if "vmhwm_kib" in item]
    if not rss:
        raise RuntimeError("RSS unavailable")
    return {"pid": pid, "samples": len(observations), "rss_last_kib": rss[-1],
            "rss_peak_observed_kib": max(rss),
            "hwm_reported_kib": max(peaks) if peaks else None,
            "note": "Linux proc memory only; no CPU, startup or responsiveness measurement"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure one user-owned Linux test process")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = sample(args.pid, samples=args.samples, interval=args.interval)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print("Memory sample recorded; not a full benchmark")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
