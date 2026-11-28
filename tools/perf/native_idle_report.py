#!/usr/bin/env python3
"""Summarise raw native_idle_sampler.sh TSV into measured JSON (no estimation).

Usage: python3 tools/perf/native_idle_report.py RAW.tsv OUT.json
Every number is derived from the raw sample rows; missing data stays null.
"""
import json
import statistics
import sys
from pathlib import Path

ROW_FIELDS = ("t", "pid", "comm", "utime", "stime", "rss_kib", "pss_kib",
              "vol", "invol", "wake", "sys_user", "sys_nice", "sys_system",
              "sys_idle", "sys_iowait")


def main(raw_path, out_path):
    text = Path(raw_path).read_text(encoding="utf-8", errors="replace")
    meta = {}
    rows = []
    for line in text.splitlines():
        if line.startswith("# "):
            body = line[2:]
            for token in body.split(" "):
                key, sep, val = token.partition("=")
                if sep:
                    meta[key] = val
            if "=" not in body:
                meta[body.strip()] = True
        elif line.startswith("S "):
            vals = line.split()
            if len(vals) - 1 < len(ROW_FIELDS):
                vals.append("NA")  # early raw logs omitted sys_iowait
            if len(vals) != len(ROW_FIELDS) + 1:
                continue
            rec = dict(zip(ROW_FIELDS, vals[1:]))
            for k in ROW_FIELDS:
                if k not in ("pid", "comm"):
                    try:
                        rec[k] = float(rec[k])
                    except ValueError:
                        rec[k] = None
            rows.append(rec)
    if not rows:
        raise SystemExit("no sample rows")
    clk = float(meta.get("clk_tck", 100))
    elapsed = max(r["t"] for r in rows)
    by_pid = {}
    for r in rows:
        by_pid.setdefault(r["pid"], []).append(r)
    procs = {}
    for pid, samples in by_pid.items():
        first, last = samples[0], samples[-1]
        ticks = (last["utime"] - first["utime"]) + (last["stime"] - first["stime"])
        pss = [s["pss_kib"] for s in samples if s["pss_kib"] is not None]
        rss = [s["rss_kib"] for s in samples if s["rss_kib"] is not None]
        procs[pid] = {
            "comm": first["comm"],
            "samples": len(samples),
            "cpu_ticks_delta": ticks,
            "cpu_percent_one_core": round(100 * ticks / clk / elapsed, 4) if elapsed else None,
            "pss_kib": {"min": min(pss), "mean": round(statistics.mean(pss), 1),
                        "max": max(pss)} if pss else None,
            "rss_kib": {"min": min(rss), "mean": round(statistics.mean(rss), 1),
                        "max": max(rss)} if rss else None,
            "voluntary_ctx_delta": int(last["vol"] - first["vol"]) if last["vol"] is not None and first["vol"] is not None else None,
            "nonvoluntary_ctx_delta": int(last["invol"] - first["invol"]) if last["invol"] is not None and first["invol"] is not None else None,
        }
    shell = {pid: p for pid, p in procs.items()
             if p["comm"] in ("startplasma-x11", "kwin_x11", "plasmashell")}
    canopy = {pid: p for pid, p in procs.items() if pid not in shell}
    def agg(group):
        if not group:
            return None
        ticks = sum(p["cpu_ticks_delta"] for p in group.values())
        pss_max = sum(p["pss_kib"]["max"] for p in group.values() if p["pss_kib"])
        pss_mean = sum(p["pss_kib"]["mean"] for p in group.values() if p["pss_kib"])
        return {
            "processes": len(group),
            "cpu_ticks_delta_sum": ticks,
            "cpu_percent_one_core": round(100 * ticks / clk / elapsed, 4) if elapsed else None,
            "cpu_percent_two_cores": round(100 * ticks / clk / elapsed / 2, 4) if elapsed else None,
            "pss_kib_sum_mean": round(pss_mean, 1),
            "pss_kib_sum_of_per_process_peaks": pss_max,
        }
    system = None
    lastrow = rows[-1]
    firstrow = rows[0]
    if all(lastrow[k] is not None and firstrow[k] is not None for k in ("sys_user", "sys_idle")):
        idle_delta = lastrow["sys_idle"] - firstrow["sys_idle"]
        system = {"idle_delta_ticks": idle_delta,
                  "idle_percent_of_all_cpu_time": round(100 * idle_delta / (clk * elapsed * 2), 3)}
    out = {
        "schema": "canopy.native_idle_report/1",
        "raw_path": str(Path(raw_path).resolve()),
        "label": meta.get("label"),
        "start_utc": meta.get("utc"),
        "end_utc": meta.get("end_utc"),
        "guest": meta.get("guest"),
        "elapsed_seconds": elapsed,
        "clk_tck": clk,
        "sample_rows": len(rows),
        "per_process": procs,
        "stock_shell_processes": shell,
        "canopy_processes": canopy,
        "aggregate_stock_shell": agg(shell),
        "aggregate_canopy": agg(canopy),
        "aggregate_all_observed": agg(procs),
        "system_idle": system,
    }
    Path(out_path).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(Path(out_path).resolve()),
                      "elapsed_seconds": elapsed,
                      "stock": agg(shell), "canopy": agg(canopy)}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
