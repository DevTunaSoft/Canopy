# Shell-service efficiency audit (reliability + security, base 128c973)

## Scope and method

- Worktree: `C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy_perf_clean_128c973`, branch `perf/shell-service-audit-128c973`, exact base `128c973e8dc64b5ce1b3c1a3e06fe1e55ed64366` (clean at audit start).
- Read-only first pass over **15 owned source files / 3,236 lines** in `canopy_features/reliability/**` and `canopy_features/security/**`. No other path was edited.
- Static counts were produced by AST/text scan (`static_owned_counts.py` in scratch) and the `performance-memory-audit` scanner. Dynamic checks are **SYNTHETIC** deterministic probes of the pure functions (finite counting mappings, `tracemalloc`), not a running Classic shell. Real desktop PSS/CPU, Mint guest, Qt launch and screen-reader behavior are **NOT_RUN** on this Windows host.
- No RSS/CPU value in this report is a real-runtime measurement. No timing-based speedup is claimed.

## Static baseline (quantified)

| Category | Count | Evidence / triage |
|---|---|---|
| Owned Python files scanned | 15 | 8 reliability, 7 security |
| Source lines | 3,236 | AST parse succeeded for all 15 |
| Skill scanner `py_whole_read` / `py_subprocess` hits | 0 / 0 | `static_baseline.json`; no whole-file reads or subprocess launches in owned modules |
| Timer / polling / thread primitives | **0 real** | 2 raw AST `.join()` name matches in `log_size_caps.py:119` and `path_jail_checks.py:96` are `str.join`, not thread joins; corrected count 0. No `time.sleep`, `QTimer`, `threading`, `poll` or `wait` call sites. Every module docstring states event-driven/caller-driven operation and the code agrees. |
| Logging / `print()` calls | 0 | No `logging` import, no log statement; action text is never stored or logged (`privilege_boundary.py:5`) |
| Bounded `deque(maxlen=...)` stores | 3 | `event_delivery_loss.py:111-113`, `lock_session_events.py:138`, `screen_topology_change.py:221` |
| Lazy single-slot caches with invalidation | 16 `_cache` references across 6 modules | e.g. `event_delivery_loss.py:114,133,141,160,200,220`, `lock_session_events.py:139,158,188`, `theme_transition_rollback.py:94,135,164,169,182`, `screen_topology_change.py:105,123,131-134`; all cleared on every writer; no unbounded cache found |
| Other byte/entry caps | 4 | `DiagnosticBuffer` max-bytes (`log_size_caps.py:62-88`), incremental JSON cap (`log_size_caps.py:107-115`), `MAX_STATE_BYTES` (`startup_checkpoints.py:26,143,157`), per-string recursion/total caps (`pack_manifest_metadata.py:34-39,144-169`) |
| Duplicated function names across modules | 16 names | 7 are substantive validators duplicated in the three composition modules: `_count`, `_flag`, `_text`, `_bounded_text`, `_session_view`, `_delivery_view`, `_derive_status` (e.g. `host_reliability_snapshot.py:149,155,209,247`; `recovery_readiness_snapshot.py:153,165,219,253,276`; `session_lifecycle_snapshot.py:142,148,154,160,204,281`). Static duplication only; **performance effect HYPOTHESIS**, not measured and not changed. |
| Unbounded pre-validation copy sites | **1 (confirmed)** | `pack_manifest_metadata.py:186` (base): `data = dict(manifest)` before `_scan` applied `MAX_FIELDS = 64` |

## Confirmed defect and fix

**`canopy_features/security/pack_manifest_metadata.py:186` (base): untrusted mapping fully copied before the field bound.** `to_safe_metadata()` is a public trust boundary for Shell Pack metadata and is also called by `security_decision_snapshot._metadata()`. Its module contract says its bounds "keep a hostile mapping from growing memory", but `dict(manifest)` materialized every caller-supplied field before `_scan()` checked `len(value) > MAX_FIELDS`. A caller-supplied mapping with *n* fields therefore caused O(n) allocation before rejection.

Deterministic **SYNTHETIC** probe (finite counting `Mapping`, `MAX_FIELDS+1` entries):

| Probe | Base 128c973 | After fix |
|---|---|---|
| Items consumed before `PackValidationError` | 65 | **0** |
| `tracemalloc` peak, 4,096-field hostile dict | 104,734 B | **528 B** |
| `tracemalloc` peak, 65,536-field hostile dict | 1,923,312 B | **528 B** |
| `tracemalloc` peak, 64-field (at-bound) input | 6,530 B | 6,681 B (unchanged within noise; same successful path) |

Fix (`pack_manifest_metadata.py:186-195` after patch): check `len(manifest) > MAX_FIELDS` before `dict()`, and translate a hostile `__len__` exception to `PackValidationError` so the new probe cannot leak a built-in error. Behavior for at-bound and valid input is unchanged; nested oversized mappings are still rejected by `_scan`.

Regression tests: `tests/test_shell_service_efficiency_audit.py` (new, 5 tests). RED on base: `test_oversized_mapping_is_rejected_before_items_are_consumed` failed with `65 != 0`; the other four were passing negative controls. GREEN after fix: 5/5 pass. No unbounded iterable, no timing threshold.

## Findings deliberately not changed

- **Duplicated validators in the three snapshot composers** (7 names, static count above): consolidating them would reduce source lines, but each runs once per `compose()` on already-bounded inputs. Performance effect **HYPOTHESIS**; not a bottleneck, not measured, no rewrite.
- **`untrusted_uri_schemes.validate_uri_intent()` normalizes the default 3-scheme allowlist on every call** (`untrusted_uri_schemes.py:35-58,67`): repeated work on a gate path, but the work is one 3-element frozenset build. Effect **HYPOTHESIS**; no change.
- **`ScreenTopologyModel.history` rebuilds a ≤64-element tuple per read** (`screen_topology_change.py:228-230`) while sibling models cache lazily: allocation is bounded and host call frequency is unknown. Effect **HYPOTHESIS**; no change.
- No timers, polling, unbounded caches, repeated heavy initialization or excessive logging were found in owned modules; nothing to fix in those categories.

## Verification actually run (exact commands, all PASS after fix)

```
python -m unittest tests.test_shell_service_efficiency_audit -v        # 5 tests, OK
python -m unittest discover -s tests -p 'test_c100_security_pack_manifest*.py'   # 46 tests, OK
python -m unittest discover -s tests -p 'test_c100_security_decision_snapshot*.py'  # 36 tests, OK
python tools/check_foundation.py                                       # PASS
python -m py_compile canopy_features/security/pack_manifest_metadata.py tests/test_shell_service_efficiency_audit.py
```

Before the fix the same targeted suites were green (46 + 36) and the new module was RED (1 failure, 4 controls passing). `check_foundation` passed before and after. No full suite or compiled Qt build was run, per the bounded-work directive.

## Resource impact / evidence labels

- **SYNTHETIC**: all `tracemalloc` and counting-proxy numbers above (pure function on a Windows host, not a shell process).
- **NOT_RUN**: real Classic shell PSS/RSS, idle CPU fraction, Mint guest acceptance, Qt launch integration, extended-operation leak sampling, and screen-reader/announcement behavior. This change touches no accessibility, announcement or visual path; there is no screen-reader behavior to claim.
- The change removes work (one whole-mapping copy on rejection) and adds one `len()` call per accepted call. It does not trade stability, security, accessibility or approved visuals for a minor gain: rejection semantics and error text are unchanged, valid input is unaffected, and the guard itself fails closed.
- Ranked next steps requiring runtime measurement: (1) sample the real Classic shell on Mint to establish PSS/CPU baseline before any consolidation of the duplicate validators; (2) count actual URI-gate call frequency in a host trace before caching the normalized allowlist; (3) profile `ScreenTopologyModel.history` read frequency before adding a cache. Suggested sampler for the owner on Linux: `python tools/measure-memory.sh <shell-pid> 60 1 sample.csv` (script exists in the repo; **NOT_RUN** here).
