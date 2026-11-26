# Linux resource measurement (read-only probe)

`tools/qa/linux_resource_probe.py` is a dependency-free, read-only collector for
Linux `/proc` resource evidence. It records PSS/RSS, CPU over a bounded
interval, wakeups when the kernel exposes a wakeup counter, and startup deltas
computed from timestamps supplied by the caller. It never starts, stops,
signals or writes to a measured process, and it does not use Windows working
set as a substitute for PSS.

## Status and evidence labels

- **SYNTHETIC** — the committed fixture tests in `tests/test_linux_resource_probe.py`.
  Every number in them comes from an invented `/proc` tree on the host Python
  interpreter; none is a Canopy runtime measurement.
- **LINUX_PROC_SCOPED** — output of a real run with `--source proc`. It is still
  only a scoped proc sample: no Mint guest, compositor, GPU, real desktop
  session or interactive visual state is attested by this tool.
- **NOT_RUN** — real five-minute Linux Mint shell-owned PSS, real desktop idle
  CPU, authoritative scheduler wakeups where `/proc/pid/sched` has no
  `nr_wakeups`, GPU/compositor cost, screen-reader behavior and automatic
  CI-on-guest acceptance. The report emits these as explicit `NOT_RUN` values;
  an unlisted item must never be read as measured.
- **Targets, not achievements** — the 200 MiB shell-owned PSS ceiling and the
  1% of one core average idle CPU from [quality gates](QUALITY.md) are
  engineering targets. The report's `targets.status` is always
  `TARGETS_NOT_ACHIEVEMENTS`; a low synthetic number is not attainment.
  See also the [Qt evidence gate](QT_PERFORMANCE_EVIDENCE_GATE.md).

## What is collected

| Field | Source | Notes |
| --- | --- | --- |
| `memory.samples.start/end[].pss_kib` | `/proc/<pid>/smaps_rollup`, falling back to summed `Pss:` from `smaps` | Null means no PSS counter; null is never coerced to zero. `pss_status` is `AVAILABLE`, `PARTIAL` or `NOT_AVAILABLE`. |
| `memory.samples.start/end[].rss_kib` | same files | RSS is not PSS and must not be substituted for it. |
| `memory.totals.pss_kib_peak` | both samples | Peak across the start and end snapshots, not a five-minute peak. |
| `cpu.total_percent_of_one_core` | two `/proc/<pid>/stat` snapshots | `ticks / clock_ticks_per_second / elapsed_seconds * 100`; process start ticks must match or the run fails closed on PID reuse. |
| `wakeups` | `/proc/<pid>/sched` `nr_wakeups` when present | Cumulative counter at sample end, not an interval delta. Context switches from `status` are recorded separately and explicitly **are not** relabeled as wakeups. |
| `startup.phases_ms` | caller-supplied timestamps | Deltas from `launch_request`; the tool does not instrument the launcher or attest timestamp provenance. |
| `scope` | caller-supplied JSON | Every measured PID must appear in `included_processes`; PIDs cannot appear in both included and excluded lists. |

All proc files are bounded (1 MiB each), regular-file only, and parsed
strictly. Malformed values, duplicate JSON keys, unbounded intervals (>300 s),
wrong types, short stat records and non-monotonic startup phases fail closed
with `MeasurementError`.

## Run it

From the repository root:

```sh
# Offline deterministic fixtures: no /proc access, no process interaction.
python3 -m unittest tests.test_linux_resource_probe -v

# Real Linux host, scoped evidence only. Supply the process scope explicitly.
python3 -m tools.qa.linux_resource_probe \
  --pid 1234 --proc-root /proc --source proc --session linux-host \
  --interval 5 --scope /absolute/path/to/scope.json \
  --startup /absolute/path/to/startup.json \
  --output /absolute/path/to/report.json
```

Scope file shape:

```json
{
  "included_processes": [
    {"pid": 1234, "label": "canopy-shell", "reason": "shell-owned"}
  ],
  "excluded_processes": [
    {"pid": 1500, "label": "cinnamon-shell", "reason": "existing desktop compositor"}
  ]
}
```

Startup file shape (monotonic seconds, caller-supplied):

```json
{"launch_request": 0.0, "process_spawn": 0.08, "first_frame": 0.42, "ready": 0.61}
```

Any report written under the proc root is refused, so a measurement run does
not mutate the tree it reads. With no `--output`, the JSON goes to stdout.

## Limits

- One short sample pair is not the five-minute idle acceptance measurement;
  no release readiness, Mint acceptance or visual approval is claimed.
- Process ownership is a caller declaration, not kernel-verified attribution.
  A compositor, desktop service or unrelated process must be listed under
  `excluded_processes` with a reason rather than silently dropped.
- No GPU, compositor cost, network, screen-reader or accessibility behavior is
  measured. Screen-reader behavior is `NOT_RUN`.
- `--session linux-mint-guest-unverified` records a caller claim only;
  `environment_attested` stays false and `acceptance.linux_mint` stays
  `NOT_RUN`. Collecting a genuine Mint guest sample requires a separate,
  independently verified guest protocol.
- This tool is evidence collection, not approval. It never reviews, approves
  or merges a pull request.
