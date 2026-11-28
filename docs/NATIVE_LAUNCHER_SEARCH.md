# Native launcher search (M3)

Status: **implemented and verified**. Base: `ec910d7a7275296ecbc8b5e5c459d356205165d1`
(`integration/canopy-plasma6-20261127` at task start). Owned paths only:

- `canopy_features/launcher/native_launcher_search.py`
- `docs/NATIVE_LAUNCHER_SEARCH.md` (this file)
- `scratch/native_launcher/**` (harnesses and evidence)

No compiled C++/QML, approved artwork, wallpaper, icon, dock geometry, CI
workflow, shared doc or test file was touched. No merge, promotion or approval
was performed; the change is published only as a draft PR.

## What was implemented

`native_launcher_search.py` is the bounded M3 search/ranking composition:

| Entry point | Behavior |
| --- | --- |
| `search_native_catalog_bytes(wire, query, limit=64)` | Pure. Ranks the exact TSV wire already emitted by the upstream catalog producer; no host I/O. |
| `search_native_directory(applications_dir, query, limit=64)` | Single read-only host entry point. Calls the one existing producer, then the pure function. |

Results are immutable `NativeSearchResult(app_id, title, tier, score, index)`
tuples. `index` is the row's position in the upstream catalog wire, so a host
can keep focus/selection aligned without rebuilding the catalog. Tiers come
from the existing ranker: `exact` (4), `prefix` (3), `substring` (2), `fuzzy`
(1), `all` (0). Ordering is total and deterministic: tier, within-tier span,
folded name length, folded name, catalog index. A blank query returns catalog
order. Nothing matches → empty bounded tuple.

### Reuse and negative claims

This module builds **no second catalog service**. Desktop-entry discovery,
bounded file reads, parsing, hidden/duplicate filtering and TSV emission remain
in `native_catalog_producer` → `desktop_entry_parser` →
`launcher_catalog_ingest`; tier semantics remain in `app_search_ranking` and
the query gate in `app_search_casefold`. The module has one import and one call
of `produce_catalog_bytes`, and no file-open, path, subprocess, socket, thread,
timer, cache, launch, telemetry, payment or subscription call. Fixed claim
tokens: `no_duplicate_catalog_service`, `no_network`, `no_paid_tier`,
`no_persistent_state`, `no_process_launch`, `no_telemetry`, `no_visual_change`.
There is no paid tier, no telemetry and no duplicate daemon.

### Bounds (cannot be widened by callers)

| Guard | Ceiling | Refusal |
| --- | --- | --- |
| Results `limit` | 64 (`MAX_RESULTS`) | strict `int`; `bool`, float, text, `0`, `>64` refused |
| Query | 128 chars (`MAX_QUERY_CHARS`) | wrong type, invalid Unicode, oversized NFKC/casefold key refused |
| Catalog wire | 64 KiB (`MAX_SNAPSHOT_BYTES`) | empty, oversized, invalid UTF-8, CR or missing LF refused |
| Wire rows | 1024 (`MAX_ENTRIES`) | counted before decode completes |
| Wire row shape | one TAB, valid desktop id, title ≤ 256 chars | control/format/noncharacter scalars refused |

Every refusal is fail-closed with `NativeSearchError`; no caller id, title or
query is echoed into diagnostics.

## Verification

| Gate | Command | Result |
| --- | --- | --- |
| New contract checks | `python scratch/native_launcher/verify_native_launcher_search.py` | **7 tests, OK, 0 failures/errors** (synthetic) |
| Existing launcher contracts | `PYTHONPATH=<worktree> python -m unittest discover -s tests -p 'test_c100_launcher*.py'` | **429 tests, OK (skipped=1)** |
| Existing runtime/enumeration contracts | `python -m unittest tests.test_classic_launcher_search tests.test_pe003_launcher_catalog_runtime_bridge tests.test_pe063_missing_app_dock_launcher tests.test_pe095_launcher_enumeration_sources` | **49 tests, OK (skipped=2)** |
| Real Plasma launch | `python scratch/native_launcher/plasma_launch_verify.py` | **17/17 checks PASS** |

The synthetic checks cover tier order, tie determinism, bounds, hostile wire
shapes, hidden/duplicate filtering through the upstream producer, and an AST
proof that the module imports only the allowlisted primitives and makes no
forbidden call. The two skips in the pre-existing suites are the Qt-toolchain
conditional tests; they are inherited, not introduced by this change.

### Real Plasma runtime evidence

`scratch/native_launcher/plasma_launch_evidence.json` records the exact
commands and outputs. Guest: existing `Canopy-Test-Plasma6` VM, `canopy` user,
real `kwin_x11` session, access via the existing NAT SSH forward and existing
scratch key (`BatchMode=yes`, `StrictHostKeyChecking=yes`, no password). No VM
start/stop/snapshot/revert, guest config write or credential use occurred.

1. The installed `.desktop` entries for Konsole, Dolphin and Kate were copied
   to host scratch and proved byte-identical by matching host/guest SHA-256.
2. The search primitive consumed scratch copies of those real entries and
   ranked the correct app first in all three cases (`tier=exact`, `score=4`,
   catalog rows = 3 for each query).
3. Those same installed entries were launched through native GIO/GAppInfo in
   the real Plasma session: `konsole` PID 64229, `dolphin` PID 64538, `kate -b`
   PID 64847, each with its own user-session D-Bus name and process tree.
4. All three processes were terminated afterwards; `pgrep` returned `NONE` for
   each, and `VMState` plus `VMStateChangeTime` were unchanged.

Real KDE entries contain invisible Unicode `Cf` scalars in translated
`Name`/`GenericName` lines (U+200D in Konsole/Dolphin, U+200B in Kate), which
the fail-closed upstream parser refuses. The scratch-only copies remove those
`Cf` scalars; `Type=`, `Name=`, `Exec=` and `Categories=` lines are byte-identical
to the installed entries and the installed files are never modified. This is
recorded explicitly in the evidence (`format_scalars_removed`,
`removed_codepoints`, `main_fields_byte_identical`).

## Resource impact and evidence labels

- **REAL_PLASMA_GUEST_SCOPED**: three native app launches, process/D-Bus
  evidence, VM framebuffer screenshot (SHA-256
  `592b23a55cd81e35e163786269a4672890a2da839b5d5c8b05a60aa886ac9514`,
  2,092,539 bytes), captured at
  `C:/Users/X1/AppData/Local/hermes/cache/scratch/native_launcher_runtime/plasma_after_launch.png`.
  Functional evidence only; not visual approval.
- **SYNTHETIC**: pure-Python contract counts and bounded allocations on the
  Windows host. Work per call is O(catalog rows + result limit) with no
  retained state, no polling and no background wakeup.
- **NOT_RUN**: compiled Canopy Qt host wiring, CI-on-guest, screen reader /
  accessibility announcements (this module exposes no visual or a11y path),
  soak/endurance, release gates and owner visual acceptance.
- No stability, security, accessibility or approved-visual trade-off is made
  for a resource gain; no long-lived process is added.

## Evidence integrity

See `scratch/native_launcher/SHA256SUMS.sha256` for file-byte digests of the
harnesses and reports. Key digests:

- `canopy_features/launcher/native_launcher_search.py`:
  `19dc5ca72d0d0a93e5a06364fe809f6bc223ea491b6618a5049695fc6c87899c`
- `scratch/native_launcher/verify_native_launcher_search.py`:
  `5ca05042dd3173fe37df23e25b56b4160f7ffe053a16c3c3319394ecef0905b7`
- `scratch/native_launcher/plasma_launch_verify.py`:
  `a2c5f55ea83e867d5ea684e70a7566571d555380fba871ac8df7fef8e2854502`
- `scratch/native_launcher/synthetic_verify_report.json`:
  `be70201c62a2df69f287990629acac044586d0ed7563fe0ad1c1f87fabaafc2a`
- `scratch/native_launcher/plasma_launch_evidence.json`:
  `37a79a17f598cf38e61668d03c529238c27d22b6777809b01ed0bc238cab7382`

Boundary: this is a pure search/ranking contract plus scoped real-guest
launch evidence. It does not claim a compiled Canopy Qt launcher, Mint/CI
acceptance, release readiness or owner visual sign-off.
