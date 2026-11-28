# Deferred shell-menu compilation — scoped startup evidence (177c380)

**Verdict: PROVEN within scoped Windows/offscreen A/B evidence.** A bounded,
nonvisual change moves the six approved shell popups into a separate QML
document loaded by an inactive `Loader`. `engine.load()` improves in 43 of 52
alternating paired runs (median pair delta 8 ms; 8 ms with three >=100 ms host
outliers removed). On the final source/binary pair, 16/16 alternating pairs
favour the candidate and all 16 paired frames are byte-identical. Earlier
batches differ only at live-clock minute boundaries, which also change between
two baseline runs.

## Exact pins

- Integration base: `integration/canopy-classic-20261123` tip
  `58d245e8db266e92260825b18434fcf967d4c444` at final rebase; original A/B
  measurements were captured at `177c380b389db24b55e80d604ce5a086b15d79e8`.
  Suite logs were refreshed at the final rebased head.
- Production diff paths: `prototype/classic/ShellMenuBar.qml`,
  `prototype/classic/ShellMenuPopupSet.qml` (new),
  `prototype/classic/CMakeLists.txt`, the two Classic source-contract tests
  (they now read both menu documents), this evidence note and its artifacts.
  No C++, artwork, QML visual geometry, timer or dock file changed.
- Both binaries were built from the same base SHA with the **same scratch-only**
  `CANOPY_PROFILE` instrumentation in `main.cpp` (identical SHA-256
  `c3f1d20ca42af988eb25d194d484e130da2cbe459e768007dfb6156dcd708fe3`);
  instrumentation was reverted before the production commit and is not in this
  PR.
- Final binary SHA-256: baseline
  `dee53e14fa165ef923309f6925b8e9fdcb3787b6bfb578ea4ea3cf8ad475c2de`,
  candidate `98beda09c2ac1b18ac664a298fb1533e292fdfd0ea1a0ff3e89840a34f079a0a`.
  Batches 1–3 used an earlier candidate build
  (`023f3a706ac628743b135894f5ccb8d4201c53e0cde79a327b42ceea16573b3b`) with
  the same QML restructuring but a different internal id spelling; batch 4 is
  the exact PR source. Each batch JSON records both hashes and every run's
  frame hash.
- Toolchain: MSYS2 UCRT64 cmake 4.5.1 / ninja / g++ 16.2.0, Qt6 Quick +
  QuickControls2, `QT_QPA_PLATFORM=offscreen`, 1200x750 approved-art self-test.

## Method and its limits

Two warmup runs per binary, then 10 / 10 / 16 / 16 alternating pairs (odd pairs
base→candidate, even pairs candidate→base, 1–2 s gap). `engine.load()` time is
a `QElapsedTimer` mark taken immediately after the window-ready check, before
any profiling traversal. The frame proxy is the `grabWindow()` PNG captured
after the unchanged fixed 1 s self-test delay.

Host: Windows 11 Pro, i5-1135G7, software raster only. **SYNTHETIC /
WINDOWS-RUNTIME / offscreen** evidence: not a Linux Mint guest, not Xvfb, not
GPU/compositor, not owner visual approval, not release evidence. Wall-clock
numbers are scoped context; the deterministic allocation deltas below anchor
the claim.

## Measured result

| Batch | Pairs | Base median | Candidate median | Pairs favouring candidate |
|---|---|---|---|---|
| 1 (earlier candidate) | 10 | 224.0 ms | 204.0 ms | 8/10 |
| 2 (earlier candidate) | 10 | 207.5 ms | 205.5 ms | 9/10 |
| 3 (earlier candidate) | 16 | 214.5 ms | 202.5 ms | 12/16 |
| 4 (final PR source) | 16 | 191.0 ms | 184.0 ms | 14/16 |

Combined: 43/52 pairs favour the candidate; median pair delta 8 ms, trimmed
median 8 ms. Three host outliers (one candidate +635 ms, two baseline +324 /
+453 ms) are retained in the raw artifacts and excluded only from the trimmed
statistic. Batch medians vary on this noisy host; the direction does not.

Deterministic work removed at load (every run): QQuickItems 322 → 162,
QObjects 598 → 320, `Menu` 7 → 1, `MenuItem` 18 → 3, `QQmlComponent` 31 → 13.
Unlike the earlier inline-`Component` attempt, the popups are now a separate
QML document, so neither its component object nor its bindings are built in
the resting scene. All six menus retain their original titles, object names,
actions and `Accessible.name` strings verbatim; the two source-contract tests
still assert those strings across the two documents.

## Frame and contract checks

- Final batch: 16/16 paired frames byte-identical. Across all batches, 50/52
  pairs are exact; the two mismatches (batch 1 pair 6, batch 2 pair 9) occur
  exactly at a clock minute boundary and touch only 42 / 46 pixels in bbox
  `(1150,11)–(1156,19)`. Two **baseline** runs at the same boundary produce
  the same 42-pixel difference, so this is the live clock, not the candidate.
- Every paired run exits 0 and captures a frame.
- Runtime menu contract (`CANOPY_TEST_MENU=1`, scratch instrumentation) is
  identical for both binaries at the final SHA:
  `menuCheck menusFound=1 got=1 opened=1 itemFound=1`.
- Idle-wakeup contract preserved: scene histogram reports exactly one
  `QQmlTimer` in both binaries; the change adds no timer, polling loop, worker
  or network/process activity.
- Full suites at both worktrees on the final rebased tree: 3222 tests, `OK (skipped=43)`
  with no new FAIL/ERROR; logs in the artifacts below.
- Screen-reader behaviour: **NOT_RUN** (no Mint guest, no accessibility bus).
  Accessible names are unchanged text, and the deferred objects are created
  on the same menu-open path before any menu becomes visible.

## Resource impact / exclusions

- Measured: `engine.load()` wall time (scoped offscreen, SYNTHETIC host
  context), startup item/object counts, QML component counts, frame hashes,
  self-test exit codes, menu-open contract, timer count, full test suite.
- NOT_RUN: Linux Mint PSS/CPU, 5-minute idle sampling, ETW context switches,
  GPU/compositor path, screen-reader announcement checks, owner visual
  approval, CI-on-guest acceptance.
- No stability, security, accessibility or approved-visual trade-off: only
  invisible popup construction is deferred; the proxy objects keep the
  existing `menuFor()/open()/visible` interface and all approved action text.

## Artifacts (SHA-256)

- `docs/evidence/perf-deferred-menus-177c380/batch1.json` —
  `71b9c9d7ece77eebfea66ed47705d2108bce07a6ffeaf4e2afa10397e8cbbd45`
- `docs/evidence/perf-deferred-menus-177c380/batch2.json` —
  `ab7a912e4e9fdb941c1522da595ddc34d1dca8a06848c69adf10658c17760326`
- `docs/evidence/perf-deferred-menus-177c380/batch3.json` —
  `a0088644514e1e0b6aaf017e0036e014c7c4fb67af7cff584814edd7a3fa2ff8`
- `docs/evidence/perf-deferred-menus-177c380/batch4.json` —
  `bfcf0b4c4d60090e63d9ea9f5f69f82db2e694a33273dfa855973269720e223c`
- `docs/evidence/perf-deferred-menus-177c380/combined.json` —
  `12708749cc574c37fe4a4e2333fc5f9ed6448c7f850d6fa03f4ec6b4e36ac856`
- `docs/evidence/perf-deferred-menus-177c380/suite-base.txt` —
  `8a9104fd6d6f9a2203328d2aa2eab833fbe5b4aa01b1a95a0b5f1ceeefb68b43`
- `docs/evidence/perf-deferred-menus-177c380/suite-candidate.txt` —
  `793c715f0ba051eee97186299987d7754d30795cc55e135c6fb263893d9fb822`
