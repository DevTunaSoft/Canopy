# PE-062 cache bounding audit — Files preview navigation history

Base: `b8735dcc e07c43dc553488a8542690d30da0449f` (`integration/canopy-classic-20261123`).

## 1. Method and its limits

Static risk audit of the exact base tree, then a **compiled synthetic probe** of
the real `FileModel` class: Qt 6.12.0 / g++ 16.2 on Windows (UCRT64), a bounded
alternating navigation workload (2000 accepted moves) over two temporary
directories under a synthetic home. The probe drains `goBack()` with a hard cap
to count retained history; it measures the allocation count (depth), not a
wall-clock speedup. No Mint desktop, compositor, GUI render, real user session,
PSS/RSS sample, GPU or disk-I/O measurement was run here (`NOT_RUN`). Screen
reader behavior is `NOT_RUN`: the change does not add, remove or reword any
announced string, accessible name or QML role. Approved visuals, icons,
wallpaper, QML and assets are untouched.

## 2. Baseline pattern table

| Candidate at base | Ownership / lifetime | Finding |
| --- | --- | --- |
| `FileModel::m_backStack` (`prototype/classic/FileModel.cpp:81`, `:105`) | host-owned navigation-history cache, one per Files window | **Confirmed unbounded growth** — appended on every `navigate()`/`goUp()`, only shrunk by `goBack()` |
| `FileModel::m_all` / `m_visible` (`:150-166`) | per-directory entries | Bounded by `kMaxEntries = 500`, cleared on every `reload()` |
| `LauncherCatalogModel::m_rows` | launcher catalog snapshot | Bounded by `MaxRows = 1024`; three validated writers replace rather than append |
| `LauncherModel` / preview dataclasses | stateless pure records | No retained state |

Static scanner totals at base: 477 `.py`, 9 `.h`, 1 `.c` scanned; 46
`py_subprocess`, 12 `py_whole_read`, 2 `c_malloc`, 2 `c_unref`. It flags
acquisition patterns, not this growth path; the compiled probe is the evidence.

## 3. Confirmed issue and fix

Before: `back_depth=2000` after 2000 navigations — one retained path per move,
linear unbounded growth (`probe_base.log`).

After: `back_depth=32` after the same 2000 moves (`probe_fixed.log`).

One minimal change:

- `prototype/classic/FileModel.h:87,93` — declare `kMaxBackStack = 32` and one
  private `pushBackStack()` writer.
- `prototype/classic/FileModel.cpp:68-76` — the only append site; it explicitly
  invalidates the oldest entry (`removeFirst()`) until the cap holds, keeping
  the newest paths so `goBack()` retains its recency contract.
- `prototype/classic/FileModel.cpp:92,116` — `navigate()` and `goUp()` route
  through that guarded writer; rejected navigation still does not push.

No visual, QML, asset, protected or contract-doc file was changed.

## 4. Verification actually run

- RED: `tests/test_pe062_file_preview_back_stack_bound.py` — 3 failures on a
  pristine detached worktree at the exact base SHA.
- GREEN: same test — 3/3 OK on the fixed tree.
- Compiled probe at both trees, 2000 steps: 2000 → 32 retained entries.
- `python -m py_compile` on the new test; full-suite normalized FAIL/ERROR set
  comparison recorded in `suite_compare.json` (evidence dir).
- Resource impact: **SYNTHETIC** compiled-model allocation count — 2000 retained
  path strings reduced to at most 32 for an arbitrarily long browsing session;
  steady-state history memory becomes O(32) instead of O(n). Transient cost is
  one `removeFirst()` per excess push, bounded and constant per navigation.
  Real desktop PSS/CPU/GPU/wakeups, Mint acceptance and screen-reader behavior:
  **NOT_RUN**. Stability, security, accessibility and approved visuals are not
  traded away: all validation, bounds, signals and QML-facing roles are
  unchanged, and the newest-history behavior is preserved.

## 5. Ranked next steps that require runtime measurement

1. On real Mint, sample PSS across a long Files browsing session and confirm the
   history term is flat; owner-run, `NOT_RUN` here.
2. Confirm dock/launcher idle CPU and GPU are unchanged; `NOT_RUN`.
3. Keep the back-stack cap in the compiled self-test if a Qt build gate is
   provisioned; source-contract lock is the CI-scoped substitute here.
