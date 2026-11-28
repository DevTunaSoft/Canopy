## M5 native performance/resource baseline

Branch from exact `ec910d7a7275296ecbc8b5e5c459d356205165d1`; no shared prototype, visual, QML, asset or compiled-input file changed. Owned paths only: `tools/perf/**`, `docs/NATIVE_PERF_BASELINE.md`, `scratch/native_perf/**`. Draft only — no merge or self-approval.

### What ran (`NATIVE RUNTIME`, scoped to the existing X11 Plasma 6 guest)
- VM `Canopy-Test-Plasma6`, Ubuntu 26.04, Plasma 6.6.7 / kwin-x11 6.6.4, Qt 6.10.2, 2 vCPU i5-1135G7, 1920x1080@60 Hz, SSH `canopy@127.0.0.1:2223`.
- Two 5-minute idle windows: STOCK_PLASMA6 shell (startplasma/kwin_x11/plasmashell) 2026-11-28T04:40:20Z–04:45:38Z, and CANOPY_CLASSIC shell + Canopy process 04:47:11Z–04:52:38Z; identical workload, raw `/proc` sampling via committed tools.
- Stock shell: PSS 601,866 KiB mean / 610,423 KiB sum of peaks; 2.1291 % of one core. Canopy Classic itself: PSS 140,896 KiB (stock window) / 133,139 KiB (Canopy window), CPU 0.2185 % / 0.2090 % of one core; 106/102 context switches in 302/311 s. `kwin_x11` context switches 26.25 → 43.47 /s.
- Frame pacing: wakeup-cadence `PROXY` (`kwin_x11` 42.567/s stock vs 71.733/s Canopy; p95 bucket 5 vs 7 at 20 ms). Real frame timestamps `NOT_RUN` (`perf_event_paranoid=4`, no KWin frame-time API).
- Background services: 28 system + 48 user units, including `app-canopy\2dclassic@autostart.service`. Full version/service inventory and running binary SHA-256 `4089251cf6a557d74ca308f3e32f59fea318f62d3285204e9ec7872bcc6b3f14` in `docs/NATIVE_PERF_BASELINE.md` and raw logs.

### Evidence and honesty
- All numbers are recomputable from `scratch/native_perf/raw/*.tsv`, `*.json` and `SHA256SUMS.txt` with `tools/perf/native_idle_report.py`. `SYNTHETIC`: none.
- Confound disclosed: a sibling agent's build finished inside the stock window and other agents' harness windows were relaunched; system-wide idle was only 19.8 % / 41.2 %, so shell CPU is **not a clean A/B**. Canopy's own figures were stable across both windows. Clean serialized re-run is the next bounded step.
- `NOT_RUN`: real frame timestamps, Canopy-free clean desktop, Linux Mint guest, hardware GPU, screen-reader behavior, CI-on-guest, visual acceptance, merge/release.
- Verdict: `BASELINE_CAPTURED_NOT_ACCEPTED`. Stock shell PSS and Canopy's PSS/CPU exceed the engineering targets under this scoped, contended measurement; no release claim follows from it.
