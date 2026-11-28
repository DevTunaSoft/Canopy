# Native Plasma 6 M5 bounded stability/soak smoke (60 min)

Status: **NATIVE RUNTIME (SCOPED_ON_GUEST_RUNTIME)** for every `/proc`,
`journalctl` and `coredumpctl` figure below. Items not observed are labelled
`NOT_RUN`. No figure is extrapolated, synthesised or carried over from a
sibling agent's measurement. The bounded soak is complete; the 24-hour
requirement is **NOT_RUN**.

## 1. Scope, ownership and serialization

- Directive SHA `79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083`
  (cap 8; heavy VM work serialized with other product agents).
- Base: `ec910d7a7275296ecbc8b5e5c459d356205165d1`; branch
  `product/native-stability-smoke-20261127`; worktree
  `C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-stability-20261127`.
- Owned paths on this branch: the full delta vs `ec910d7a` is **32 files**
  (`git diff --name-only ec910d7a..f8cbe123`): `tools/stability/**` (3),
  `docs/NATIVE_STABILITY_SMOKE.md`, `docs/NATIVE_STABILITY_REMEDIATION.md`,
  `scratch/native_stability/**` (18), `scratch/pr749_incident/**` (5),
  `tests/fixtures/native_soak/**` (3) and
  `tests/test_native_soak_remediation.py` (1). This supersedes the shorter
  three-glob owned-path list in the PR body. No shared QML, source, asset,
  config or packaging file was edited.
- VM `Canopy-Test-Plasma6` (UUID `3aecd840-4dd6-4481-913f-64a289da406d`),
  VirtualBox 7.2.22, 2 vCPU / 4096 MiB, Ubuntu guest kernel
  `7.0.0-14-generic`, X11 Plasma session, `DISPLAY=:0`. Access via the
  pre-existing NAT SSH forward `127.0.0.1:2223`, user `canopy`, pre-existing
  scratch Ed25519 key (key material never committed). No VM start/stop,
  snapshot/revert, package, service, compositor or persistent setting change.
- Serialization evidence: guest preflight at `2026-11-28T06:25:54Z` showed
  3 users, load average `0.15, 0.41, 0.34`, the four target PIDs and no other
  agent's build/harness process. One sampler session only. Later contention
  and guest service failures are recorded in §4 rather than hidden.
- Time-box: requested 3600 s, observed **3659 s** (`06:25:56Z`–`07:26:55Z`,
  60 min 59 s), 51 sample instants / 204 sample rows, 60 s nominal interval.

## 2. Exact commands run

From the worktree root, with `KEY` pointing at the pre-existing scratch key:

```sh
# Short tool validation (not stability evidence):
ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 \
  -o ServerAliveInterval=30 -p 2223 canopy@127.0.0.1 'python3 - 12 5 PILOT' \
  < tools/stability/native_soak_sampler.py > scratch/native_stability/raw/pilot.tsv 2> scratch/native_stability/raw/pilot.err
ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 \
  -o ServerAliveInterval=30 -p 2223 canopy@127.0.0.1 'python3 - 12 5 PILOT2' \
  < tools/stability/native_soak_sampler.py > scratch/native_stability/raw/pilot2.tsv 2> scratch/native_stability/raw/pilot2.err
python3 tools/stability/native_soak_report.py scratch/native_stability/raw/pilot2.tsv scratch/native_stability/raw/pilot2.json

# Final bounded soak (exact runner invocation):
DURATION=3600 INTERVAL=60 LABEL=NATIVE_SOAK_60M bash tools/stability/run_native_soak.sh

# Runner's internal sampler and report commands (also in soak.meta):
ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -p 2223 canopy@127.0.0.1 \
  'python3 - 3600 60 NATIVE_SOAK_60M' \
  < tools/stability/native_soak_sampler.py \
  > scratch/native_stability/raw/soak.tsv 2> scratch/native_stability/raw/soak.err
python3 tools/stability/native_soak_report.py \
  scratch/native_stability/raw/soak.tsv scratch/native_stability/raw/soak.json

cd scratch/native_stability/raw && sha256sum -c SHA256SUMS.txt
cd ../.. && sha256sum -c scratch/native_stability/TOOLS_SHA256SUMS.txt
```

The first 12 s PILOT aborted in the journal-probe step (a naive/aware
datetime comparison); the fault was fixed before PILOT2 and the final run.
Only PILOT2 and the final soak use the committed sampler logic. The report
tool was extended after collection to classify gaps and core dumps; it was
re-run against the **unchanged** raw `soak.tsv`, and its final bytes are
hashed in the tool manifest.

Sampler signals: `/proc/<pid>/stat` (utime+stime at `CLK_TCK=100`,
starttime tick for identity), `/proc/<pid>/smaps_rollup` (`Pss`, `Rss`),
`/proc/<pid>/status` (voluntary/nonvoluntary context switches), `/proc/stat`
(system idle ticks, `procs_running`), `systemctl list-units --state=running`,
`journalctl -b --user --since @start` and `coredumpctl list`. Process set is
selected by exact `/proc/<pid>/cmdline` argv0 role, never by substring
guessing. Kernel `se.nr_wakeups` was **not exported** in any sample, so all
wakeup figures below are `NOT_RUN`; context-switch deltas are the labelled
proxy, not wakeup counts.

## 3. Measurements (NATIVE RUNTIME, scoped)

| PID / role | PSS first / mean / last (KiB) | PSS growth | CPU (% of one core, whole soak) | ctx switches/s | Wakeups |
| --- | --- | --- | --- | --- | --- |
| 4656 `startplasma-x11` | 5,377 / 5,377 / 5,377 | 0 (0.0 %) | 0.0000 | 0.000 | NOT_RUN (no export) |
| 5384 `kwin_x11` | 138,401 / 127,194 / 110,221 | −28,180 (−20.36 %) | 0.7467 | 29.139 | NOT_RUN (no export) |
| 5422 `plasmashell` | 457,361 / 453,017 / 446,204 | −11,157 (−2.44 %) | 0.0014 | 0.000 | NOT_RUN (no export) |
| 5667 `canopy-classic` | 128,124 / 126,680 / 124,342 | −3,782 (−2.95 %) | 0.0000 | 0.000 | NOT_RUN (no export) |

- Canopy Classic's CPU ticks did not change in any observed 5-minute window:
  all 12 windows report `0.0000 %` of one core **over sampled instants only**
  (CPU gap-coverage caveat below). Its voluntary and nonvoluntary
  context-switch counters also did not change over the full hour
  (2,461 / 2,634 at both ends). PSS ended 3,782 KiB (−2.95 %) below its first
  sample (128,124 → 124,342 KiB); the raw 51-sample series has 5 small upward
  steps, so the decline is **net, not monotonic**. No Canopy memory growth is
  observed over 61 minutes; monotonic PSS decrease is not claimed.
- The declining `kwin_x11` PSS (−20.36 %) and fluctuating shell values are
  not attributable to Canopy: other agents and guest services were active in
  the shared VM. Treat these as scoped observations, not a clean A/B.
- System idle fraction derived from `/proc/stat` was 86.48 %–89.14 %
  (mean 88.01 %) of both vCPUs' time during sampled instants. This does not
  cover the two sampling gaps in §4.
- CPU bucket caveat (from the regenerated report's `cpu_bucket_caveats`): the
  12 buckets are fixed 300 s relative-time bins and `cpu_pct_of_one_core`
  divides by `observed_span_s`, not by 300 s. Sample coverage ranged from
  0.3 % (1/300 s) to 89.0 % (267/300 s); buckets 5 (127/300 s), 7 (120/300 s)
  and 9 (180/300 s) are shortened by the two gaps in §4. `0.0000 %` means no
  CPU ticks were observed in that bucket's samples, **not** proof of zero CPU
  outside them. `NA` tick reads were excluded, never zeroed, and no rows were
  synthesised to fill a bucket.

## 4. Crashes, service counts and sampling gaps

- Target processes: **no restart and no exit** for any of the four PIDs
  (`process_start` after t=0: 0; `process_exit`: 0). Target-binary core dumps:
  **0**.
- Guest system service core dumps during the soak: **8** (all
  `SIGABRT`, `inaccessible`): `systemd-journald` at 06:56:32 and 07:12:57,
  `udevadm` at 06:56:33 and 07:12:57, `systemd-logind` at 06:56:33 and
  07:12:58, `systemd-resolved` at 06:56:33 and 07:12:58. The legacy journal
  probe reported 132 system "errors" in the window; remediation re-labels that
  total `JOURNAL_ERROR_COUNT_UNRELIABLE_LEGACY_HOSTNAME_MATCH` because the
  whole-line match counted the hostname `canopy-plasma6` inside
  `systemd-coredump` backtraces. **132 is not a trustworthy error count** and
  is not reused as evidence here. The watchdog line at 07:12:55 is
  `systemd-journald.service: Watchdog timeout (limit 3min)!`; user journal
  errors: 0. The 8 coredumps come from an independent probe and remain valid.
  These are guest-service failures, **not** Canopy or shell-process crashes;
  no causal attribution to Canopy is claimed.
- Running systemd units: system 48 first / 50.06 mean / 54 max / 52 last;
  user 53 throughout. The +4 system-unit drift and the service crashes are
  recorded as `SERVICE_COUNT_DRIFT` and `CRASH_OR_ERROR_EVENT` warnings.
- Sampling gaps (no invented rows): `1654 s → 1833 s` (179 s) and
  `2278 s → 2819 s` (541 s). Both coincide with the systemd-journald
  watchdog/core-dump episodes. Read-only guest/VBox evidence (kernel `soft
  lockup` lines plus VirtualBox heartbeat/catch-up lag aligned via `Log
  opened`) classifies **both** gaps `GUEST_STALL_PROVEN`; see §7 and
  `scratch/native_stability/raw/soak_remediated.json`. The earlier `INFERRED`
  "sampler `systemctl` probe stalled" story is **superseded and unproven**,
  not a Canopy root cause. No rows were synthesised for either gap. The soak
  duration is the observed wall/monotonic span (3659 s), not 51 × 60 s.

## 5. Limits and verdict

- `NATIVE RUNTIME` / `SCOPED_ON_GUEST_RUNTIME`: the PSS/CPU/context-switch,
  unit-count and journal observations on the shared X11 Plasma 6 guest.
- `NOT_RUN`: **24 h stability** (only 3659 s observed), true low-end hardware
  (this is a modest 2 vCPU / 4 GiB virtual guest, not a low-end device),
  wakeup counters (kernel export absent), clean Canopy-free serialized A/B,
  Linux Mint guest, hardware GPU path, automatic CI-on-guest, owner visual
  acceptance, merge/release. `SYNTHETIC`: none.
- Machine verdict in the legacy `scratch/native_stability/raw/soak.json`:
  `SOAK_WARN_CRASH_OR_ERROR_EVENT+SAMPLING_GAP+SERVICE_COUNT_DRIFT`. The
  regenerated `scratch/native_stability/raw/soak_remediated.json` keeps a WARN
  and adds `+JOURNAL_ERROR_COUNT_UNRELIABLE_LEGACY_HOSTNAME_MATCH`; both are
  byte-stable reports over the same unchanged raw TSV. No target-process
  restart or growth was observed, so this is **not** a Canopy-target failure;
  it is a scoped stability smoke with real guest service degradation and two
  `GUEST_STALL_PROVEN` gaps. M5 24-hour stability and low-end hardware evidence
  remain open.
- Engineering target context (targets, not acceptance): Canopy's 0.0000 %
  idle CPU met the ≤1 % target; its ~124–128 MiB incremental PSS was within
  the ≤200 MiB target but above the <100 MiB aspirational target. No release
  or visual approval is implied.
- No merge, no self-approval, no ready-for-merge promotion. DRAFT PR only.

## 6. Artifact index

- `scratch/native_stability/raw/soak.tsv` — 204 sample rows + events/headers.
- `scratch/native_stability/raw/soak.err` — empty (sampler rc=0).
- `scratch/native_stability/raw/soak.meta` — exact commands, launch/end UTC, rc.
- `scratch/native_stability/raw/preflight.txt` — VM state, guest baseline,
  coredump baseline, host snapshot.
- `scratch/native_stability/raw/soak.json` and `report_stdout.txt` — generated
  report; `report_stderr.txt` empty.
- `scratch/native_stability/raw/pilot.tsv`, `pilot2.tsv` — tool validation only.
- `scratch/native_stability/raw/SHA256SUMS.txt` and
  `scratch/native_stability/TOOLS_SHA256SUMS.txt` — byte-exact manifests.
- `scratch/native_stability/CLAIM.md` — claim, ownership, serialization,
  time-box.

## 7. Post-diagnosis remediation (no promotion)

The WARN in this document was diagnosed from read-only guest/VBox evidence as
guest soft-lockup/package noise, not a Canopy failure (`39ad2835`). The
sampler/report defects found there are fixed on this branch; see
`docs/NATIVE_STABILITY_REMEDIATION.md` and
`scratch/native_stability/raw/soak_remediated.json`. The original raw bytes are
unchanged; the regenerated report keeps a `SOAK_WARN_...` verdict, marks the
legacy hostname-inflated error count unreliable, proves both >120 s gaps from
read-only evidence, and labels the exclusive-guest 1 h rerun `NOT_RUN`. There is
still no READY promotion, merge or approval. §4 above now carries these
  same labels (legacy 132 unreliable; both gaps `GUEST_STALL_PROVEN`), so §4
  and this section agree; no figure in either section relies on the legacy
  hostname-inflated error count.
