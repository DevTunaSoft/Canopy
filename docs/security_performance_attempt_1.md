# Offline security and resource gates — attempt 1

Task: `security-performance-gate-attempt-1`
Branch: `feat/canopy-supervisor-security-performance-gate-attempt-1`
Commit SHA (workspace HEAD at time of run): `3209dc6459086bcfc18f900bf88062f7bb187ad0`
Environment: Python 3.12.10, pytest 9.2.0 available; tests run with `python -m unittest` per project convention.
Working directory: worktree root `security-performance-gate-attempt-1`.

No files were edited except this report. No CI, workflow, approved design,
artwork, dock icon, wallpaper, or Qt GUI file was changed. No git commit,
push, PR, merge, or branch change was performed.

## Commands and results

All commands were run from the worktree root. Output excerpts are verbatim.

### 1. Reliability matrix (offline document-schema gate)

Command: `python -m unittest tests.test_reliability_99_gate_matrix -v`

Result: **PASS** — `Ran 6 tests in 0.027s` / `OK`

Excerpt:
```
test_ninety_nine_uniquely_numbered_gates ... ok
test_eleven_distinct_domains_nine_gates_each ... ok
test_every_entry_has_priority_and_explicit_not_done_status ... ok
test_every_p0_gap_remains_explicit ... ok
test_optical_and_mint_acceptance_remain_blocked ... ok
test_owner_rules_no_deadline_or_reviewer_recruitment ... ok
Ran 6 tests in 0.027s
OK
```

Scope note: this is a document-schema check, not evidence that the 99 review
gates pass. The test module docstring states it is "NOT evidence that
unimplemented or blocked runtime capabilities have passed." No product-wide
percent-complete is claimed.

### 2. Performance evidence gate (offline validator gate)

Command: `python -m unittest tests.test_perf_evidence_gate -v`

Result: **PASS** — `Ran 10 tests in 0.074s` / `OK`

Excerpt:
```
test_five_minute_numeric_targets_are_not_release_claims ... ok
test_real_old_five_second_baseline_never_becomes_release_pass ... ok
test_short_or_sparse_real_report_is_not_sufficient ... ok
test_cpu_and_memory_targets_are_independent ... ok
test_raw_tick_recalculation_defeats_fake_passing_percent ... ok
test_reject_mismatched_source_or_binary_and_self_reported_method ... ok
test_reject_nan_bool_negative_and_unbounded_values ... ok
test_reject_impossible_counter_sequence_or_memory_peak ... ok
test_bounded_report_reader_and_cli_status_codes ... ok
test_reject_symlinked_or_non_json_report ... ok
Ran 10 tests in 0.074s
OK
```

Scope note: these tests exercise the validator with **synthetic** data only.
The module docstring says "No invented Qt idle performance; synthetic numbers
test the validator only." The validator emitted a synthetic `status: PASS`
object with `linux_mint_guest_proven: false`, `release_approved: false`, and
`visual_approval: false`. Those numbers (`cpu_percent_one_core_calculated:
0.5246`, `pss_kib_peak: 65000`) are fabricated test fixtures, **not** real
measurements, and are not reported as results here.

### 3. Shell pack validation (offline metadata gate)

Command: `python -m unittest tests.test_shell_pack -v`

Result: **PASS** — `Ran 24 tests in 0.591s` / `OK`

Excerpt:
```
test_checked_in_starter_is_valid ... ok
test_cli_accepts_starter_and_rejects_missing_pack ... ok
test_future_unsupported_host_api_fails_closed ... ok
test_unknown_manifest_schema_fails_closed ... ok
test_reject_nonempty_permissions ... ok
test_entrypoint_path_traversal_rejected ... ok
test_symlinked_manifest_rejected ... ok
test_duplicate_json_keys_rejected ... ok
test_manifest_size_is_bounded ... ok
Ran 24 tests in 0.591s
OK
```

### 4. Shell pack validator CLI — valid starter (positive control)

Command: `python tools/check_shell_pack.py examples/shell-pack-starter`

Result: **PASS** (exit 0)

Excerpt:
```
SHELL_PACK_MANIFEST_PASS: org.example.canopy.minimal (metadata only; no runtime loading or trust verification)
EXIT=0
```

Scope note: per AGENTS.md and the CLI output, this is metadata validation
only — not a runtime loader, permission sandbox, security approval, or
evidence of same-session switching.

### 5. Shell pack validator CLI — missing pack (negative control)

Command: `python tools/check_shell_pack.py examples/does-not-exist-pack`

Result: **PASS** (expected fail-closed, exit 1)

Excerpt:
```
SHELL_PACK_FAIL: pack must be a real local directory
EXIT=1
```

## Five-minute CPU / PSS — NOT RUN

Result: **NOT RUN**. No real Linux Mint guest measurement exists.

There is no schema-2 five-minute idle report in the repository, and
`tools/qa/perf_evidence_gate.py` is an offline validator, not a benchmark
runner. Its own `--help` text says existing 5-second headless Qt baselines are
deliberately `INSUFFICIENT_EVIDENCE` for the five-minute Linux Mint release
targets and that self-reported data is not signed guest provenance.

No CPU percentage, PSS figure, duration, sample count, hardware, distro,
kernel, driver, or compositor value is reported as a measurement. No figure is
invented. The synthetic numbers in test 2 are documented above as fixtures and
are explicitly excluded from any result claim.

## Blocked / not-run summary

- Reliability 99 gates: PASS for document schema only; runtime gates remain
  GAP/BLOCKED/CI-SCOPED per the audit matrix — no new claims made.
- Performance evidence: PASS for validator behavior only; five-minute CPU/PSS
  on a real Mint guest NOT RUN.
- Shell packs: PASS for metadata validation and fail-closed negative control;
  runtime loading, sandbox, trust, and A→B→A switching NOT RUN and not claimed.
