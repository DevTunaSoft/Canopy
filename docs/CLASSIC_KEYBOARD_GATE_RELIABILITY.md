# Classic keyboard gate reliability — concurrent-load timeout root cause

## Scope

Read-only root-cause work on `tools/qa/classic_keyboard_accessibility_gate.py`.
No QML, artwork, geometry, colour, approved assets, PR #626/#627 docs, `main`,
or global config were touched. The baseline and the fix are both pinned at
`128c973e8dc64b5ce1b3c1a3e06fe1e55ed64366`.

## Symptom (exact log)

Concurrent-load full-suite log:
`C:/Users/X1/AppData/Local/hermes/cache/terminal-output/out-1795645104-14640-3bb0.log`
SHA-256 `52081a66e24bc51edb4733ed652ecd77547edf28c5a3fb101d517aac6b10cddc`.

`tests/test_c100_classic_keyboard_accessibility.py` reported **18 tests in
157.563 s, failures=3, errors=3**. All six failures are the same
`subprocess.TimeoutExpired ... timed out after 10 seconds` raised by
`run_driver` and re-raised as `GateError("keyboard driver timed out")`, across
**four distinct test methods**:

1. `test_cli_exit_codes_for_not_run_and_valid_evidence` — ERROR in `setUp`
2. `test_driver_timeout_and_bad_paths_fail_closed` — ERROR in `setUp`
3. `test_source_contract_passes_and_is_read_only` — ERROR in `setUp`
4. `test_driver_negative_controls_never_become_pass` — FAIL for modes
   `reorder`, `wrong_detail`, `extra` (`assertIn(expected, "keyboard driver timed out")`)

The fake driver emits eleven lines and exits immediately; it has no keyboard
work. Every other test in the same class passed in that run, including ones
using the same `setUp` report. The failure set is therefore a per-launch
scheduling lottery, not a step-contract regression.

## Bounded experiments

| # | Experiment | Artifact SHA-256 | Result |
|---|------------|------------------|--------|
| 1 | Affected module alone, unmodified base | `98a7c60f9360b4fd572bf731f26d12a1ef78d31f36d386162e223245c4afd3ed` | 18 tests in 67.590 s, errors=1 — same `setUp` timeout, so contention is present even without the concurrent suite |
| 2 | Timing probe, 10 bare launches + 10 gated launches | script `fcc471d0b826e31ea48dd45d8bba1bff86185231b65298c427d605b768e6c530` | bare interpreter start min/median/max = 0.333 / 1.219 / 2.703 s; `run_driver` = 1.386 / 2.481 / **10.178 s** — one launch crossed the 10 s budget even with a 30 s allowance |
| 3 | New regression tests on pristine detached worktree at `128c973` | `e1328d8e2e5190ef209b1c24207e2adae7db66953f81fab10786fe0ff009d1ee` | 14 tests, failures=1, errors=7 (RED) |
| 4 | New regression tests with the fix | `754f980a077cb036ca1017b041cdc7840274ffe93ac99dbd99a2cb4fb0aaf8bb` | 14 tests, OK (GREEN) |
| 5 | Affected module with the fix on the same host | `842a3c1ced5c7f1eb14ea76a4d3955d8fc69cc47e7d460bc685aa47d1c3b5493` | 18 tests in 55.845 s, OK — zero FAIL, zero ERROR |

Interpretation: host contention is real (a bare Python process start on this
Windows host already costs ~1.2 s median and up to 2.7 s while many suites run
concurrently); the same module passes on other runs without any code change;
and the gate nevertheless has a genuine **stability** defect — one
fixed-timeout attempt with no bounded retry and no in-process coordination —
which converts that transient scheduling delay into a hard FAIL. It is **not**
a keyboard-contract defect: source contracts pass, no false PASS is produced,
and all semantic negative controls remain strict.

## Fix

- `MAX_DRIVER_ATTEMPTS = 2`: retry an **identical** launch once on
  `subprocess.TimeoutExpired` only. The per-attempt timeout is unchanged
  (`MIN_TIMEOUT = 2`, `MAX_TIMEOUT = 90`); total worst-case budget is bounded
  at `2 × timeout`. No timeout was raised.
- A module-level `threading.Lock` serialises launches made by threads inside
  one process, so a single test process cannot inflate its own contention.
  Cross-process host load is absorbed by the bounded retry, not by widening a
  budget.
- `OSError`, nonzero exit, malformed output, oversized output and invalid
  timeout arguments are **never** retried or softened. A driver that keeps
  hanging still raises `GateError` whose text contains `timed out`; no skip,
  no `PASS` promotion, no report-schema change.

## No-weakening negative controls

`tests/test_classic_keyboard_accessibility_gate.py` and
`tests/test_keyboard_gate_contention.py` prove, deterministically: identical
inputs on retry; bounded attempt count; persistent timeout still FAIL; real
sleeping driver with `MIN_TIMEOUT` still FAIL; `OSError`, nonzero exit and
malformed step lines are single-attempt; timeout bounds unchanged; concurrent
in-process launches serialised; reordered step reports still rejected with
`step contract`; report still `platform=offscreen`, `input_mode=keyboard-only`,
and `screen_reader`/`mint_acceptance`/`visual_approval` = `NOT_RUN`.

## Full suite

See `Current head` and the full-suite log SHA in the PR body. The suite was
run once on the exact code/test tree that this commit contains; only this
evidence document was edited afterwards.

## Resource / evidence note

- `SYNTHETIC`: the launch timings above are short host microbenchmarks on a
  contended Windows host, not a real Qt runtime measurement.
- `NOT_RUN`: compiled Qt offscreen self-test at this exact head, Linux Mint
  acceptance, and any screen-reader behaviour. The gate records
  `screen_reader = NOT_RUN` and never infers an announcement from key steps.
- No new services, threads beyond the bounded lock, background processes or
  visual assets are added; the retry adds at most one extra bounded
  subprocess launch on a transient timeout and zero on the normal path.
