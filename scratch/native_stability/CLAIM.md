# Claim: M5 bounded native Plasma stability/soak smoke

- Directive: `79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083`
  (cap 8, serialize VM work with other product agents).
- Claimed: 2026-11-28T06:25Z by the native-stability-smoke subagent.
- Worktree: `C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-stability-20261127`
  branch `product/native-stability-smoke-20261127` from
  `ec910d7a7275296ecbc8b5e5c459d356205165d1`.
- Owned paths on this branch: 32 changed files vs `ec910d7a` —
  `tools/stability/**` (3), `docs/NATIVE_STABILITY_SMOKE.md`,
  `docs/NATIVE_STABILITY_REMEDIATION.md`, `scratch/native_stability/**` (18),
  `scratch/pr749_incident/**` (5), `tests/fixtures/native_soak/**` (3) and
  `tests/test_native_soak_remediation.py` (1). No shared source, QML, asset or
  config edit; the PR body's shorter path list is superseded.
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

## Post-diagnosis remediation (read-only, no promotion)

- Diagnosis `39ad2835` traced the WARN to guest soft lockups and sampler
  defects. Remediation on this branch fixes the hostname regex, stores bounded
  per-sample unit names, adds a read-only VBox/soft-lockup gap classifier,
  corrects the guest meta key and `sample_count` type, and documents CPU bucket
  caveats. Details: `docs/NATIVE_STABILITY_REMEDIATION.md`.
- The exclusive/quiesced-guest 1 h soak rerun is `NOT_RUN`: read-only preflight
  at `2026-11-28T08:03:19Z` found active unattended-upgrade/apt work (including
  PID 66146), load 3.29/2.41/2.40 and 10 soft lockups. No VM action taken.
- Verdict remains `SOAK_WARN_...`; no READY, merge or approval.
- Documentation residuals corrected without touching raw bytes: §4 marks the
  legacy 132 journal errors unreliable and both gaps `GUEST_STALL_PROVEN`
  (aligned with §7); PSS is a net −3,782 KiB with 5 upward steps, not
  monotonic; the CPU bucket caveat records 0.3 %–89.0 % coverage, `NA`
  exclusion and no synthesised rows; changed-path count is 32.
