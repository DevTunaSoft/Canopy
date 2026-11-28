# Claim: M5 bounded native Plasma stability/soak smoke

- Directive: `79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083`
  (cap 8, serialize VM work with other product agents).
- Claimed: 2026-11-28T06:25Z by the native-stability-smoke subagent.
- Worktree: `C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-stability-20261127`
  branch `product/native-stability-smoke-20261127` from
  `ec910d7a7275296ecbc8b5e5c459d356205165d1`.
- Owned paths only: `tools/stability/**`, `docs/NATIVE_STABILITY_SMOKE.md`,
  `scratch/native_stability/**`. No shared source, QML, asset or config edit.
- VM: existing `Canopy-Test-Plasma6` (UUID `3aecd840-4dd6-4481-913f-64a289da406d`,
  2 vCPU / 4096 MiB, X11 Plasma 6), pre-existing NAT SSH `127.0.0.1:2223`,
  pre-existing scratch key (never committed). No VM start/stop/snapshot/revert,
  no package, compositor, service or persistent guest setting change.
- Serialization: preflight at 06:25:54Z found no other agent's build or native
  harness process in the guest, 3 users and load average 0.15/0.41/0.34.
  Only one lightweight sampler session is run at a time. Host VM contention
  and any process changes are recorded in the raw TSV, not hidden.
- Time-box: 3600 s (60 min) nominal, 60 s sampling. This is a **bounded** soak;
  24 h is explicitly `NOT_RUN` unless separately observed.
- No merge, no self-approval, no ready-for-merge promotion. One DRAFT PR to
  `integration/canopy-plasma6-20261127` only.
