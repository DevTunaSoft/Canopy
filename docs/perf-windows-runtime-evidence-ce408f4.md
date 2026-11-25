# Classic Qt compiled preview — Windows-runtime performance evidence

**Classification: SYNTHETIC / WINDOWS-RUNTIME. NOT MINT VERIFIED.**
This is a Windows host running an `offscreen` Qt platform build. It is not
Linux Mint evidence, not a 5-minute PSS idle run, not a real-desktop/GPU run,
and not release acceptance. No visual asset was changed and nothing was merged.

**Read every number below as SYNTHETIC.** The 15 s CPU/working-set activity
proxy is not a scheduler-wakeup measurement: true wakeups are **NOT_RUN**.
GPU/compositor cost is **NOT_RUN** (software raster only). Real five-minute
shell-owned PSS on a real desktop is **NOT_RUN**. The idle PSS and idle CPU
engineering targets in README.md remain targets, not attained values.

## Exact artifacts and provenance

| Item | Value |
|---|---|
| Build source SHA (current integration tip at worktree creation) | `ce408f42dfb596e7c72efd907f9dcbad872b8c3b` (`integration/canopy-classic-20261123`) |
| Source worktree | `C:/Users/X1/AppData/Local/hermes/cache/scratch/cperf-wt-ce408f4` (detached, clean) |
| Build dir | `C:/Users/X1/AppData/Local/hermes/cache/scratch/cperf-build-ce408f4` |
| Binary | `canopy-classic-spike.exe` |
| Binary SHA-256 | `8cbc17989d78a1ed16ee44fea4b350167613334c7b992d391fa4bbab694fa66c` |
| Binary size | recorded in `cperf-results-ce408f4.json` |
| Results JSON | `C:/Users/X1/AppData/Local/hermes/cache/scratch/cperf-results-ce408f4.json` |
| Results JSON SHA-256 | `317c47e996eabac037ccdb47c8400a52621831fd077016856d6a849eb6315cb9` |
| Captured frame SHA-256 | `98986320fa2c199bb29a7e47156836f6eb7eb533b789925be3ee34557fb0a246` |
| Sampler | `cperf_measure.py` (scratch), uv venv with psutil 7.2.2 |
| Toolchain | MSYS2 UCRT64: cmake 4.5.1, ninja 1.13.2, g++ 16.2.0, Qt6Quick/QuickControls2 |

The integration branch advanced twice while the run was in progress (to
`a3327fbd152579c04d4419f56f7873226d16425e` by gate time). Every number below
is pinned to the exact binary and source SHA above, which was the live tip
when the worktree was created and built. No Qt preview source changed between
the measured SHA and the later tips in the observed merges.

## Host / session

- OS: Microsoft Windows 11 Pro, build/kernel `10.0.26300` (x86-64 / AMD64).
- CPU: 11th Gen Intel Core i5-1135G7 @ 2.40 GHz, 4 cores / 8 logical.
- GPU present: Intel Iris Xe Graphics, driver 30.0.101.1191. **Not used** —
  `QT_QPA_PLATFORM=offscreen` selects the software raster path.
- Session: interactive console session 1, user `x1` (Active). Measurements ran
  as ordinary child processes from that session, with a bounded workload.

## Method

1. Configure/build from the isolated worktree with UCRT64:
   `cmake -S <wt>/prototype/classic -B <build> -G Ninja -DCMAKE_PREFIX_PATH=C:/msys64/ucrt64 -DCMAKE_CXX_COMPILER=C:/msys64/ucrt64/bin/g++.exe`
   then `cmake --build <build> -j2`. Configure and build exited 0; 43 build
   steps. Non-fatal notes: Qt QTP0001 author warning; `gio-unix-2.0` absent so
   native app launching compiled as its disabled fallback.
2. Bounded workload: `--approved-art-dir <wt>/.../approved --self-test-approved
   --self-test-size 1200x750 --self-test-screenshot <png>`, all runs with
   `QT_QPA_PLATFORM=offscreen`. Every invocation exited 0 and produced a PNG.
   Success is established by exit code + PNG SHA-256; this Qt build does not
   emit the `qInfo()` self-test lines to stdout, so no pass-line count is
   claimed.
3. Frame proxy: parent polls at 4 ms for the first non-empty PNG written after
   `grabWindow()`. The self-test arms a fixed `QTimer::singleShot(1000, ...)`
   before capture, so 1.000 s of every measured time-to-frame is deliberate;
   net startup = time-to-frame − 1.000 s.
4. Cold = first launch after >=8 s with no preview process alive (OS standby
   list **not** flushed). Warm = five immediate repeat launches. Core
   baseline = `--self-test-system-apps-capability` (QCoreApplication only, no
   QML/Quick scene, `singleShot(0, quit)`), five launches.
5. Idle: same approved-art scene with no screenshot flag, so it stays in
   `app.exec()`. After a 2 s warmup, sampled every 20 ms for ~15 s with
   `psutil.memory_info()` (Windows working set), `memory_full_info().uss`
   (private bytes), `cpu_times()` and handle/thread counts. The child was
   terminated after the bounded window.
6. Wakeup proxy: count 20 ms windows with >=2 ms CPU delta. Windows scheduler
   ticks are ~15.6 ms, so this is an activity proxy, not ETW context-switch or
   frame counting. The QML clock source keeps one 60 s one-shot timer.

Two full measurement passes were run on the same binary; both are reported
rather than averaged into a single "win".

## Results (SYNTHETIC Windows-host samples; no real-desktop claim)

All rows are SYNTHETIC host observations on the pinned `offscreen` binary, not
estimates of real Mint behaviour and not target attainment. The idle CPU and
active-window rows are a 20 ms activity proxy, not measured wakeups (**NOT_RUN**).

| Metric | Pass A | Pass B (results JSON) |
|---|---|---|
| Core-only startup median (5 runs) | 0.1084 s | 0.0578 s (range 0.0531–0.1034) |
| Cold time-to-frame median (2 runs) | 1.7075 s | 1.3266 s (1.3194, 1.3339) |
| Warm time-to-frame median (5 runs) | 1.6606 s | 1.3550 s (range 1.3054–1.3939) |
| Net cold startup (−1.000 s timer) | 0.7075 s | 0.3266 s |
| Net warm startup (−1.000 s timer) | 0.6606 s | 0.3550 s |
| Scene cost above QtCore-only (warm net − core) | 0.5522 s | 0.2972 s |
| Idle working set (min / mean / max) | 65,880,064 / 65,881,825 / 65,884,160 B | 65,409,024 / 65,535,703 / 66,031,616 B |
| Idle CPU, one logical core (mean / max) | 0.00% / 0.00% | 0.00% / 0.00% |
| Idle CPU, all 8 logical cores (mean / max) | 0.00% / 0.00% | 0.00% / 0.00% |
| Idle samples / active 20 ms windows | 299 / 0 | 454 / 0 |
| Max gap between active windows | whole window | 14.968 s (whole window — no activity) |

Run-to-run variance is large (cold 1.33–1.71 s, core 0.058–0.108 s), so no
speedup claim is made. Cold and warm medians differ by ~28 ms in Pass B and
are inside the host noise floor; there is no demonstrated cold-cache penalty
beyond the first launch.

### Largest measured bottleneck on the SYNTHETIC host

QML/Quick scene initialization plus first-frame composition dominates the
SYNTHETIC startup samples: net warm startup 0.30–0.66 s versus 0.058–0.108 s
for QtCore-only startup in the same binary — roughly 5–11× the core path, with
the scene delta measured at 0.297 s (Pass B) and 0.552 s (Pass A). The 1.000 s
pre-capture timer is a fixed self-test delay, not application work, and is
excluded from that comparison. On this offscreen host the activity proxy showed
0.00% sampled CPU and zero active 20 ms windows over 299/454 samples, with a
~62.5–62.8 MiB working set; this is **not** a wakeup measurement (wakeups
**NOT_RUN**), not a GPU measurement (**NOT_RUN**) and not the real five-minute
PSS target (**NOT_RUN**). No speedup or target attainment is claimed from the
noisy host timings.

## Bounded regression gate added

`tests/test_c100_idle_wakeup_contract_gate.py` statically asserts that
`prototype/classic/ClockLabel.qml` keeps exactly one 60 s, non-repeating,
initially stopped QML timer, the `refreshScheduled` property, the wall-clock
alignment expression, and no animation/per-frame timer type. It includes a
mutated-source RED case. This gate is deterministic and has **no timing
threshold**, so it cannot flake on the noisy host; it guards the static timer
mechanism seen alongside the SYNTHETIC activity-proxy profile. It does not
measure wakeups (**NOT_RUN**), GPU (**NOT_RUN**) or real five-minute PSS
(**NOT_RUN**), is not a Mint gate and does not grant release approval.

## Exclusions / unmeasured surfaces

- **NOT_RUN**: Linux Mint guest, Xvfb/real desktop, real five-minute PSS and
  idle target, `/proc/smaps_rollup`, CI-on-guest acceptance and visual approval.
- **NOT_RUN**: GPU/compositor path (offscreen software raster only).
- **NOT_RUN**: true scheduler wakeups and frame-rate measurement; a 20 ms CPU
  activity proxy was sampled instead.
- No standby-list/disk-cache flush: "cold" is operational, not a cold disk read.
- **NOT_RUN**: screen-reader or accessibility behavior measurement.
- No visual, layout, artwork or QML geometry change in this workstream.
- No commit to main and no merge; changes live on a dedicated perf branch.

## Verification commands

```
<uv-venv>/Scripts/python.exe cperf_measure.py        # JSON results in scratch
python -m unittest discover -s tests -p 'test_c100_idle_wakeup_contract_gate.py'
python -m unittest discover -s tests                 # full suite
sha256sum canopy-classic-spike.exe cperf-results-ce408f4.json
```
