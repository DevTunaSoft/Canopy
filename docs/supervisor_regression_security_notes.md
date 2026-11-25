# Supervisor regression and security evidence notes

Task: `regression-security-notes`
Branch: `feat/canopy-supervisor-regression-security-notes`
HEAD at time of run: `250257df8571d1ce4fa3d736f7072c4bc22dd2c1`
Environment: Windows (win32), Python 3.14.10, source worktree only.
Byte-code writes disabled for every Python command with `PYTHONDONTWRITEBYTECODE=1`.
Result vocabulary: PASS / FAIL / BLOCKED / NOT RUN, per `docs/QUALITY.md`.

These results are **CI-SCOPED / source-context only**. They are not Linux Mint,
compositor, security-runtime, usability or visual acceptance evidence. No
product-wide release claim follows from this file.

## Commands run and results

All commands run from the worktree root. Output excerpts below are copied from
the actual runs; durations and counts are exact.

### 1. Full discovery suite — PASS

Command:
```
$env:PYTHONDONTWRITEBYTECODE="1"; py -3 -m unittest discover -s tests -v
```
Result excerpt:
```
Ran 282 tests in 16.386s

OK (skipped=53)
```
Totals: 282 tests run, 0 failures, 0 errors, 53 skipped, therefore 229 passed.
The 53 skips are POSIX-only tests on Windows (breakdown below). An all-skipped
run would not be green; here 229 tests actually executed and passed.

### 2. Canopy supervisor suite — PASS

Command:
```
$env:PYTHONDONTWRITEBYTECODE="1"; py -3 -m unittest tests.test_canopy_supervisor -v
```
Result excerpt:
```
Ran 42 tests in 4.274s

OK
```
Totals: 42 tests run, 0 failures, 0 errors, 0 skipped.
Lines such as `SUPERVISOR_FAIL: scope overlaps protected paths: canopy/assets/*`
and `SUPERVISOR_FAIL: duplicate task id: alpha` are expected negative-control
output printed inside tests that assert fail-closed behavior. They are not test
failures; the harness reported `ok` for those tests and `OK` overall. Printed
`INITIALIZED`, `ADDED`, `CHECK_PASS`, dashboard and `PAUSED`/`RESUMED` lines are
fixture output from subprocess-driven tests, not actions on this worktree.

### 3. Performance evidence gate suite — PASS

Command:
```
$env:PYTHONDONTWRITEBYTECODE="1"; py -3 -m unittest tests.test_perf_evidence_gate -v
```
Result excerpt:
```
Ran 10 tests in 0.060s

OK
```
Totals: 10 tests run, 0 failures, 0 errors, 0 skipped.

Important: one test prints a JSON report such as
`{"cpu_percent_one_core_calculated": 0.5246, ..., "measured_seconds": 305.0,
"pss_kib_peak": 65000, "linux_mint_guest_proven": false, "release_approved": false,
"scope": "self-reported numeric idle targets only", "status": "PASS"}`.
This is a **synthetic self-reported test fixture** used to exercise the gate's
validator. It is not a real five-minute measurement, it explicitly sets
`linux_mint_guest_proven` and `release_approved` to `false`, and none of its
numbers are adopted here as evidence.

### 4. Reliability 99 gate matrix suite — PASS

Command:
```
$env:PYTHONDONTWRITEBYTECODE="1"; py -3 -m unittest tests.test_reliability_99_gate_matrix -v
```
Result excerpt:
```
Ran 6 tests in 0.010s

OK
```
Totals: 6 tests run, 0 failures, 0 errors, 0 skipped. These tests enforce matrix
shape (11 domains x 9 gates = 99 unique gates, P0 gaps remain explicit, optical
and Mint acceptance remain blocked). Passing them confirms the audit matrix is
internally consistent; it does not close any gate.

### 5. Foundation checker — PASS

Command:
```
$env:PYTHONDONTWRITEBYTECODE="1"; py -3 tools/check_foundation.py
```
Result excerpt:
```
PASS: foundation files, tagline, and local Markdown links
```

## Known POSIX-only skips on Windows

The 53 skips in the full discovery run fall into three reasons, counted from the
run output:

| Count | Skip reason (verbatim) |
|---|---|
| 21 | `Desktop Entry Exec quoting and execute-bit checks are POSIX-only` |
| 2 | `POSIX symlink policy is not portable to Windows` |
| 30 | `POSIX executable-bit and shell-script semantics are unavailable on Windows` |

These are platform gaps, not product test failures. Per the task direction, PR
#135 isolates these POSIX-only skips. This note did not inspect PR #135 content
(no git history or open-PR load was performed, per task rule 1), so that
isolation is recorded as reported, not independently verified here.

## Five-minute CPU and PSS — NOT RUN

Real five-minute idle CPU and PSS measurement on Linux Mint: **NOT RUN**. No
figures are reported or invented. This is the honest gate state:

- Audit gate R066 (five-minute idle CPU, PSS, wakeups recorded on Mint): BLOCKED
  in `docs/RELIABILITY_99_GATE_AUDIT.md`; NOT RUN in this environment.
- Audit gate R067 (short informational Qt CPU/PSS sample on Ubuntu Actions):
  CI-SCOPED in the audit; not reproduced here.
- `docs/QUALITY.md` lists `<= 1%` average shell CPU and `<= 200 MiB` PSS as
  initial targets, not verified results. No target is presented as a measurement.
- The JSON printed by the performance gate test (section 3) is a test fixture,
  not a substitute for this measurement.

## Security evidence scope

No secrets, tokens or credentials were exposed by these runs. The supervisor and
host test suites include negative controls for protected-path rejection,
credential redaction, missing-token fail-closed, symlink rejection, duplicate-key
and path-traversal rejection, and untrusted-pack/no-execution behavior; those
controls passed in the scoped runs above. This is source-level CI-SCOPED
evidence only. Audit gates R029 (signature/provenance verification), R030 (QML
isolation), R031 (runtime capability enforcement) and R032 (installer privilege)
remain GAP in the audit and are not closed by this note.

## Docs consulted

- `AGENTS.md` — engineering contract (read once).
- `docs/QUALITY.md` — quality gates and measurement rules (read once).
- `docs/RELIABILITY_99_GATE_AUDIT.md` — 99-gate acceptance matrix (read once).
  Initial totals restated there: 18 CI-SCOPED, 73 GAP, 8 BLOCKED. No percent
  complete score is computed from these scoped passes.
- `README.md` and `docs/ARCHITECTURE.md` were not loaded in this run; the task
  rule set specified AGENTS.md and docs/QUALITY.md, and no code behavior was
  changed.

## Change and publication record

- Only repository file written: `docs/supervisor_regression_security_notes.md`
  (this file). The task objective also names the same path in uppercase; the
  owned, editable path is the lowercase spelling used here. On this Windows
  filesystem the two spellings resolve to one file.
- Evidence JSON written outside the worktree to
  `...\evidence\regression-security-notes\evidence.json` with `commit_sha`
  set to `PENDING` and `draft` set to `true`.
- `PYTHONDONTWRITEBYTECODE=1` was set for all Python commands. No `__pycache__`
  directories were found in the worktree before or after the runs.
- No git commit, push, PR creation, merge or branch change was performed. The
  supervisor publishes; this note is draft evidence only.
