# PR #749 1-hour native soak WARN — incident diagnosis (read-only)

Status: **DIAGNOSED — GUEST/SYSTEM INCIDENT, NOT CANOPY-CAUSED. NO INTEGRATION.**
No merge, approval, PR promotion, VM state change, guest service/package change,
snapshot, revert or destructive action was performed. All VM access was read-only
SSH (`canopy@127.0.0.1:2223`) plus reads of on-disk VirtualBox logs.

- Subject: PR #749 head `449e39e7bd00af24aec50a05c70340c0b10a8120`, branch
  `product/native-stability-smoke-20261127`, directive SHA `1fba4b1e` (cap 8),
  soak window `2026-11-28T06:25:56Z`–`07:26:55Z` (3659 s observed).
- Diagnosis branch/worktree: `diagnosis/pr749-soak-20261128`,
  `C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-pr749-diagnosis`.
- Owned paths only: `docs/NATIVE_STABILITY_INCIDENT.md`, `scratch/pr749_incident/**`.

## 1. Exact source of the WARN

`SOAK_WARN_CRASH_OR_ERROR_EVENT+SAMPLING_GAP+SERVICE_COUNT_DRIFT` is produced
*after collection* by `tools/stability/native_soak_report.py`, not by a Canopy
runtime detector:

| Warning | Generating condition | Evidence |
| --- | --- | --- |
| `CRASH_OR_ERROR_EVENT` | `coredump_total=8` OR `journal_system_errors_total=132` OR `journal_user_errors_total>0` (report.py lines 143–145) | single `EVENT journal_probe` emitted at `t=3659` (`07:26:55Z`) by the sampler after the last sample; parsed into `soak.json` lines 80–113 |
| `SAMPLING_GAP` | two instants separated by >120 s (report.py lines 104–106) | t `1654→1833` (179 s), `2278→2819` (541 s), `soak.json` lines 250–260 |
| `SERVICE_COUNT_DRIFT` | running system units max−min >5 (48→54 = 6) (report.py lines 150–153) | `system_running_units` first/min 48, max 54, last 52, mean 50.06 |

The probe that supplied the crash warning is the sampler's terminal
`journal_events()` call: `coredumpctl list --no-pager` (timestamps >= soak start)
and `journalctl -b -p err -o short-iso --since @1795847156`. It is one aggregate
probe at the end of the soak, not an in-window crash signal from Canopy.

### Report-tool defect found (does not create the coredumps)

`native_soak_sampler.py` line 149 matches `canopy|kwin|...` against the **whole
journal line**, including hostname `canopy-plasma6`. Replaying the exact query
and window read-only gives 271–273 error lines, of which **exactly 132** match
the hostname; that is the report's `journal_system_errors_total=132`. The number
is therefore a hostname false-positive subset (mostly `systemd-coredump`
backtrace frames and rsyslog TTY warnings), not 132 distinct crashes. The
`coredumpctl` count of 8 is independent and real; the WARN would still fire from
those 8. User errors 0 is likewise only what survived the same filter.

## 2. The 8 service coredumps — exact time, source, cause

All eight are `SIGABRT`, `inaccessible`, guest system services (no Canopy target):

| UTC (coredumpctl) | PID | Service | Journal cause |
| --- | --- | --- | --- |
| 06:56:32 | 337 | `/usr/lib/systemd/systemd-journald` | watchdog timeout at 06:56:30, `Killing process 337 ... SIGABRT` |
| 06:56:33 | 386 | `/usr/bin/udevadm` (systemd-udevd) | watchdog at 06:56:32, killed with SIGABRT |
| 06:56:33 | 750 | `/usr/lib/systemd/systemd-logind` | watchdog at 06:56:30, killed with SIGABRT |
| 06:56:33 | 385 | `/usr/lib/systemd/systemd-resolved` (uid 989) | watchdog at 06:56:32, killed with SIGABRT |
| 07:12:57 | 67719 | `systemd-journald` | watchdog at 07:12:55, killed with SIGABRT |
| 07:12:57 | 67863 | `systemd-udevd` | watchdog at 07:12:56, killed with SIGABRT |
| 07:12:58 | 68009 | `systemd-resolved` | watchdog at 07:12:56, killed with SIGABRT |
| 07:12:58 | 66280 | `systemd-logind` | watchdog at 07:12:56, killed with SIGABRT |

`journalctl` also shows `snapd.service: Watchdog timeout (limit 5min)!` and
`Killing process 747 (snapd) with signal SIGABRT` at 07:12:56, but no ninth
coredump was listed. Both waves ended in `Failed with result 'watchdog'` and
scheduled restarts; journald reported
`system.journal corrupted or uncleanly shut down, renaming and replacing` after
each wave (06:56:32, 07:12:56; user journal at 07:13:20).

**Root cause (proven from guest kernel and VirtualBox logs, read-only): guest-wide
CPU scheduling stalls / kernel soft lockups.** Guest kernel lines:
`watchdog: BUG: soft lockup - CPU#0 stuck for 26s ... [swapper/0]` at 06:50:54,
repeated 06:51:24, 06:51:53, 06:52:31, 06:53:01, 06:53:31; then
`CPU#1 stuck for 167s! [unattended-upgr:66146]` at 06:56:32 and
`CPU#0 stuck for 453s! [swapper/0:0]` at 07:12:56. Tainted `[L]=SOFTLOCKUP`.
The stalled task name `unattended-upgr:66146` ties the first episode to guest
unattended-upgrade/apt work (`apt-daily-upgrade.service` started 06:47:37);
the second is idle-thread starvation. Systemd's 3-minute watchdogs expired
because the services could not be scheduled, so systemd itself sent SIGABRT.
This is guest/system noise amplified by host-level VM scheduling lag, not a
Canopy crash or a Canopy-induced service failure.

## 3. Sampling gaps — cause corrected

The committed doc's `INFERRED` explanation ("`systemctl` unit-count probe can
stall while journald is unhealthy") is **not supported**; independent logs show
the whole guest stopped making progress:

- Gap A: last sample t=1654 at 06:53:30/31Z → next t=1833 at 06:56:30Z (179 s).
  Guest journal has no entries 06:53:31→06:56:32 (181 s). VirtualBox log
  (VM log opened 04:00:20.2816957Z; uptime 02:56:10.732968 = 06:56:29.44Z)
  records `TM: Giving up catch-up attempt at a 208.7 s lag` and
  `Guest seems to be unresponsive. Last heartbeat received 178 seconds ago`
  → last heartbeat 06:53:30.95Z. Exact match to the sampler and journal gaps.
- Gap B: t=2278 at 07:03:54/55Z → t=2819 at 07:12:55/56Z (541 s).
  Guest journal gap 07:04:49→07:12:56 (487 s), with soft lockup reports at
  07:04:45 and 07:12:56. VirtualBox uptime 03:12:36.327812 = 07:12:55.04Z
  records `TM: Giving up catch-up attempt at a 500.5 s lag` and heartbeat gone
  483.3 s → last heartbeat 07:04:51.72Z. Exact match.
- VirtualBox log shows no `Changing the VM state` after the initial RUNNING:
  no pause/save/snapshot/revert during the soak. The gaps are scheduling
  stalls of the entire guest, consistent with the kernel soft lockups and
  host-side catch-up lag; an isolated `systemctl` timeout (8 s per probe in the
  sampler) cannot explain 179 s or 541 s. No rows were synthesised.

## 4. Service count components (48 / 54 / 52)

The sampler stored only aggregate `systemctl list-units --state=running`
**counts**, not unit names; exact per-unit membership at each instant is
therefore `PARTIAL` (journal-attributed), not a complete census.

- **48** at t=0 (06:25:56Z) — steady guest baseline; user units separately 53.
- 49 from 06:48:07Z after `apt-daily-upgrade.service` started at 06:47:37
  (guest package maintenance, unrelated to Canopy). `NA` at 06:49:24 and user
  `NA` at 06:51:53 are probe timeouts during the lockup episodes.
- 51 at 06:56:30Z, then **54 max** at 06:57:29Z — first coredump wave created
  transient `systemd-coredump@92/93/94-*.service`,
  `drkonqi-coredump-processor@92/93/94-*.service`, and
  `apport-coredump-hook@*.service`; additionally `user@107.service`,
  `session-1013.scope` and `packagekit.service` started 06:56:38–06:57:09.
  These transient crash-handler/session/package units are the drift source.
- 52 at 07:01:54Z and at the 07:26:55Z end — most transient handlers had
  deactivated; the second wave produced three more `systemd-coredump@95/96/97`
  and `drkonqi-coredump-processor@95/96/97` units at 07:12:56, which were gone
  again by 07:13:56; later small changes include `snapd.service`,
  `systemd-timedated.service`, `packagekit.service` restarts and
  `avahi-daemon.service` at 07:26:13.
- No Canopy process, scope, unit or file appears in any of these transitions.
  `SERVICE_COUNT_DRIFT` is a guest churn metric, not a Canopy regression.

## 5. Canopy attribution

- Four target PIDs/identities unchanged: 4656 `startplasma-x11`, 5384 `kwin_x11`,
  5422 `plasmashell`, 5667 `canopy-classic`; `process_start` after t=0 = 0,
  `process_exit` = 0, `target_process_coredumps` = [].
- `canopy-classic` PID 5667: CPU ticks delta **0**, voluntary+involuntary
  context-switch delta **0**, PSS 128124→124342 KiB (−2.95 %) over 51 samples;
  all 12 five-minute CPU windows 0.0000 %. It was not executing during the
  lockups and cannot plausibly have caused them.
- Guest journal errors matching the real crash chain name only systemd services,
  kernel, dbus/rsyslog/snapd; no Canopy invocation in the crash path.
- Verdict: **GUEST_SYSTEM_NOISE / HOST_VM_SCHEDULING_STALL**, NOT Canopy-caused.
  The WARN is a valid data-quality alert about the guest, not a stability
  failure of PR #749's target processes. It is still not evidence of stability.

## 6. Bounded remediation (proposed, not executed) and explicit NOT_RUN

Proposed, bounded and reversible, requiring a fresh run rather than a merge:

1. Fix `native_soak_sampler.py` journal pattern to match only the message body
   after the hostname and count distinct events, so hostname `canopy-plasma6`
   cannot inflate error totals; add a regression fixture. Do not change the
   committed raw logs — regenerate a new report from unchanged bytes.
2. Record bounded per-sample unit names (e.g. first 64 running units, hashed or
   capped) so `SERVICE_COUNT_DRIFT` can be decomposed without a second probe.
3. Add a read-only VM/VBox heartbeat and guest `soft lockup` classifier to the
   report so gaps become `GUEST_STALL_PROVEN` instead of `INFERRED`; do not
   synthesise rows to fill gaps.
4. Rerun the 1-hour soak only on an exclusively owned, quiesced guest (no
   unattended-upgrade/apt activity, no sibling agent builds) and require zero
   soft lockups, zero coredumps and no >120 s gaps before using it as evidence.

`NOT_RUN` for this diagnosis and still open for PR #749: 24-hour stability,
clean Canopy-free serialized A/B, low-end hardware, Linux Mint guest, hardware
GPU path, automatic CI-on-guest, wakeup counters (kernel does not export them),
owner visual acceptance, integration, merge and approval. No destructive VM
action, no guest package/service/config change and no PR write was performed.

## 7. Evidence index (verified SHA-256 of current bytes)

| Path (relative to worktree) | SHA-256 | Notes |
| --- | --- | --- |
| `scratch/pr749_incident/committed/scratch__native_stability__raw__soak.tsv` | `75c6a558de4ebdd6f21b2e13e4e99fd4b674c7efa8734448248102e7662b8c39` | committed raw samples, 220 lines |
| `scratch/pr749_incident/committed/scratch__native_stability__raw__soak.json` | `3a24fa0ee18799d002eb0e8cbc3b27fda73303935311bd5afbd21496ea09f597` | committed machine verdict |
| `scratch/pr749_incident/vm/journal_window.txt` | `d31594472e5144cc41bea8d5f99ba4ada03baed45147214c1d176f9144fafcd6` | read-only guest journal 06:50–07:15:30Z |
| `scratch/pr749_incident/vm/systemd_units_window.txt` | `58b0b61161128081be9bfb57192c8a3d66b77bf2d7181119aa589d60746b2a31` | read-only systemd[1] unit events 06:25–07:27Z |
| `scratch/pr749_incident/vm/vbox_correlation.txt` | `b33854a8e6e83c358b663af8c77747853d476df3dd462d58a75fdb6f246325d5` | VBox log header, heartbeat/catch-up/state lines |
| `scratch/pr749_incident/vm/err_replay.txt` | `f6dbfdab34c1b9f8660adbf6dbc2ec40b59e7703d7c65cbe8cafa3983612c7d0` | exact `p=err` replay; 132 hostname matches of 271 total |

`SYNTHETIC`: none. All figures above are from committed bytes or read-only
guest/VBox logs; inference is labelled where the raw sampler cannot prove it.
