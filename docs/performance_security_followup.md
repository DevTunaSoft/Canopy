# Performance and security gate gaps — follow-up

**Status: evidence review, not a release claim.** Recorded 2026-11-21 against
worktree `performance-security-followup`, branch
`feat/canopy-supervisor-performance-security-followup`.
Commit SHA: `PENDING` (supervisor publishes; no commit made here).

Scope: read `docs/QUALITY.md` and `docs/RELIABILITY_99_GATE_AUDIT.md` once,
ran the available offline gate tests, and recorded the remaining performance
and security gaps. No artwork, icons, wallpaper, dock, Qt GUI, workflow or
supervisor source was touched. Only this file changed.

## Basis

- `docs/QUALITY.md` states all budgets are initial targets, not verified
  results: PSS `<= 200 MiB` and average shell-owned CPU `<= 1%` of one core
  over a **five-minute** idle measurement on the reference machine. It requires
  commit SHA, hardware, distro/kernel, driver, compositor, commands, duration,
  before/after metrics and explicit PASS/FAIL/BLOCKED/NOT RUN.
- `docs/RELIABILITY_99_GATE_AUDIT.md` is a 99-question acceptance matrix, not
  99 completed tests. Its totals: 18 CI-SCOPED, 73 GAP, 8 BLOCKED. It forbids a
  percent-complete score and requires exact SHA, environment, command and
  artifact per completed gate.
- `docs/QT_PERFORMANCE_EVIDENCE_GATE.md` documents the only existing resource
  artifact: a schema-1, ~5-second Ubuntu/Xvfb headless baseline. Its numeric
  PASS is explicitly `release_approved=false`, `linux_mint_guest_proven=false`,
  `visual_approval=false`.

## Offline gate tests run (exact commands and output)

Environment: Windows, Python 3.12.10, pytest 9.2.0; test runner `unittest`.

| Command | Result | Output excerpt |
|---|---|---|
| `python -m unittest discover -s tests -v` | PASS (53 POSIX-only tests skipped on Windows) | `Ran 288 tests in 7.775s` / `OK (skipped=53)` |
| `python -m unittest tests.test_perf_evidence_gate tests.test_reliability_99_gate_matrix -v` | PASS | `Ran 16 tests in 0.056s` / `OK` |
| `python -m unittest tests.test_shell_pack tests.test_shell_pack_registry -v` | PASS | `Ran 45 tests in 2.978s` / `OK` |

These runs prove only that the validator, matrix and metadata contracts behave
as coded in this source checkout. They are not Mint, compositor, runtime,
usability, security or visual acceptance.

## Five-minute CPU / PSS — NOT RUN

**Result: NOT RUN. No figures recorded and none invented.** No real
five-minute idle sample, Mint guest report or schema-2 measurement artifact
exists in this worktree (`**/*baseline*.json`: no files found). Gate R066 stays
BLOCKED. A real value needs a reproducible guest sampler, pinned source/binary
SHA, recorded environment and exclusions, sampling log and human review.

The perf test run prints JSON containing `cpu_percent_one_core_calculated:
0.5246`, `pss_kib_peak: 65000`, `measured_seconds: 305.0`,
`linux_mint_guest_proven: false`, `release_approved: false`. Those numbers are
**synthetic validator fixtures** from `tests/test_perf_evidence_gate.py`
(`long_case()`, all-f/e placeholder hashes). They are not Canopy measurements
and must never be reported as idle CPU or PSS.

## Performance gate gaps

From `RELIABILITY_99_GATE_AUDIT.md`, "Resource efficiency & stability":

| Gate | Priority | Evidence | Acceptance question (gap) |
|---|---|---|---|
| R064 | P0 | GAP | Five user-selectable performance profiles and Auto Mode work |
| R065 | P0 | GAP | No inactive shell keeps duplicate desktop services running |
| R066 | P0 | BLOCKED | Five-minute idle CPU, PSS and wakeup metrics recorded on Mint |
| R067 | P1 | CI-SCOPED | Short informational Qt CPU/PSS sampling runs on Ubuntu Actions |
| R068 | P1 | GAP | Cold start, warm start and responsiveness have reproducible budgets |
| R069 | P1 | GAP | Repeated shell switching has no retained subscriptions or memory leak |
| R070 | P1 | GAP | Integrated/discrete/VM/software GPU fallback behaves gracefully |
| R071 | P1 | GAP | Low-spec 4 GB RAM guests stay responsive under realistic app load |
| R072 | P2 | GAP | Battery, suspend and thermal workloads are benchmarked |

R067 is CI-SCOPED only: a ~5-second Ubuntu/Xvfb headless baseline. It must not
be promoted to the R066 five-minute Mint acceptance. The ≤200 MiB PSS and ≤1%
CPU targets remain unverified targets, not results.

## Security gate gaps

From `RELIABILITY_99_GATE_AUDIT.md`, "Security, trust & adversarial inputs":

| Gate | Priority | Evidence | Acceptance question (gap) |
|---|---|---|---|
| R028 | P0 | CI-SCOPED | Manifest duplicate keys, invalid permissions and symlink paths are rejected |
| R029 | P0 | GAP | Signature and publisher provenance are verified before pack execution |
| R030 | P0 | GAP | QML plugin isolation prevents arbitrary file and D-Bus access |
| R031 | P0 | GAP | Runtime capability permissions are enforced, not merely described |
| R032 | P0 | GAP | Untrusted updater/installer paths cannot gain elevated privileges |
| R033 | P1 | GAP | Filesystem TOCTOU races and symlink replacements are fuzz-tested |
| R034 | P1 | GAP | Pack archives reject zip slips, decompression bombs and dangerous links |
| R035 | P1 | GAP | Dangerous desktop-entry or URL protocols cannot bypass launch policy |
| R036 | P1 | GAP | Dependency, SBOM and vulnerability scanning gate releases |

Adjacent Shell Pack / privacy gaps still open: R023, R024 and R029–R032 are P0
GAP (capability-checked API, untrusted QML isolation, signatures, enforced
permissions, updater privilege). R094 (no silent collection of passwords,
tokens or documents) is P0 GAP; R095 and R096 (bounded/exportable logs,
user-controlled crash telemetry off by default) are P1 GAP.

The offline tests do evidence R028-shaped behaviour only: duplicate JSON keys,
invalid permissions, absolute/traversal/URI entrypoints, symlinked manifest or
entrypoint, bounded manifest size, unknown fields/schema and duplicate or
out-of-catalog symlink rejection are rejected in `test_shell_pack` and
`test_shell_pack_registry`. This is source-level metadata validation. It is not
runtime sandboxing, signature verification, capability enforcement or proof
that untrusted QML is isolated.

## What would close the gaps

- Collect a real schema-2 five-minute Mint idle sample with source/binary SHA
  pins, guest provenance, exclusions and sampling log for R066.
- Add reproducible cold/warm launch, switch/leak and GPU-fallback budgets for
  R068–R071.
- Implement and test signed provenance, enforced runtime capabilities, QML
  plugin isolation and least-privilege updater paths for R029–R032.
- Add fuzz/adversarial coverage for TOCTOU, archives and launch policy and wire
  SBOM/vulnerability scanning into releases for R033–R036.

## Decision discipline

Green source tests do not make any P0 gate complete. No five-minute CPU/PSS
claim, no Mint compatibility claim, no runtime security claim and no release
approval is made here. Keep any PR draft until exact-SHA, environment, command
and artifact evidence exists for the relevant gates. The supervisor publishes;
this task made no commit, push, PR, merge or branch change.
