# PR #749 stability sampler — bounded remediation (no promotion)

Status: **SAMPLER/REPORT DEFECTS FIXED; SOAK RERUN NOT_RUN; VERDICT STAYS WARN.**
No merge, approval, PR promotion, VM state change, guest package/service/config
change or destructive action was performed. All guest/VBox access was read-only.

- Directive Rev3 SHA `1fba4b1e` (cap 8).
- Subject: `product/native-stability-smoke-20261127` (PR #749); smoke commit
  `449e39e7`, remediation head `f8cbe123`, doc-fix head pushed on this branch.
- Diagnosis source: `39ad2835` (`diagnosis/pr749-soak-20261128`),
  `docs/NATIVE_STABILITY_INCIDENT.md`, `scratch/pr749_incident/diagnosis.json`.
- Remediation worktree:
  `C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-pr749-remediate-20261128`.
- Owned paths only: `tools/stability/**`, `docs/NATIVE_STABILITY_SMOKE.md`,
  `docs/NATIVE_STABILITY_REMEDIATION.md`, `scratch/native_stability/**`,
  `scratch/pr749_incident/**`, `tests/test_native_soak_remediation.py`,
  `tests/fixtures/native_soak/**`. The documentation-residual pass that
  follows owns only `docs/NATIVE_STABILITY_SMOKE.md`, this document and
  `scratch/native_stability/**`; the full branch delta vs `ec910d7a` remains
  **32 files** across those seven path groups (3 tools, 2 docs, 18
  `scratch/native_stability`, 5 `scratch/pr749_incident`, 3 test fixtures,
  1 test module). The PR body's shorter owned-path list is corrected in §5.

## 1. Defects fixed

| # | Defect (from diagnosis) | Fix | Evidence |
| --- | --- | --- | --- |
| 1 | Journal regex matched the whole `short-iso` line, so hostname `canopy-plasma6` inflated `journal_system_errors_total` to 132 | `native_soak_sampler.py`: `journal_message_body()` strips timestamp + hostname + unit tag before `ERROR_PATTERN` is applied; `matching_error_lines()` also records a distinct-event count | regression fixture `tests/fixtures/native_soak/journal_err_hostname_fixture.txt`: legacy whole-line match = 6, corrected message-body match = 3, none contain the hostname |
| 2 | Sampler stored only unit *counts*, so `SERVICE_COUNT_DRIFT` could not be decomposed | `unit_sample_event()` emits bounded per-sample `unit_sample` EVENTs (cap 64, sorted names, explicit `truncated` flag and `PROBE_UNAVAILABLE` status); `S` row schema stays `/2` so legacy raw stays parseable | report `unit_membership` aggregates names; legacy raw is labelled `NOT_RUN`, never invented |
| 3 | >120 s gaps were reported raw with an `INFERRED` service-probe story | `native_soak_report.py` adds a read-only file-scan classifier: guest `soft lockup` lines + VirtualBox heartbeat/catch-up lag (VBox uptime offset from `Log opened`) → `GUEST_STALL_PROVEN`; no evidence → `NOT_RUN_NO_READONLY_EVIDENCE` / `UNCLASSIFIED_NO_READONLY_EVIDENCE`; SHA-256 of each source recorded; no rows synthesised | both gaps reclassified `GUEST_STALL_PROVEN` from unchanged evidence |
| 4 | Wrong guest meta key: `meta.get("host=vm guest")` always returned `None` | reads the correct `# guest=` key | regenerated report: `"guest": "canopy-plasma6"` |
| 5 | `sample_count` was the string `"51"` | `as_int()` casts to `int` | regenerated report: `"sample_count": 51` (int) |
| 6 | 5-minute CPU buckets divided by `span` without saying the bucket could be under-covered | every bucket now carries `nominal_window_s`, `observed_span_s`, `coverage_pct`, `samples` and an explicit caveat; global `cpu_bucket_caveats` added; `NA` ticks excluded, not zeroed | 12 buckets, e.g. bucket 0 = 240/300 s (80.0 % coverage) |

Legacy raw probes are additionally labelled
`JOURNAL_ERROR_COUNT_UNRELIABLE_LEGACY_HOSTNAME_MATCH`: the 132 error total in
the original `soak.json` came from the old hostname-inflating probe and is not
trustworthy. The 8 coredumps are independent and remain valid, so the warning
still fires honestly.

## 2. Honest labels preserved

Regenerated verdict (from **unchanged** raw bytes):

```
SOAK_WARN_CRASH_OR_ERROR_EVENT+SAMPLING_GAP+SERVICE_COUNT_DRIFT+JOURNAL_ERROR_COUNT_UNRELIABLE_LEGACY_HOSTNAME_MATCH
```

No `READY`, no `SOAK_STABLE_BOUNDED`, no promotion. `not_run` includes
`24H_SOAK`, `TRUE_LOW_END_HARDWARE`, `RELEASE_ACCEPTANCE`,
`SOAK_RERUN_EXCLUSIVE_QUIESCED_GUEST`, `MERGE`, `APPROVAL`.

## 3. Why the 1 h soak was NOT_RUN

Read-only SSH preflight at `2026-11-28T08:03:19Z` on `canopy-plasma6`:

- load average `3.29, 2.41, 2.40` (not quiesced);
- active `apt.systemd.daily install` / `update` and three `unattended-upgrade`
  processes, including PID `66146` — the exact task named in the first soft
  lockup of the diagnosed soak;
- 10 `soft lockup` matches in the last 1000 kernel journal lines.

The guest is therefore **not exclusively owned or quiesced**. Per the
diagnosis's own criterion (zero soft lockups, zero coredumps, no >120 s gaps on
an exclusive guest), a fresh bounded soak would not be admissible evidence. No
soak was started; no package/service was stopped; no VM state was changed.

## 4. Evidence index (SHA-256 of current bytes)

| Path | SHA-256 |
| --- | --- |
| `tools/stability/native_soak_sampler.py` | `b82349db322b1fb47b408da49d884b2efc8338b96f8ac26175310ac9f6f3d289` |
| `tools/stability/native_soak_report.py` | `b49942569d0cb8de037d319053a4667b83941bd2824d09d515fa0d986bb05376` |
| `tools/stability/run_native_soak.sh` | `7a5dd926f06372facf6535e808bbc3f56dc09f6e17d67d1f170efcbea9e63958` |
| `scratch/native_stability/raw/soak_remediated.json` | `1c43ba9b7744edb3bc02c74cddec513e836f543771dac2c7d7341ab48de60e98` |
| `scratch/pr749_incident/vm/journal_window.txt` | `d31594472e5144cc41bea8d5f99ba4ada03baed45147214c1d176f9144fafcd6` |
| `scratch/pr749_incident/vm/vbox_correlation.txt` | `b33854a8e6e83c358b663af8c77747853d476df3dd462d58a75fdb6f246325d5` |
| `scratch/pr749_incident/vm/err_replay.txt` | `f6dbfdab34c1b9f8660adbf6dbc2ec40b59e7703d7c65cbe8cafa3983612c7d0` |

The committed raw files under `scratch/native_stability/raw/` were **not**
edited: `sha256sum -c SHA256SUMS.txt` still passes for all 13 entries.

## 5. Checks rerun

1. `python3 -m unittest -v tests.test_native_soak_remediation` — 13 tests, OK.
2. `sha256sum -c scratch/native_stability/raw/SHA256SUMS.txt` — 13/13 OK.
3. `sha256sum -c scratch/native_stability/TOOLS_SHA256SUMS.txt` — 3/3 OK.
4. Regenerate report from unchanged raw with `--evidence-dir
   scratch/pr749_incident/vm --rerun-note ...` — RC 0, both gaps
   `GUEST_STALL_PROVEN`, VERDICT `SOAK_WARN_...`, rerun `NOT_RUN`.
5. Read-only VM state + guest preflight (above) — no VM action.
6. Documentation-residual re-check at the pushed doc-fix head: §4 of
   `docs/NATIVE_STABILITY_SMOKE.md` now marks the 132 total
   `JOURNAL_ERROR_COUNT_UNRELIABLE_LEGACY_HOSTNAME_MATCH` and both gaps
   `GUEST_STALL_PROVEN` (matching §7); the monotonic PSS wording is replaced by
   the measured net −3,782 KiB with 5 upward steps in 51 raw samples; the CPU
   gap-coverage caveat (0.3 %–89.0 % bucket coverage, `NA` excluded, no rows
   synthesised) is stated; and the changed-path list is corrected to 32 files.
7. Re-verified at that head: `sha256sum -c SHA256SUMS.txt` 13/13 OK,
   `sha256sum -c TOOLS_SHA256SUMS.txt` 3/3 OK,
   `sha256sum -c SOAK_REMEDIATED_SHA256SUMS.txt` 1/1 OK, unit suite 13/13 OK.
   WARN verdict and `not_run` list unchanged; no raw byte was edited.
