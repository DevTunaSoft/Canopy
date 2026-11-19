#!/usr/bin/env python3
"""Collect a bounded, informational Qt process baseline on Linux.

This is not a release threshold or a five-minute idle benchmark.
No shell commands and no elevated privileges are required.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def read_pss_kib(pid: int) -> int:
    path = Path(f"/proc/{pid}/smaps_rollup")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Pss:"):
            return int(line.split()[1])
    raise ValueError("Pss field missing")


def read_cpu_ticks(pid: int) -> int:
    # The comm field in /proc/PID/stat may contain spaces or parentheses.
    record = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    end = record.rfind(")")
    if end < 0:
        raise ValueError("Malformed process stat")
    fields_after_comm = record[end + 2:].split()
    return int(fields_after_comm[11]) + int(fields_after_comm[12])


def measure(exe: Path, duration: float) -> dict:
    if not exe.is_file():
        raise FileNotFoundError(exe)
    process = subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, env=os.environ.copy())
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Canopy exited early: {process.returncode}")
            if process.stderr is None:
                raise RuntimeError("Missing startup channel")
            import select
            ready, _, _ = select.select([process.stderr], [], [], 0.25)
            if ready:
                line = process.stderr.readline().decode("utf-8", errors="replace")
                if "CANOPY_CLASSIC_WINDOW_READY" in line:
                    break
        else:
            raise TimeoutError("Canopy did not report window readiness")
        ticks_start = read_cpu_ticks(process.pid)
        pss_start = read_pss_kib(process.pid)
        started = time.monotonic()
        time.sleep(duration)
        if process.poll() is not None:
            raise RuntimeError(f"Canopy exited during sample: {process.returncode}")
        elapsed = time.monotonic() - started
        ticks_end = read_cpu_ticks(process.pid)
        pss_end = read_pss_kib(process.pid)
        tick_rate = os.sysconf("SC_CLK_TCK")
        return {
            "schema": 1,
            "kind": "short-headless-baseline-not-mint-acceptance",
            "duration_seconds": round(elapsed, 3),
            "cpu_percent_one_core": round(100 * (ticks_end - ticks_start) / tick_rate / elapsed, 3),
            "pss_kib_start": pss_start,
            "pss_kib_end": pss_end,
            "backend": os.environ.get("QT_QUICK_BACKEND", "default"),
        }
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=float, default=5)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 30:
        parser.error("--seconds must be between 1 and 30")
    try:
        data = measure(args.executable.resolve(), args.seconds)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
