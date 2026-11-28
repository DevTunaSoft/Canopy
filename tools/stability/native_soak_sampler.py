#!/usr/bin/env python3
"""Guest-side bounded native Plasma stability sampler (read-only).

Piped over the existing SSH forward:
    ssh -i "$KEY" -p 2223 canopy@127.0.0.1 'python3 - 1800 60 SOAK' \
      < tools/stability/native_soak_sampler.py > scratch/native_stability/raw/soak.tsv

Emits newline-delimited TSV on stdout. No guest file, package, service,
compositor or persistent setting is changed. Process identity is taken from
/proc/<pid>/cmdline and the observed starttime tick, never from sampled values.
`/proc/<pid>/sched` wakeup export is probed; when the kernel does not export
it, context switches from /proc/<pid>/status are the labelled proxy.

PR749 remediation (read-only changes only):
  * journal error keywords are matched against the *message body only*; the
    short-iso timestamp/hostname/unit prefix is stripped first, so a guest
    named ``canopy-plasma6`` can no longer inflate error totals.
  * a bounded per-sample ``unit_sample`` EVENT records the running unit names
    (capped, with a truncation flag) so COUNT drift can be decomposed without
    a second probe.  The ``S`` row column set is unchanged (schema /2).
  * helpers are importable; the collection loop runs only under __main__ so
    regression tests can exercise the parsing without touching the guest.
"""
import calendar
import datetime as dt
import json
import os
import platform
import re
import subprocess
import sys
import time

UNIT_NAME_CAP = 64

TARGET_RULES = (
    "argv0 basename in {startplasma-x11,kwin_x11,plasmashell} or "
    "startswith('canopy-classic'); exact argv0, no substring guessing"
)

# `journalctl -o short-iso` layout: TIMESTAMP HOSTNAME UNIT[PID]: MESSAGE
SHORT_ISO_PREFIX = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})\s+\S+\s+"
)
UNIT_TAG = re.compile(r"^[^:\s][^:]*?(?:\[\d+\])?:\s")

# Applied to the message body only (never to the hostname).
ERROR_PATTERN = re.compile(
    r"canopy|kwin|plasmashell|startplasma|segfault|SIGSEGV|SIGABRT|core dumped|soft lockup",
    re.IGNORECASE,
)


def utc_now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(*fields):
    print(*fields, sep=" ", flush=True)


def journal_message_body(line):
    """Strip the short-iso timestamp + hostname + unit tag from one line.

    The hostname (e.g. ``canopy-plasma6``) is *never* keyword-matched: doing so
    was the PR749 defect that inflated ``journal_system_errors_total`` to 132.
    Lines without a recognisable prefix are returned unchanged so no evidence
    is silently dropped.
    """
    body = SHORT_ISO_PREFIX.sub("", line.strip(), count=1)
    body = UNIT_TAG.sub("", body, count=1)
    return body.strip()


def matching_error_lines(stdout_text):
    """Return (matched_bodies, distinct_bodies) from journalctl short-iso text."""
    bodies = [journal_message_body(ln) for ln in stdout_text.splitlines()]
    matched = [b for b in bodies if b and ERROR_PATTERN.search(b)]
    return matched, list(dict.fromkeys(matched))


def target_pids():
    found = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as fh:
                argv0 = fh.read().split(b"\0", 1)[0].decode("utf-8", "replace")
        except OSError:
            continue
        base = os.path.basename(argv0)
        role = None
        if base in ("startplasma-x11", "kwin_x11", "plasmashell"):
            role = "shell:" + base
        elif base.startswith("canopy-classic"):
            role = "canopy"
        if role:
            found[pid] = (role, base)
    return found


def stat_fields(pid):
    with open("/proc/%d/stat" % pid) as fh:
        rest = fh.read().rsplit(") ", 1)[1].split()
    # index 0 == /proc stat field 3
    return {
        "utime": int(rest[11]),
        "stime": int(rest[12]),
        "starttime": int(rest[19]),
        "rss_kib": int(rest[21]) * 4,
    }


def pss_kib(pid):
    try:
        with open("/proc/%d/smaps_rollup" % pid) as fh:
            for line in fh:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return "NA"


def ctx_switches(pid):
    out = {"vol": "NA", "invol": "NA"}
    try:
        with open("/proc/%d/status" % pid) as fh:
            for line in fh:
                if line.startswith("voluntary_ctxt_switches:"):
                    out["vol"] = int(line.split(":", 1)[1].strip())
                elif line.startswith("nonvoluntary_ctxt_switches:"):
                    out["invol"] = int(line.split(":", 1)[1].strip())
    except OSError:
        pass
    return out


def wakeups(pid):
    try:
        with open("/proc/%d/sched" % pid) as fh:
            match = re.search(r"se\.nr_wakeups:(\d+)", fh.read())
        return int(match.group(1)) if match else "NA"
    except OSError:
        return "NA"


def system_ticks():
    with open("/proc/stat") as fh:
        for line in fh:
            if line.startswith("cpu "):
                vals = [int(v) for v in line.split()[1:]]
                total = sum(vals)
                idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
                return idle, total
    return "NA", "NA"


def running_procs():
    with open("/proc/stat") as fh:
        for line in fh:
            if line.startswith("procs_running"):
                return int(line.split()[1])
    return "NA"


def systemctl_units(scope):
    """Return (count, sorted_unit_names) or (None, None) on probe failure."""
    cmd = ["systemctl", "list-units", "--state=running", "--no-legend", "--plain"]
    if scope == "user":
        cmd.insert(1, "--user")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if out.returncode != 0:
            return None, None
        names = sorted({ln.split()[0] for ln in out.stdout.splitlines() if ln.strip()})
        return len(names), names
    except (OSError, subprocess.SubprocessError):
        return None, None


def unit_sample_event(scope, t, count, names, cap=UNIT_NAME_CAP):
    """Bounded per-sample unit membership; never truncates silently."""
    if names is None:
        return {"event": "unit_sample", "t": t, "scope": scope, "count": "NA",
                "units": [], "unit_cap": cap, "truncated": False,
                "status": "PROBE_UNAVAILABLE"}
    return {"event": "unit_sample", "t": t, "scope": scope, "count": count,
            "units": names[:cap], "unit_cap": cap,
            "truncated": len(names) > cap, "status": "OK"}


def journal_events(start_utc):
    """Return bounded, single-line summaries of errors since soak start."""
    result = {"journal_user_errors": [], "journal_system_errors": [],
              "coredumps": [], "errors": [],
              "journal_match_scope": "message_body_only",
              "journal_warning": "hostname prefix stripped before keyword match (PR749 fix)"}
    since_args = ["--since", "@%d" % calendar.timegm(dt.datetime.strptime(
        start_utc, "%Y-%m-%dT%H:%M:%SZ").timetuple())]
    for key, cmd in (
        ("journal_user_errors", ["journalctl", "--user", "-b", "--no-pager", "-q", "-p", "err", "-o", "short-iso"]),
        ("journal_system_errors", ["journalctl", "-b", "--no-pager", "-q", "-p", "err", "-o", "short-iso"]),
    ):
        try:
            proc = subprocess.run(cmd + since_args, capture_output=True, text=True, timeout=20)
            matched, distinct = matching_error_lines(proc.stdout)
            result[key] = matched[-12:]
            result[key + "_total"] = len(matched)
            result[key + "_distinct_total"] = len(distinct)
            if proc.returncode != 0:
                result["errors"].append("%s rc=%d" % (key, proc.returncode))
        except (OSError, subprocess.SubprocessError) as exc:
            result["errors"].append("%s: %s" % (key, type(exc).__name__))
    try:
        proc = subprocess.run(["coredumpctl", "list", "--no-pager"],
                              capture_output=True, text=True, timeout=20)
        recent = []
        start_dt = dt.datetime.strptime(start_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc)
        for line in proc.stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 4:
                continue
            try:
                when = dt.datetime.strptime(" ".join(parts[:3]),
                                            "%a %Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if when.replace(tzinfo=dt.timezone.utc) >= start_dt:
                recent.append(line.strip())
        result["coredumps"] = recent[-12:]
        result["coredump_total"] = len(recent)
        if proc.returncode != 0:
            result["errors"].append("coredumpctl rc=%d" % proc.returncode)
    except (OSError, subprocess.SubprocessError) as exc:
        result["errors"].append("coredumpctl: %s" % type(exc).__name__)
    return result


def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 1800
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    label = sys.argv[3] if len(sys.argv) > 3 else "SOAK"
    clk = os.sysconf("SC_CLK_TCK")
    start_mono = time.monotonic()
    start_utc = utc_now()

    emit("# schema=native-soak-sample/2")
    emit("# label=%s" % label)
    emit("# start_utc=%s" % start_utc)
    emit("# clk_tck=%s" % clk)
    emit("# guest=%s" % platform.node())
    emit("# kernel=%s" % platform.uname().release)
    emit("# target_rules=%s" % TARGET_RULES)
    emit("# unit_name_cap=%s" % UNIT_NAME_CAP)
    emit("# journal_match_scope=message_body_only")
    emit("# column_set: t_rel_s utc pid role comm starttime_ticks utime_ticks stime_ticks rss_kib pss_kib vol_ctx invol_ctx wakeups_or_NA sys_idle_ticks sys_total_ticks procs_running system_units user_units")

    seen = {}          # (pid, starttime) -> {"role", "first_t"}
    last_set = set()
    samples = 0
    while True:
        now = time.monotonic()
        elapsed = int(now - start_mono)
        targets = target_pids()
        idle, total = system_ticks()
        sys_count, sys_names = systemctl_units("system")
        user_count, user_names = systemctl_units("user")
        procs = running_procs()
        for pid, (role, base) in sorted(targets.items()):
            try:
                st = stat_fields(pid)
            except OSError:
                continue
            key = (pid, st["starttime"])
            if key not in seen:
                seen[key] = {"role": role, "first_t": elapsed}
                emit("EVENT %s" % json.dumps(
                    {"event": "process_start", "t": elapsed, "pid": pid,
                     "role": role, "starttime": st["starttime"]}, sort_keys=True))
            ctx = ctx_switches(pid)
            emit("S", elapsed, utc_now(), pid, role, base, st["starttime"],
                 st["utime"], st["stime"], st["rss_kib"], pss_kib(pid),
                 ctx["vol"], ctx["invol"], wakeups(pid), idle, total, procs,
                 sys_count if sys_count is not None else "NA",
                 user_count if user_count is not None else "NA")
        current = set(targets)
        for pid in sorted(last_set - current):
            emit("EVENT %s" % json.dumps(
                {"event": "process_exit", "t": elapsed, "pid": pid}, sort_keys=True))
        last_set = current
        for scope, count, names in (("system", sys_count, sys_names),
                                    ("user", user_count, user_names)):
            emit("EVENT %s" % json.dumps(
                unit_sample_event(scope, elapsed, count, names), sort_keys=True))
        samples += 1
        if elapsed >= duration:
            break
        time.sleep(max(0.0, min(interval, start_mono + elapsed + interval - time.monotonic())))

    end_utc = utc_now()
    emit("EVENT %s" % json.dumps({"event": "journal_probe", "t": elapsed,
                                  "since": start_utc, **journal_events(start_utc)}, sort_keys=True))
    emit("# samples=%s" % samples)
    emit("# elapsed_s=%s" % elapsed)
    emit("# end_utc=%s" % end_utc)


if __name__ == "__main__":
    main()
