# Claim: M5 native performance/resource baseline

- Directive SHA `79e30d79`, agent cap 8, 5 product agents active.
- Claimed by: native-perf-baseline subagent (M5), 2026-11-27/28.
- Owned paths (exactly): `tools/perf/**`, `docs/NATIVE_PERF_BASELINE.md`, `scratch/native_perf/**`.
- Worktree: `C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-perf-baseline-20261127`, branch `product/native-perf-baseline-20261127` from `ec910d7a7275296ecbc8b5e5c459d356205165d1`.
- VM: `Canopy-Test-Plasma6`, SSH `canopy@127.0.0.1:2223` with pre-existing scratch key; read-only guest probes plus reversible 5-minute idle sampling. No VM start/stop/snapshot/revert, no package/service/setting change, no shared prototype edits.
- Serialization: host process check at claim time found another agent's `build_baseline.py` compile in this VM; the sibling rebuild's raw mtime is `2026-11-28T04:46:31Z`, which is in the gap after the stock window ended (`04:45:38Z`) and before the Canopy window began (`04:47:11Z`). No clean serialized A/B was achieved; the earlier "deferred until that compile exited" / "inside the stock window" wording was wrong and is corrected here. Concurrent `native-task-harness` windows (PIDs 21747/24585 at claim time; PIDs 30924/33163 in the between-window raw probe) are scope caveats, not Canopy shell processes; per-window relaunch inventory is `NOT_RUN`.
- Time-box: 30 minutes from 2026-11-28T04:30Z; record findings and continue afterward.
- No merge, no self-approval; one draft PR to `integration/canopy-plasma6-20261127` only.
