#!/usr/bin/env python3
"""Guest-side wakeup-cadence probe (frame-pacing PROXY, not frame timestamps).

Usage: ssh ... canopy@127.0.0.1 'python3 - 60 kwin_x11 canopy-classic' < this-file
Reads cumulative context-switch counters from /proc at 20 Hz and emits one
JSON line per monitored process: mean wakeups/s, p50/p95 of 20 ms buckets and
the raw bucket histogram. No guest writes, no process control, no settings.
"""
import json
import statistics
import sys
import time
from pathlib import Path


def counts(pid):
    data = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace")
    def field(name):
        for line in data.splitlines():
            if line.startswith(name + ":"):
                return int(line.split(":", 1)[1].strip())
        return None
    a, b = field("voluntary_ctxt_switches"), field("nonvoluntary_ctxt_switches")
    return (a + b) if a is not None and b is not None else None


def main():
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    names = sys.argv[2:] or ["kwin_x11", "canopy-classic"]
    targets = {}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc / "comm").read_text().strip()
        except OSError:
            continue
        if comm in names and comm not in targets:
            targets[comm] = int(proc.name)
    result = {"schema": "canopy.wakeup_cadence_proxy/1", "label": "PROXY_NOT_FRAME_TIMESTAMPS",
              "duration_seconds": seconds, "sample_interval_ms": 20,
              "targets": targets, "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "per_process": {}}
    previous = {n: counts(p) for n, p in targets.items()}
    buckets = {n: [] for n in targets}
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(0.02)
        for name, pid in targets.items():
            cur = counts(pid)
            prev = previous[name]
            if cur is not None and prev is not None:
                buckets[name].append(cur - prev)
            previous[name] = cur
    elapsed = seconds
    for name, values in buckets.items():
        total = sum(values)
        ordered = sorted(values)
        def pct(q):
            return ordered[min(len(ordered) - 1, int(q * len(ordered)))] if ordered else None
        result["per_process"][name] = {
            "pid": targets[name], "bucket_count": len(values),
            "wakeups_total": total, "wakeups_per_second": round(total / elapsed, 3),
            "bucket_p50": pct(0.5), "bucket_p95": pct(0.95), "bucket_max": max(values) if values else None,
        }
    result["end_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
