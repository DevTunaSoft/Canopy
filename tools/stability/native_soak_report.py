#!/usr/bin/env python3
"""Summarise a native-soak TSV (native-soak-sample/2) into JSON facts.

Usage:
    python3 tools/stability/native_soak_report.py RAW.tsv REPORT.json \
        [--evidence-dir DIR] [--rerun-note TEXT]

Never synthesises missing data: NA stays null, NOT_RUN items are explicit.

PR749 remediation:
  * ``sample_count`` is an int, ``guest`` reads the correct ``# guest=`` key;
  * bounded per-sample ``unit_sample`` events are aggregated so SERVICE_COUNT_DRIFT
    can be decomposed (legacy raw without them is labelled NOT_RUN);
  * >120 s gaps are classified from *read-only* guest-journal / VirtualBox-log
    evidence into GUEST_STALL_PROVEN vs UNCLASSIFIED (never by inventing rows);
  * 5-minute CPU buckets carry explicit coverage caveats;
  * a legacy journal probe whose hostname inflated error totals is labelled
    unreliable instead of being silently trusted.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import statistics
import sys

STRING_COLS = {"utc", "role", "comm"}

COLS = ("t_rel_s utc pid role comm starttime_ticks utime_ticks stime_ticks "
        "rss_kib pss_kib vol_ctx invol_ctx wakeups_or_NA sys_idle_ticks "
        "sys_total_ticks procs_running system_units user_units").split()

BUCKET_S = 300
UNIT_OBSERVED_CAP = 256
EVIDENCE_EXCERPT_CAP = 3

CPU_BUCKET_CAVEATS = [
    "Buckets are fixed 300 s relative-time bins, not guest wall-clock aligned.",
    "cpu_pct_of_one_core divides by observed_span_s (first..last sample in the bucket), not by 300 s; "
    "edge buckets, NA probes and sampling gaps reduce coverage_pct.",
    "0.0000% means no CPU ticks were observed in that bucket's samples; it is not proof of zero CPU "
    "outside those samples.",
    "NA tick reads are excluded, never converted to zero.",
]

JOURNAL_ISO = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2}))\s+\S+\s+(.*)$")
VBOX_UPTIME = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.(\d{6})\s+(.*)$")
LOG_OPEN = re.compile(r"Log opened\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)")
SOFT_LOCKUP = re.compile(r"soft lockup", re.IGNORECASE)
VBOX_STALL = re.compile(r"catch-up|heartbeat|unresponsive|stall|watchdog", re.IGNORECASE)


def num(value):
    if value in ("NA", "", None):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


def as_int(value, default=0):
    parsed = num(value)
    return parsed if isinstance(parsed, int) else default


def summarize_series(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return {"min": min(vals), "max": max(vals),
            "mean": round(statistics.fmean(vals), 3),
            "first": vals[0], "last": vals[-1]}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_iso_utc(text):
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def load_raw(path):
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
    return meta, rows, events


def cpu_windows(rows, clk):
    """Bounded 5-minute buckets with honest coverage caveats."""
    windows = {}
    for row in rows:
        if row["role"] != "canopy":
            continue
        bucket = row["t_rel_s"] // BUCKET_S
        windows.setdefault(bucket, []).append(row)
    result = []
    for bucket, samples in sorted(windows.items()):
        samples.sort(key=lambda r: r["t_rel_s"])
        first, last = samples[0], samples[-1]
        span = max(1, last["t_rel_s"] - first["t_rel_s"])
        tick_vals = (first["utime_ticks"], first["stime_ticks"],
                     last["utime_ticks"], last["stime_ticks"])
        ticks = None
        if all(v is not None for v in tick_vals):
            ticks = (last["utime_ticks"] + last["stime_ticks"]
                     - first["utime_ticks"] - first["stime_ticks"])
        pct = round(100.0 * ticks / clk / span, 4) if ticks is not None else None
        result.append({
            "window_index": bucket,
            "start_s": first["t_rel_s"],
            "end_s": last["t_rel_s"],
            "nominal_window_s": BUCKET_S,
            "observed_span_s": span,
            "coverage_pct": round(100.0 * span / BUCKET_S, 1),
            "samples": len(samples),
            "cpu_pct_of_one_core": pct,
            "caveat": ("CPU%% is over observed samples only (%d/%d s); not a full-window "
                       "utilisation. No rows were synthesised to fill the bucket." %
                       (span, BUCKET_S)),
        })
    return result


def summarize_unit_events(events):
    """Aggregate bounded per-sample unit membership events."""
    out = {}
    for scope in ("system", "user"):
        evs = [e for e in events if e.get("event") == "unit_sample"
               and e.get("scope") == scope]
        if not evs:
            out[scope] = {"status": "NOT_RUN",
                          "reason": "no unit_sample events in raw TSV (legacy raw)"}
            continue
        names = sorted({n for e in evs for n in e.get("units", [])})
        caps = [e.get("unit_cap") for e in evs if e.get("unit_cap")]
        out[scope] = {
            "status": "OK",
            "samples": len(evs),
            "unit_cap": max(caps) if caps else None,
            "truncated_any": any(e.get("truncated") for e in evs),
            "probe_unavailable_samples": sum(1 for e in evs if e.get("status") != "OK"),
            "distinct_units_observed": len(names),
            "units_observed": names[:UNIT_OBSERVED_CAP],
            "units_observed_truncated": len(names) > UNIT_OBSERVED_CAP,
            "first_t_s": min(e.get("t", 0) for e in evs),
            "last_t_s": max(e.get("t", 0) for e in evs),
            "count_series": summarize_series([num(e.get("count")) for e in evs]),
        }
    return out


def legacy_journal_probe(journal):
    """A legacy probe matched keywords against the whole line incl. hostname."""
    if journal.get("journal_match_scope") == "message_body_only":
        return False
    stored = (journal.get("journal_system_errors", []) or []) + \
             (journal.get("journal_user_errors", []) or [])
    return any("canopy-plasma6" in ln for ln in stored)


def _evidence_scan(evidence_dir, start_dt, gap):
    """Read-only correlation of one gap with guest journal + VBox log files."""
    lo = start_dt + dt.timedelta(seconds=gap["from_s"] - 30)
    hi = start_dt + dt.timedelta(seconds=gap["to_s"] + 30)
    out = {"method": "read-only-file-scan", "no_rows_synthesised": True,
           "window_utc": [lo.strftime("%Y-%m-%dT%H:%M:%SZ"),
                          hi.strftime("%Y-%m-%dT%H:%M:%SZ")],
           "sources": {}, "guest_soft_lockup_lines": [], "vbox_stall_lines": []}
    if not evidence_dir or not os.path.isdir(evidence_dir):
        out["classification"] = "NOT_RUN_NO_READONLY_EVIDENCE"
        return out

    journal_path = os.path.join(evidence_dir, "journal_window.txt")
    if os.path.isfile(journal_path):
        with open(journal_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = JOURNAL_ISO.match(line.strip())
                if not match:
                    continue
                when = parse_iso_utc(match.group(1))
                if when is None or not (lo <= when <= hi):
                    continue
                if SOFT_LOCKUP.search(match.group(2)):
                    out["guest_soft_lockup_lines"].append(line.strip())
        out["sources"]["guest_journal"] = {
            "path": os.path.basename(journal_path), "sha256": sha256_file(journal_path)}

    vbox_path = os.path.join(evidence_dir, "vbox_correlation.txt")
    if os.path.isfile(vbox_path):
        with open(vbox_path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        opened = LOG_OPEN.search(text)
        log_open = parse_iso_utc(opened.group(1)) if opened else None
        if log_open:
            for line in text.splitlines():
                match = VBOX_UPTIME.match(line.strip())
                if not match:
                    continue
                secs = (int(match.group(1)) * 3600 + int(match.group(2)) * 60
                        + int(match.group(3)) + int(match.group(4)) / 1e6)
                when = log_open + dt.timedelta(seconds=secs)
                if lo <= when <= hi and VBOX_STALL.search(match.group(5)):
                    out["vbox_stall_lines"].append(line.strip())
        out["sources"]["vbox_log"] = {
            "path": os.path.basename(vbox_path), "sha256": sha256_file(vbox_path),
            "log_open_utc": opened.group(1) if opened else None}

    if not out["sources"]:
        out["classification"] = "NOT_RUN_NO_READONLY_EVIDENCE"
        out["basis"] = "no read-only evidence files found in supplied directory"
        return out

    if out["guest_soft_lockup_lines"] and out["vbox_stall_lines"]:
        out["classification"] = "GUEST_STALL_PROVEN"
        out["basis"] = "guest soft lockup + VirtualBox heartbeat/catch-up lag"
    elif out["guest_soft_lockup_lines"] or out["vbox_stall_lines"]:
        out["classification"] = "GUEST_STALL_PROVEN"
        out["basis"] = ("guest soft lockup" if out["guest_soft_lockup_lines"]
                        else "VirtualBox heartbeat/catch-up lag")
    else:
        out["classification"] = "UNCLASSIFIED_NO_READONLY_EVIDENCE"
        out["basis"] = "no matching read-only evidence in supplied window"

    for key in ("guest_soft_lockup_lines", "vbox_stall_lines"):
        out[key] = out[key][:EVIDENCE_EXCERPT_CAP]
    return out


def classify_gaps(gaps, start_utc, evidence_dir):
    start_dt = parse_iso_utc(start_utc) if start_utc else None
    if start_dt is None:
        return [{"from_s": g["from_s"], "to_s": g["to_s"], "delta_s": g["delta_s"],
                 "classification": "NOT_RUN_NO_START_UTC" } for g in gaps]
    return [dict(g, **_evidence_scan(evidence_dir, start_dt, g)) for g in gaps]


def build_report(path, meta, rows, events, evidence_dir, rerun_note):
    targets = {}
    for row in rows:
        key = (row["pid"], row["starttime_ticks"])
        targets.setdefault(key, []).append(row)

    clk = int(meta.get("clk_tck", "100") or 100)
    duration = as_int(meta.get("elapsed_s"), 0)
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

    sys_units = summarize_series([r["system_units"] for r in rows])
    user_units = summarize_series([r["user_units"] for r in rows])
    idle = summarize_series([
        (100.0 * r["sys_idle_ticks"] / r["sys_total_ticks"])
        if r["sys_total_ticks"] else None for r in rows])

    legacy_probe = legacy_journal_probe(journal)
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
    if legacy_probe:
        warnings.append("JOURNAL_ERROR_COUNT_UNRELIABLE_LEGACY_HOSTNAME_MATCH")

    report = {
        "schema": "native-soak-report/2",
        "source": path,
        "label": meta.get("label"),
        "start_utc": meta.get("start_utc"),
        "end_utc": meta.get("end_utc"),
        "duration_s": duration,
        "sample_count": as_int(meta.get("samples"), 0),
        "clk_tck": clk,
        "guest": meta.get("guest"),
        "kernel": meta.get("kernel"),
        "target_rules": meta.get("target_rules"),
        "processes": per_process,
        "canopy_cpu_5min_windows": cpu_windows(rows, clk),
        "cpu_bucket_caveats": CPU_BUCKET_CAVEATS,
        "system_idle_pct": idle,
        "system_running_units": sys_units,
        "user_running_units": user_units,
        "unit_membership": summarize_unit_events(events),
        "process_start_events": starts,
        "process_exit_events": exits,
        "sample_gaps_gt_120s": gaps,
        "sample_gap_classification": classify_gaps(gaps, meta.get("start_utc"), evidence_dir),
        "target_process_coredumps": target_dumps,
        "system_service_coredumps": system_dumps,
        "journal_probe": journal,
        "journal_probe_quality": {
            "legacy_hostname_inflation": legacy_probe,
            "journal_match_scope": journal.get("journal_match_scope", "whole_line_legacy"),
            "note": ("Legacy probe matched keywords against the whole short-iso line, "
                     "including hostname canopy-plasma6; error totals are not trustworthy. "
                     "Coredump totals are independent and remain valid." if legacy_probe
                     else "Message-body-only keyword matching."),
        },
        "soak_rerun": {
            "status": "NOT_RUN",
            "reason": rerun_note or ("NOT_RUN: exclusive quiesced guest not demonstrated; "
                                     "no fresh soak was executed."),
            "vm_actions": "read-only only; no VM state change",
        },
        "verdict": "SOAK_WARN_" + "+".join(warnings) if warnings else "SOAK_STABLE_BOUNDED",
        "warnings": warnings,
        "not_run": ["24H_SOAK", "TRUE_LOW_END_HARDWARE", "RELEASE_ACCEPTANCE",
                    "SOAK_RERUN_EXCLUSIVE_QUIESCED_GUEST", "MERGE", "APPROVAL"],
    }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw")
    parser.add_argument("out")
    parser.add_argument("--evidence-dir", default=None,
                        help="directory with read-only journal_window.txt / vbox_correlation.txt")
    parser.add_argument("--rerun-note", default=None,
                        help="explicit reason string for the NOT_RUN soak rerun")
    args = parser.parse_args(argv)

    meta, rows, events = load_raw(args.raw)
    report = build_report(args.raw, meta, rows, events, args.evidence_dir, args.rerun_note)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({k: report[k] for k in (
        "label", "start_utc", "end_utc", "duration_s", "sample_count",
        "guest", "verdict", "warnings", "not_run", "soak_rerun")}, indent=2, sort_keys=True))
    for proc in report["processes"]:
        pss = proc["pss_kib"] or {}
        print("%-9s pid=%-6s PSS first/mean/last=%s/%s/%s KiB growth=%s%% CPU=%s%% ctx/s=%s" %
              (proc["role"], proc["pid"], pss.get("first"), pss.get("mean"),
               pss.get("last"), proc["pss_growth_pct"], proc["cpu_pct_of_one_core"],
               proc["ctx_per_s"]))
    sys_units, user_units = report["system_running_units"], report["user_running_units"]
    idle = report["system_idle_pct"]
    print("system units min/max=%s/%s user units min/max=%s/%s idle%% min/mean=%s/%s" %
          (sys_units["min"] if sys_units else None, sys_units["max"] if sys_units else None,
           user_units["min"] if user_units else None, user_units["max"] if user_units else None,
           idle["min"] if idle else None, idle["mean"] if idle else None))
    for gap in report["sample_gap_classification"]:
        print("gap %s->%s (%ss): %s" % (gap["from_s"], gap["to_s"], gap["delta_s"],
                                        gap["classification"]))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: native_soak_report.py RAW.tsv REPORT.json "
                 "[--evidence-dir DIR] [--rerun-note TEXT]")
    main()
