# Native Plasma 6 vs Canopy Classic: 5-minute idle resource baseline (M5)

Status: **NATIVE RUNTIME (SCOPED_ON_GUEST_RUNTIME)** for all `/proc`-derived
numbers in this document. Items that could not be instrumented in this session
are marked `NOT_RUN` explicitly. No synthesis, no extrapolation, no fabricated
RSS; every figure below is computed from the raw TSV/JSON artifacts listed at
the end and re-computable with the committed tools.

## 1. Scope and method

- Directive SHA `79e30d79` (cap 8, 5 active product agents), M5.
- Exact base: `ec910d7a7275296ecbc8b5e5c459d356205165d1`
  (`integration/canopy-plasma6-20261127` tip at claim time).
- Owned paths only: `tools/perf/**`, this document, `scratch/native_perf/**`.
  No shared prototype, QML, visual, asset or compiled-input file was edited.
- Subject: existing `Canopy-Test-Plasma6` VM (Oracle VirtualBox 7.2.22,
  UUID `3aecd840-4dd6-4481-913f-64a289da406d`, 2 vCPU / 4096 MiB, X11 Plasma
  session on `DISPLAY=:0`). Access: pre-existing NAT SSH forward
  `127.0.0.1:2223` with the pre-existing scratch Ed25519 key, guest user
  `canopy`. No VM start/stop/snapshot/revert, no package, service, desktop
  entry, compositor or persistent setting change.
- Requested workload: two 300-second idle desktop runs on the same guest,
  each with a **requested** 5-second sampling interval. The `/proc` walk took
  ~5 s per pass, so the realised interval was ~10 s. The committed report
  parsed **30 sample instants / 120 rows** for `STOCK_PLASMA6` (302 s) and
  **44 sample instants / 176 rows** for `CANOPY_CLASSIC` (311 s): **74
  instants / 296 rows total**. The earlier "61 sample instants" wording was
  wrong and is corrected here. The stock TSV additionally contains 120
  malformed `S <n>` continuation lines that the report skips by design; those
  raw bytes are retained unchanged and are not counted as samples.
  `STOCK_PLASMA6` = shell-owned set `startplasma-x11`, `kwin_x11`,
  `plasmashell`. `CANOPY_CLASSIC` = the same shell set plus the Canopy Classic
  process tree. Incremental consumption = Canopy process set measured in the
  second run, with the stock shell delta reported separately so drift is not
  hidden. "Identical open windows in both runs" is `EVIDENCE_GAP`: the only
  window list on disk is the single between-window `env_probe.txt` capture;
  no per-window window inventory was recorded.
- Raw signals: `/proc/<pid>/stat` (utime+stime ticks at `CLK_TCK=100`),
  `/proc/<pid>/smaps_rollup` (`Pss`, `Rss`), `/proc/<pid>/status`
  (voluntary/nonvoluntary context switches), `/proc/stat` (system idle ticks),
  `/proc/<pid>/sched` (wakeup counter if exported). Process set by exact PID
  from `pgrep`, never by guessing from sampled values.
- Commands (host side, exact form):

```sh
# STOCK_PLASMA6, 2026-11-28 (see scratch/native_perf/raw/stock_idle.meta)
ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 \
  -p 2223 canopy@127.0.0.1 'bash -s STOCK_PLASMA6 300 5' \
  < tools/perf/native_idle_sampler.sh > scratch/native_perf/raw/stock_idle.tsv

# CANOPY_CLASSIC, 2026-11-28 (see scratch/native_perf/raw/canopy_idle.meta)
ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 \
  -p 2223 canopy@127.0.0.1 'bash -s CANOPY_CLASSIC 300 5' \
  < tools/perf/native_idle_sampler.sh > scratch/native_perf/raw/canopy_idle.tsv

python3 tools/perf/native_idle_report.py scratch/native_perf/raw/stock_idle.tsv scratch/native_perf/raw/stock_idle.json
python3 tools/perf/native_idle_report.py scratch/native_perf/raw/canopy_idle.tsv scratch/native_perf/raw/canopy_idle.json
ssh -i "$KEY" -p 2223 canopy@127.0.0.1 'python3 - 60 kwin_x11 canopy-classic' \
  < tools/perf/native_wakeup_probe.py  # wakeup-cadence PROXY, not frame timestamps
ssh -i "$KEY" -p 2223 canopy@127.0.0.1 'bash -s' \
  < tools/perf/native_env_probe.sh > scratch/native_perf/raw/env_probe.txt
```

## 2. Exact environment / versions

Recorded in `scratch/native_perf/raw/env_probe.txt` at `2026-11-28T04:47:04Z`
(guest probe captured **between** the two sampling windows; exact command in
§1). Provenance tokens: `RAW` = literal line in that artifact, `NOT_RUN` = no
raw probe captured for the claim, `EVIDENCE_GAP` = claimed earlier but not
corroborated by any raw byte in this PR. A `NOT_RUN` host-side probe is not
evidence against the guest facts; it means only that those facts are not
proven here.

| Item | Exact value | Provenance |
| --- | --- | --- |
| Guest OS | Ubuntu 26.04 LTS (Resolute Raccoon), `Linux canopy-plasma6 7.0.0-14-generic #14-Ubuntu SMP PREEMPT_DYNAMIC Mon Apr 13 11:09:53 UTC 2026 x86_64` | `RAW`: `env_probe.txt` `uname -a`, `/etc/os-release` |
| Guest vCPU | 2 x `11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz`, `Hypervisor vendor: KVM`, `Virtualization type: full` | `RAW`: `env_probe.txt` `lscpu` |
| X screen | 1920x1080 at 60 Hz on VGA-1 | `RAW`: `env_probe.txt` `$ xrandr` |
| Plasma | `plasma-workspace 4:6.6.7-0ubuntu0.1`, `kwin-x11 4:6.6.4-0ubuntu1` | `RAW`: `env_probe.txt` `$ dpkg-query plasma/kwin/qt6` |
| Qt | `qmake6` 6.10.2; `pkg-config Qt6Core/Qt6Quick` 6.10.2 / 6.10.2; `qt6-base-dev 6.10.2+dfsg-7` | `RAW`: `env_probe.txt` `$ qmake6 -v`, `$ pkg-config Qt6Core Qt6Quick`, dpkg-query |
| User autostart | `app-canopy\x2dclassic@autostart.service` = Canopy Classic; KDE Connect, Discover notifier, Geoclue demo agent, PipeWire/WirePlumber, KDED6, KAccess, Powerdevil, KScreen, portal services, accessibility bus | `RAW`: `env_probe.txt` `$ running user services` (earlier `\2dclassic` spelling corrected to raw `\x2dclassic`) |
| System services (running) | 28, incl. `ssh`, `sddm`, `NetworkManager`, `upower`, `systemd-logind`, `cups`, `snapd`, `chrony`, `avahi-daemon` | `RAW`: `env_probe.txt` `$ running system services` (28 lines counted) |
| User services (running) | 48 | `RAW`: `env_probe.txt` `$ running user services` (48 lines counted) |
| Guest Canopy process | PID 5667, `/home/canopy/.local/bin/canopy-classic` | `RAW`: `env_probe.txt` `$ canopy pids/cmdlines`; earlier "started `2026-11-28T04:09:48Z`" is `EVIDENCE_GAP` (no raw start-time line) |
| SDDM autologin, `DISPLAY=:0` | asserted host-side session facts | `EVIDENCE_GAP`: `sddm.service` running is `RAW`, but autologin and a `DISPLAY` variable are not in any raw log; only the `$ X session` window list is on disk |
| Host hypervisor package / VM name / UUID / 4096 MiB / "no snapshot" | Oracle VirtualBox 7.2.22, `Canopy-Test-Plasma6`, UUID `3aecd840-4dd6-4481-913f-64a289da406d`, 4096 MiB, no snapshot | `NOT_RUN`: no host-side `VBoxManage` capture exists; SSH endpoint and scratch key are documented commands, not raw guest evidence |
| Guest Canopy source pin | task base `ec910d7a7275296ecbc8b5e5c459d356205165d1` | `NOT_RUN` in guest raw logs (host git claim only); sibling guest rebuild path, mtime `2026-11-28T04:46:31Z` and SHA-256 `f7497694e81890e119a5f3b3b1306e13229dc585c87aeb15632f553eb4ca4011` are `RAW` from `env_probe.txt` and are **not** the proven executed binary |
| Executed Canopy binary hash | earlier claim `4089251cf6a557d74ca308f3e32f59fea318f62d3285204e9ec7872bcc6b3f14` | `EVIDENCE_GAP`: no `/proc/5667/exe` hash or executing-inode hash appears in any raw artifact; the claim is withdrawn as evidence, not replaced by an inference |

Other agents' `native-task-harness --auto ./harness/NativeTaskHarness.qml`
windows were visible in the between-window `env_probe.txt` capture (PIDs
30924, 33163; the earlier PIDs 21747/24585 in `CLAIM.md` are an earlier
host-side observation). They are excluded from both process sets, but per-run
window identity is `EVIDENCE_GAP` as noted in §1. `NOT_RUN`: clean-desktop
boot without any Canopy window, Mint guest (this VM is Ubuntu 26.04), real
AMD/NVIDIA GPU path (virtual VGA), screen-reader/assistive-technology
behavior, automatic CI-on-guest acceptance, owner visual acceptance, and a
live `/proc/<pid>/exe` hash probe.

## 3. Measurements

`NATIVE RUNTIME` numbers, computed from raw TSV by
`tools/perf/native_idle_report.py`. `STOCK_PLASMA6` ran from SSH invocation
`2026-11-28T04:40:20Z` (first sample header `04:40:27Z`) to `04:45:38Z`
(302 s, 30 parsed instants / 120 rows); `CANOPY_CLASSIC` ran `04:47:11Z`–
`04:52:38Z` (311 s, 44 parsed instants / 176 rows). Requested interval 5 s;
actual ~10 s because each `/proc` walk costs ~5 s.
CPU is ticks/`CLK_TCK`/elapsed; PSS is the mean of per-sample
`smaps_rollup:Pss`; RSS is `smaps_rollup:Rss` (kernel reports 4 KiB pages).

| PID / role | Stock PSS mean / peak (KiB) | Canopy-run PSS mean / peak | Stock RSS mean (KiB) | Canopy-run RSS mean | Stock CPU (% of 1 core) | Canopy-run CPU | Stock ctx switches/s | Canopy-run ctx switches/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4656 `startplasma-x11` | 7,312 / 7,402 | 7,025 / 7,156 | 46,224 | 46,018 | 0.0000 | 0.0000 | 0.00 | 0.00 |
| 5384 `kwin_x11` | 115,630 / 119,877 | 120,959 / 126,034 | 254,134 | 264,198 | 1.6821 | 5.6527 | 26.25 | 43.47 |
| 5422 `plasmashell` | 478,924 / 483,144 | 462,314 / 467,645 | 624,679 | 606,719 | 0.4470 | 0.3151 | 2.97 | 3.70 |
| 5667 `canopy-classic` | 140,896 / 144,433 | 133,139 / 135,228 | 269,838 | 261,018 | 0.2185 | 0.2090 | 0.35 | 0.33 |

- Shell-owned aggregate (startplasma+kwin+plasmashell): stock **601,866 KiB
  mean PSS / 610,423 KiB sum of per-process peaks**, **2.1291 % of one core**
  (1.0646 % of both); Canopy run **590,298 KiB mean / 600,835 KiB peak**,
  **5.9678 % of one core**. Canopy Classic's own contribution is
  **~130–141 MiB PSS, ~0.21 % of one core**, with near-identical numbers in
  both windows (66 vs 65 CPU ticks; 106 vs 102 context switches).
- Wakeups over the full 5-minute windows: `kwin_x11` 7,929 → 13,519 context
  switches (26.25 → 43.47 /s); `canopy-classic` 106 → 102 (0.35 → 0.33 /s).
- Frame pacing: `PROXY` only, from `native_wakeup_probe.py` (20 Hz sampling of
  cumulative context switches, 60 s): `kwin_x11` 42.567/s in the stock probe
  vs 71.733/s in the Canopy probe, 20 ms-bucket p50 1 / p95 5 vs p50 1 / p95 7;
  `canopy-classic` 0.383/s in both. Display refresh is 60 Hz. Real compositor/
  QML frame timestamps are **`NOT_RUN`**: guest `perf_event_paranoid=4`, no
  KWin frame-time DBus property and no Canopy frame-timestamp hook were
  available. Do not read the proxy as "frames per second".
- Background services: 28 running system units and 48 running user units at
  probe time, including `app-canopy\x2dclassic@autostart.service` and KDE
  Plasma/PipeWire/portal services. The full unit lists are in
  `scratch/native_perf/raw/env_probe.txt` (no service was started or stopped
  by this task).
- Running Canopy binary identity: `EVIDENCE_GAP`. No raw artifact in this PR
  contains a SHA-256 of `/proc/5667/exe`, of its resolved deleted inode, or
  of any other executed-binary probe. The earlier value
  `4089251cf6a557d74ca308f3e32f59fea318f62d3285204e9ec7872bcc6b3f14` is
  withdrawn as an evidence claim: it is not corroborated by a raw log and is
  not replaced by an inference. `env_probe.txt` contains only the sibling
  rebuild's path, mtime `04:46:31Z` and SHA-256
  `f7497694e81890e119a5f3b3b1306e13229dc585c87aeb15632f553eb4ca4011`,
  which is **not** proven to be the binary executed by PID 5667. No binary
  was built or replaced by this task, and a fresh `/proc/<pid>/exe` probe is
  `NOT_RUN`.

## 4. Limits, labels and verdict

- `NATIVE RUNTIME` / `SCOPED_ON_GUEST_RUNTIME`: all PSS/RSS/CPU/wakeup figures
  above, on a real X11 Plasma 6 desktop in the existing VM; **not** a Linux
  Mint acceptance run and not a release gate.
- Confound recorded, not hidden: a sibling agent's build was writing
  `/home/canopy/native_build_baseline/out/build/canopy-classic-spike` with
  mtime `2026-11-28T04:46:31Z` — **after** the stock window ended
  (`04:45:38Z`) and in the gap before the Canopy window began (`04:47:11Z`).
  Earlier wording that put that build "inside the stock window" was wrong and
  is corrected. Other agents' harness windows were visible in the
  between-window probe; per-window relaunch events are `NOT_RUN` in raw logs.
  System-wide idle was only **19.8 %** (stock) and **41.2 %** (Canopy) of the
  two cores' time, so the two shell-CPU aggregates are **not a clean A/B**;
  the higher `kwin_x11` CPU in the Canopy run cannot be attributed to Canopy
  Classic. Canopy's own PSS/CPU/wakeups were stable across both windows, so
  its incremental figures are usable with this caveat. A clean serialized
  re-run is `NOT_RUN` and remains the next bounded step.
- `NOT_RUN`: real frame timestamps, clean Canopy-free desktop baseline,
  Linux Mint guest, hardware GPU path, screen-reader/assistive-technology
  behavior, automatic CI-on-guest, owner visual acceptance, merge/release,
  a live `/proc/<pid>/exe` hash probe, host-side `VBoxManage` VM-config
  capture, per-window window/harness relaunch inventory, and a clean
  serialized A/B re-run.
  `SYNTHETIC`: none; no microbenchmark or invented number is used.
- Engineering verdict: **BASELINE_CAPTURED_NOT_ACCEPTED**. Stock shell PSS
  (~588 MiB mean) exceeds the 200 MiB shell target by ~3×, Canopy Classic's
  own PSS (~130–141 MiB) exceeds the 100 MiB incremental idle target, and its
  CPU (~0.21 % of one core) exceeds the 0.1 % idle CPU target. These are scoped, contended measurements, not a
  release rejection on their own; no merge, no self-approval, no shared-file
  edit. Draft PR only.

## 5. Raw artifact index

`scratch/native_perf/SHA256SUMS.txt` covers every raw artifact from the exact
committed bytes: `stock_idle.tsv`, `stock_idle.json`, `stock_wakeup.json`,
`canopy_idle.tsv`, `canopy_idle.json`, `canopy_wakeup.json`, `env_probe.txt`,
`CLAIM.md`, their `.meta`/`.err` sidecars. Committed tools are hashed in
`scratch/native_perf/TOOLS_SHA256SUMS.txt` (relative to the repository root).
Recompute with `sha256sum -c SHA256SUMS.txt` from `scratch/native_perf/`.

## 6. Provenance corrections in this commit

No measurement was re-run and no new guest probe was executed in this
remediation; the raw artifacts keep their original bytes and hashes. The
four documented caveats are resolved as follows:

| Caveat | Label after correction | Raw basis |
| --- | --- | --- |
| Stock-window timestamp contradiction | `CORRECTED` | `stock_idle.meta` end `04:45:37Z`, `stock_idle.tsv` end comment `04:45:38Z`, `canopy_idle.meta` start `04:47:11Z`, and `env_probe.txt` sibling-build mtime `04:46:31Z`: the build finished **in the gap**, not inside the stock window. Earlier "inside the stock window" wording is withdrawn. |
| Executed-binary SHA absent from raw logs | `EVIDENCE_GAP` | No raw line hashes `/proc/5667/exe`; `env_probe.txt` hashes only the sibling rebuild `f7497694...`. Earlier running-binary SHA `4089251c...` is withdrawn as evidence; fresh probe `NOT_RUN`. |
| Sample-instant count mismatch | `CORRECTED` | Report JSONs: stock `sample_rows=120` with 30 instants, Canopy `sample_rows=176` with 44 instants; total 296 rows / 74 instants, not 61. The stock TSV's 120 malformed `S <n>` lines are skipped by the parser and not counted. |
| Environment facts not raw-corroborated | `RAW` / `NOT_RUN` / `EVIDENCE_GAP` | §2 now marks each fact: guest OS/CPU/versions/services/screen are `RAW` in `env_probe.txt`; host VM package/name/UUID/RAM/snapshot, process start time, autologin/`DISPLAY`, per-window inventory and a clean serialized A/B are `NOT_RUN` or `EVIDENCE_GAP` as specified. |

Verdict is unchanged: **BASELINE_CAPTURED_NOT_ACCEPTED**. Clean A/B:
**`NOT_RUN`** — the two existing windows remain contended and no serialized
re-run was performed by this remediation. No merge, no approval, no release
claim.
