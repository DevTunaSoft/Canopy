#!/usr/bin/env python3
"""Summarise a native-soak TSV (native-soak-sample/2) into JSON facts.

Usage: python3 tools/stability/native_soak_report.py RAW.tsv REPORT.json
Never synthesises missing data: NA stays null, NOT_RUN items are explicit.
"""
import json
import statistics
import sys

STRING_COLS = {"utc", "role", "comm"}

COLS = ("t_rel_s utc pid role comm starttime_ticks utime_ticks stime_ticks "
        "rss_kib pss_kib vol_ctx invol_ctx wakeups_or_NA sys_idle_ticks "
        "sys_total_ticks procs_running system_units user_units").split()


def num(value):
    if value in ("NA", "", None):
        return None
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return None


def summarize_series(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return {"min": min(vals), "max": max(vals),
            "mean": round(statistics.fmean(vals), 3),
            "first": vals[0], "last": vals[-1]}


def main(path, out_path):
    meta, rows, events = {}, [], []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("# "):
                body = line[2:]
                if "=" in body:
                    k, v = body.split("=", 1)
                    meta[k] = v
                else:
                    parts = body.split(":", 1)
                    meta[parts[0]] = parts[1].strip() if len(parts) == 2 else ""
            elif line.startswith("S "):
                fields = line.split()
                if len(fields) != len(COLS) + 1:
                    raise ValueError("row field count %d != %d: %s" %
                                     (len(fields) - 1, len(COLS), line[:160]))
                rows.append(dict(zip(
                    COLS, (f if col in STRING_COLS else num(f)
                           for col, f in zip(COLS, fields[1:])))))
            elif line.startswith("EVENT "):
                events.append(json.loads(line[6:]))

    targets = {}
    for row in rows:
        key = (row["pid"], row["starttime_ticks"])
        targets.setdefault(key, []).append(row)

    clk = int(meta.get("clk_tck", "100"))
    duration = int(meta.get("elapsed_s", "0") or 0)
    per_process = []
    for (pid, starttime), samples in sorted(targets.items()):
        samples.sort(key=lambda r: r["t_rel_s"])
        first, last = samples[0], samples[-1]
        span = max(1, last["t_rel_s"] - first["t_rel_s"])
        cpu_ticks = (last["utime_ticks"] or 0) + (last["stime_ticks"] or 0) \
            - (first["utime_ticks"] or 0) - (first["stime_ticks"] or 0)
        pss_first, pss_last = first["pss_kib"], last["pss_kib"]
        per_process.append({
            "pid": pid, "role": first["role"], "comm": first["comm"],
            "starttime_ticks": starttime, "samples": len(samples),
            "first_t_s": first["t_rel_s"], "last_t_s": last["t_rel_s"],
            "pss_kib": summarize_series([r["pss_kib"] for r in samples]),
            "rss_kib": summarize_series([r["rss_kib"] for r in samples]),
            "pss_growth_kib": (pss_last - pss_first)
            if None not in (pss_first, pss_last) else None,
            "pss_growth_pct": round(100.0 * (pss_last - pss_first) / pss_first, 2)
            if pss_first else None,
            "cpu_pct_of_one_core": round(100.0 * cpu_ticks / clk / span, 4)
            if cpu_ticks >= 0 else None,
            "cpu_ticks_delta": cpu_ticks,
            "ctx_total_delta": (last["vol_ctx"] or 0) + (last["invol_ctx"] or 0)
            - (first["vol_ctx"] or 0) - (first["invol_ctx"] or 0),
            "ctx_per_s": round(((last["vol_ctx"] or 0) + (last["invol_ctx"] or 0)
                                - (first["vol_ctx"] or 0) - (first["invol_ctx"] or 0)) / span, 3),
            "wakeups_exported": last["wakeups_or_NA"] is not None,
            "wakeups_delta": (last["wakeups_or_NA"] - first["wakeups_or_NA"])
            if None not in (first["wakeups_or_NA"], last["wakeups_or_NA"]) else None,
        })

    starts = [e for e in events if e.get("event") == "process_start" and e.get("t", 0) > 0]
    exits = [e for e in events if e.get("event") == "process_exit"]
    journal = next((e for e in events if e.get("event") == "journal_probe"), {})

    instants = sorted({r["t_rel_s"] for r in rows})
    gaps = [{"from_s": a, "to_s": b, "delta_s": b - a}
            for a, b in zip(instants, instants[1:]) if b - a > 120]
    target_names = ("canopy-classic", "kwin_x11", "plasmashell", "startplasma-x11")
    dumps = journal.get("coredumps", [])
    target_dumps = [ln for ln in dumps if any(name in ln for name in target_names)]
    system_dumps = [ln for ln in dumps if ln not in target_dumps]

    # Bounded 5-minute CPU windows for the incremental Canopy process.
    windows = {}
    for row in rows:
        if row["role"] != "canopy":
            continue
        bucket = row["t_rel_s"] // 300
        windows.setdefault(bucket, []).append(row)
    cpu_windows = []
    for bucket, samples in sorted(windows.items()):
        samples.sort(key=lambda r: r["t_rel_s"])
        first, last = samples[0], samples[-1]
        span = max(1, last["t_rel_s"] - first["t_rel_s"])
        ticks = (last["utime_ticks"] + last["stime_ticks"]
                 - first["utime_ticks"] - first["stime_ticks"])
        cpu_windows.append({"window_index": bucket, "start_s": first["t_rel_s"],
                            "end_s": last["t_rel_s"],
                            "cpu_pct_of_one_core": round(100.0 * ticks / clk / span, 4)})

    sys_units = summarize_series([r["system_units"] for r in rows])
    user_units = summarize_series([r["user_units"] for r in rows])
    idle = summarize_series([
        (100.0 * r["sys_idle_ticks"] / r["sys_total_ticks"])
        if r["sys_total_ticks"] else None for r in rows])

    warnings = []
    if any(p["pss_growth_kib"] is not None and
           (p["pss_growth_kib"] > 51200 or (p["pss_growth_pct"] or 0) > 25)
           for p in per_process):
        warnings.append("PSS_GROWTH_THRESHOLD")
    if starts:
        warnings.append("PROCESS_RESTART")
    if journal.get("coredump_total", 0) or journal.get("journal_user_errors_total", 0) \
            or journal.get("journal_system_errors_total", 0):
        warnings.append("CRASH_OR_ERROR_EVENT")
    if target_dumps or starts:
        warnings.append("TARGET_PROCESS_RESTART_OR_CRASH")
    if gaps:
        warnings.append("SAMPLING_GAP")
    if sys_units and user_units:
        if (sys_units["max"] - sys_units["min"] > 5 or
                user_units["max"] - user_units["min"] > 8):
            warnings.append("SERVICE_COUNT_DRIFT")
    if idle and idle["min"] < 10:
        warnings.append("HIGH_HOST_CONTENTION")

    report = {
        "schema": "native-soak-report/1",
        "source": path,
        "label": meta.get("label"),
        "start_utc": meta.get("start_utc"),
        "end_utc": meta.get("end_utc"),
        "duration_s": duration,
        "sample_count": meta.get("samples"),
        "clk_tck": clk,
        "guest": meta.get("host=vm guest"),
        "kernel": meta.get("kernel"),
        "target_rules": meta.get("target_rules"),
        "processes": per_process,
        "canopy_cpu_5min_windows": cpu_windows,
        "system_idle_pct": idle,
        "system_running_units": sys_units,
        "user_running_units": user_units,
        "process_start_events": starts,
        "process_exit_events": exits,
        "sample_gaps_gt_120s": gaps,
        "target_process_coredumps": target_dumps,
        "system_service_coredumps": system_dumps,
        "journal_probe": journal,
        "verdict": "SOAK_WARN_" + "+".join(warnings) if warnings else "SOAK_STABLE_BOUNDED",
        "warnings": warnings,
        "not_run": ["24H_SOAK", "TRUE_LOW_END_HARDWARE", "RELEASE_ACCEPTANCE"],
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({k: report[k] for k in (
        "label", "start_utc", "end_utc", "duration_s", "sample_count",
        "verdict", "warnings", "not_run")}, indent=2, sort_keys=True))
    for proc in per_process:
        pss = proc["pss_kib"] or {}
        print("%-9s pid=%-6s PSS first/mean/last=%s/%s/%s KiB growth=%s%% CPU=%s%% ctx/s=%s" %
              (proc["role"], proc["pid"], pss.get("first"), pss.get("mean"),
               pss.get("last"), proc["pss_growth_pct"], proc["cpu_pct_of_one_core"],
               proc["ctx_per_s"]))
    print("system units min/max=%s/%s user units min/max=%s/%s idle%% min/mean=%s/%s" %
          (sys_units["min"] if sys_units else None, sys_units["max"] if sys_units else None,
           user_units["min"] if user_units else None, user_units["max"] if user_units else None,
           idle["min"] if idle else None, idle["mean"] if idle else None))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: native_soak_report.py RAW.tsv REPORT.json")
    main(sys.argv[1], sys.argv[2])
