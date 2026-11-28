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
- Equal workload: 5 continuous minutes of idle desktop per run, 5-second
  sampling (61 sample instants), identical guest, identical open windows in
  both runs. `STOCK_PLASMA6` = shell-owned set `startplasma-x11`, `kwin_x11`,
  `plasmashell`. `CANOPY_CLASSIC` = the same shell set plus the Canopy Classic
  process tree. Incremental consumption = Canopy process set measured in the
  second run, with the stock shell delta reported separately so drift is not
  hidden.
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
(exact command in §1). `NATIVE RUNTIME`, read from the live guest:

| Item | Exact value |
| --- | --- |
| Host hypervisor | Oracle VirtualBox 7.2.22; VM `Canopy-Test-Plasma6`, UUID `3aecd840-4dd6-4481-913f-64a289da406d`, 2 vCPU, 4096 MiB, no snapshot |
| Guest OS | Ubuntu 26.04 LTS (Resolute Raccoon), `Linux canopy-plasma6 7.0.0-14-generic #14-Ubuntu SMP PREEMPT_DYNAMIC Mon Apr 13 11:09:53 UTC 2026 x86_64` |
| vCPU | 2 × `11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz`, KVM full virtualization |
| Desktop | X11 Plasma session, SDDM autologin, `DISPLAY=:0`, 1920x1080@60 Hz on VGA-1 |
| Plasma | `plasma-workspace 4:6.6.7-0ubuntu0.1`, `kwin-x11 4:6.6.4-0ubuntu1` |
| Qt | `qmake6`: Qt 6.10.2; `pkg-config Qt6Core Qt6Quick`: 6.10.2 / 6.10.2; `qt6-base-dev 6.10.2+dfsg-7` |
| User autostart | `app-canopy\2dclassic@autostart.service` = Canopy Classic; KDE Connect, Discover notifier, Geoclue demo agent, PipeWire/WirePlumber, KDED6, KAccess, Powerdevil, KScreen, portal services, accessibility bus |
| System services (running) | 28, incl. `ssh`, `sddm`, `NetworkManager`, `upower`, `systemd-logind`, `cups`, `snapd`, `chrony`, `avahi-daemon` |
| Guest Canopy process | PID 5667 `/home/canopy/.local/bin/canopy-classic`, started `2026-11-28T04:09:48Z` |
| Canopy source pin | `ec910d7a7275296ecbc8b5e5c459d356205165d1` (task base); a sibling agent's guest-only rebuild at `/home/canopy/native_build_baseline/out/build/canopy-classic-spike` finished `04:46:31Z`, SHA-256 `f7497694e81890e119a5f3b3b1306e13229dc585c87aeb15632f553eb4ca4011` — that file is **not** claimed to be the binary executed by PID 5667; the running binary identity is probed separately below. |

Other agents' `native-task-harness --auto ./harness/NativeTaskHarness.qml`
windows were present in both runs (PIDs changed during the window) and are
excluded from both process sets. `NOT_RUN`: clean-desktop boot without any
Canopy window, Mint guest (this VM is Ubuntu 26.04), real AMD/NVIDIA GPU
path (virtual VGA), screen-reader/assistive-technology behavior,
automatic CI-on-guest acceptance, owner visual acceptance.

## 3. Measurements

`NATIVE RUNTIME` numbers, computed from raw TSV by
`tools/perf/native_idle_report.py`. `STOCK_PLASMA6` ran
`2026-11-28T04:40:20Z`–`04:45:38Z` (302 s, 30 sample instants / 120 rows);
`CANOPY_CLASSIC` ran `04:47:11Z`–`04:52:38Z` (311 s, 44 instants / 176 rows).
Requested interval 5 s; actual ~10 s because each `/proc` walk costs ~5 s.
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
  probe time, including `app-canopy\2dclassic@autostart.service` and KDE
  Plasma/PipeWire/portal services. The full unit lists are in
  `scratch/native_perf/raw/env_probe.txt` (no service was started or stopped
  by this task).
- Running Canopy binary identity: PID 5667's `/proc/5667/exe` pointed to a
  **deleted** file; SHA-256 of the still-executing inode is
  `4089251cf6a557d74ca308f3e32f59fea318f62d3285204e9ec7872bcc6b3f14`.
  The sibling agent's newly built `canopy-classic-spike`
  (`f7497694e81890e119a5f3b3b1306e13229dc585c87aeb15632f553eb4ca4011`)
  was **not** the running binary. No binary was built or replaced here.

## 4. Limits, labels and verdict

- `NATIVE RUNTIME` / `SCOPED_ON_GUEST_RUNTIME`: all PSS/RSS/CPU/wakeup figures
  above, on a real X11 Plasma 6 desktop in the existing VM; **not** a Linux
  Mint acceptance run and not a release gate.
- Confound recorded, not hidden: a sibling agent's native build was still
  writing `/home/canopy/native_build_baseline/out/build/canopy-classic-spike`
  at `04:46:31Z`, inside the stock window, and other agents' harness windows
  were relaunched during both windows. System-wide idle was only **19.8 %**
  (stock) and **41.2 %** (Canopy) of the two cores' time, so the two shell-CPU
  aggregates are **not a clean A/B**; the higher `kwin_x11` CPU in the Canopy
  run cannot be attributed to Canopy Classic. Canopy's own PSS/CPU/wakeups were
  stable across both windows, so its incremental figures are usable with this
  caveat. A clean serialized re-run is the next bounded step.
- `NOT_RUN`: real frame timestamps, clean Canopy-free desktop baseline,
  Linux Mint guest, hardware GPU path, screen-reader/assistive-technology
  behavior, automatic CI-on-guest, owner visual acceptance, merge/release.
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
