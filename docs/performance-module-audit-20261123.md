# Pure-Python module performance/memory audit — 2026-11-23

Worktree: `perf/integration-module-audit-20261123` (isolated, branched from
`origin/integration/canopy-classic-20261123` @ `4c0d742`). Scope: the 58 Python
modules under `canopy_features/` plus their 58 `tests/test_c100_*.py` files.
No visual/QML/C++/asset, supervisor, VM, or other-branch work was performed.

## 1. Method and its limits

Measured on Windows 11, CPython 3.14.9 (`python3`), in the isolated worktree.
Four baselines were taken **before any edit**:

1. `python3 static-audit-skill.py canopy_features baseline-static.json`
   (the `static-audit.py` script shipped with the `performance-memory-audit`
   skill, copied verbatim into the worktree).
2. Cold import of all 58 modules in a fresh interpreter, 5 runs
   (`measure_perf.py`, kept outside the repo in scratch).
3. `tracemalloc` + `time.perf_counter` over five bounded, representative
   operations, with identical inputs and repetition counts before and after.
4. `python3 -m unittest discover -s tests -p 'test_c100_*.py'`, three runs in
   an untouched worktree at `4c0d742` and three runs after the change.

Limits, stated plainly:

- **No application runtime profile was run.** There is no Linux desktop shell,
  Qt runtime or Mint VM here. All numbers are CPython-level import timings,
  synthetic bounded-operation microbenchmarks and unit-test timings — not RSS,
  heap, frame-time, GPU or wakeup measurements of a running Classic session.
- The host is **very noisy**: identical untouched operations varied by up to
  ~40% between harness runs (e.g. `rank_applications` 51,702 -> 52,391 ->
  40,0 µs/call across runs; cold-import median 254.91 -> 355.25 ms). Absolute
  before/after harness timings are therefore *not* used as proof. The claim
  below rests on a **paired, alternating, in-process A/B** plus a deterministic
  allocation count.
- The combined-repository baseline (1271 tests, 3 failures + 37 errors from
  pre-existing Windows-only permission tests on the untouched base) is a
  known precondition and is **not** attributed to this change. The scoped
  c100 suite passes on both trees.

## 2. Baseline static risk table

`static-audit.py` over `canopy_features/` (58 `.py` files, before and after):

| Pattern | Count before | Count after |
|---|---:|---:|
| `py_subprocess` | 1 | 1 |
| `py_whole_read` | 0 | 0 |
| all JS/C patterns | 0 | 0 |

The module set contains no whole-file reads or unbounded FIFO drains. Static
density was near zero, so the triage moved to measured hot paths. `cProfile`
of the baseline suite (1,018,104 calls / 6.233 s) showed test time dominated by
filesystem I/O (`_io.open` 1.158 s, `nt.mkdir` 0.476 s) rather than feature
code; the hottest feature functions were `_subsequence_span` (0.024 s / 4011
calls), `_plain_token` (0.022 s), `rank_matches` (0.021 s) and
`window_state_capabilities.apply` (0.018 s).

### Baseline measurements (before edit)

| Measurement | Baseline |
|---|---|
| Cold import of 58 modules, median of 5 fresh interpreters | 254.91 ms (runs: 254.91, 244.68, 271.56, 255.54, 242.62) |
| `build_launch_argv`, 16x900-byte tokens, 200 reps | 1120.67 µs/call; tracemalloc peak Δ 2249 B |
| `bounded_json_report`, 800-event / 65,235-byte report, 100 reps | 43,796.03 µs/call; peak Δ 633,683 B (6,336.8 B/call) |
| `rank_applications`, 2048 names fuzzy, 30 reps | 51,702.05 µs/call; peak Δ 743,701 B |
| `rank_matches`, 4096 names, 30 reps | 62,228.0 µs/call; peak Δ 844,893 B |
| `DiagnosticBuffer.feed`, 64 KiB, 100 reps | 20.9 µs/call; peak Δ 197,067 B |
| c100 suite (untouched tree @ 4c0d742), 3 runs | 913 tests, OK (6 skipped); unittest seconds 7.769 / 5.923 / 5.180, median 5.923 |

## 3. Confirmed issue and fix

`bounded_json_report` counted each JSON chunk's encoded byte length by
allocating a temporary `bytes` object, then discarded it:

- **Before** — `canopy_features/security/log_size_caps.py:105-106`:
  `encoded = piece.encode("ascii"); total += len(encoded)`
- **After** — `canopy_features/security/log_size_caps.py:101-108`:
  the encoder at line 99 sets `ensure_ascii=True`, so every chunk is ASCII and
  `len(piece)` *is* its UTF-8 byte count; `total += len(piece)` at line 108.

For the 65,235-byte benchmark report, `iterencode` yields **14,405 chunks**, so
the fix removes **14,405 short-lived `bytes` allocations per report** — a
deterministic count, not an estimate. The invariant is asserted by
`tests/test_c100_security_log_size_caps.py:136`
(`test_iterencode_chunks_are_ascii_by_contract`, covering Unicode, surrogate
pairs and escapes) and the unchanged cap behaviour by line 150
(`test_cap_boundary_is_byte_exact_with_escaped_unicode`).

Paired in-process A/B (both module versions loaded in one interpreter, 6
alternating rounds, 300 calls per round, 800-event payload):

| Session | Baseline median | After median | Delta |
|---|---:|---:|---:|
| 1 | 19,467.5 µs/call | 14,298.4 µs/call | -26.5% |
| 2 | 12,405.9 µs/call | 8,672.5 µs/call | -30.1% |

Minimums: 13,389.1 -> 11,695.9 µs (session 1), 5,123.2 -> 4,603.7 µs (session 2).

### Candidates evaluated and deliberately not shipped

- Reusing per-token UTF-8 byte counts in `apps/launch_argv.py` (avoid a second
  encode in `_assemble`): implemented, regression-tested, then **reverted** —
  paired A/B showed no reliable gain (median 4,420 vs 4,596 µs/call; mins
  3,197 vs 3,020), and the extra private-helper plumbing was not justified.
- Removing the position list in `launcher/app_search_ranking._subsequence_span`
  and an ASCII fast path in `launcher/app_search_casefold._normalize`: tested
  in scratch copies; no reliable gain (ranking median 29,796 vs 31,726 µs,
  casefold median 33,024 vs 35,889 µs). Not applied.

Peak `tracemalloc` deltas for the other four operations were byte-identical
before/after, as expected: this fix removes transient allocations that never
raise peak. No memory-growth claim is made for them.

## 4. Verification actually run

Exact commands (from the worktree):

```
python3 static-audit-skill.py canopy_features <out>.json
python3 measure_perf_canopy.py <label> <repo> <out>.json
python3 -m cProfile -o baseline-profile.prof -m unittest discover -s tests -p 'test_c100_*.py'
python3 -m py_compile canopy_features/security/log_size_caps.py tests/test_c100_security_log_size_caps.py
python3 -m unittest tests.test_c100_security_log_size_caps -v
python3 -m unittest discover -s tests -p 'test_c100_*.py'
bash -n tools/measure-memory.sh
python3 paired_json.py        # scratch, paired in-process A/B
```

Outcomes:

- `py_compile`: OK. Focused tests: **18 tests, OK** in 0.065 s.
- Full scoped c100 suite: **915 tests, OK (6 skipped)** — the original 913 plus
  the two new regression tests. Three post-change runs: unittest seconds
  4.197 / 3.770 / 3.521 (median 3.770). The A/B suite comparison is confounded
  by warm-cache ordering and host noise, so **no suite-level speedup is claimed**.
- Static audit after the edit: 58 files scanned, `py_subprocess: 1`, unchanged.
- `bash -n tools/measure-memory.sh`: OK (see limit above; not executed).

## 5. Ranked next steps that need runtime measurement

1. Run the Classic Qt session on the owner's Linux desktop and sample RSS across
   repeated launcher searches and log-report generation:
   `tools/measure-memory.sh <pid> 120 1 rss.csv`. RSS that trends upward across
   identical cycles needs a real heap snapshot before any further change.
2. Profile a full launcher session with `sysprof` and allocate with
   `valgrind --tool=massif` if step 1 shows growth; focus on
   `app_search_ranking.rank_applications` and `app_search_casefold.rank_matches`,
   which dominate our synthetic catalog benchmarks (peak Δ 743,701 B and
   844,893 B per call) but were not shown to be application hot paths.
3. Only after runtime evidence, revisit the three rejected candidates above.
   Do not change C ownership, signal lifetimes or any visual asset on static
   evidence alone.
