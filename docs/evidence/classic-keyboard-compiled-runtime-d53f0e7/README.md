# Classic keyboard/accessibility gate — real compiled Qt offscreen execution

This note records the first execution of `tools/qa/classic_keyboard_accessibility_gate.py`
against a **real compiled Classic Qt binary** in offscreen mode. PR #599's gate previously
reported `compiled_qt_offscreen.status=NOT_RUN` because no runtime driver was supplied.
The gate now has a bounded built-in harness that launches the pinned executable with its
own `--self-test-*` hooks, requires every expected marker, and maps the verified markers
onto the eleven pinned keyboard steps.

## Scope and labels

- `CI-scoped local offscreen`: real compiled Qt on this Windows host with
  `QT_QPA_PLATFORM=offscreen`; **not** Linux Mint acceptance, not a compositor/session test.
- `SYNTHETIC`: unit-test harness paths (mocked subprocess, fake binary) used for negative
  controls. They prove the adapter fails closed; they are not runtime evidence.
- `NOT_RUN`: screen-reader output, real Mint keyboard dispatch, sustained idle PSS/CPU,
  owner visual approval. The gate rejects any report claiming otherwise.
- The compiled markers prove launcher open/search/close, the wired Files keyboard
  bindings, dock activation intent without false focus, and successful offscreen captures.
  Focus object names, accessible names and focus-border widths are checked against the
  exact frozen source files read at run time; they are source facts, **not** observed
  key events or screen-reader output.

## Exact environment and pins

- Host: Windows 11, MSYS_NT-10.0-26300 x86_64; Python 3.14.10.
- Toolchain: MSYS2 UCRT64, CMake 4.5.1, Ninja 1.13.2, g++ 16.2.0, Qt 6.12.0.
- Build: `cmake -S prototype/classic -B <scratch-build> -G Ninja -DCMAKE_BUILD_TYPE=Release`
  with `C:/msys64/ucrt64/bin` on `PATH`; then `cmake --build <scratch-build> --parallel 2`.
  The build used the disabled GIO fallback (`gio-unix-2.0` header absent), recorded as a
  build condition; no QML, C++ or asset file was edited.
- Task-pinned integration tip: `d53f0e731da97b86883c16dc9ac23b180a19eb54` (PR #599 merge).
- Live integration tip at PR creation: `4e504dbaf45b0c974de1fd28fc5de9e65f69a0cb`;
  its delta added the notification-centre QML/C++ and CI/docs files, none of them owned
  here. This branch was rebased onto that tip and the compiled binary rebuilt from that
  source; the gate run used source SHA `f800e576816cb2395cf2c66c4d3be3353d305a49` (the code commit before evidence finalization). No code changed afterwards; the final PR head is recorded in the PR body only.
- Compiled binary: `canopy-classic-spike.exe`, SHA-256 `bf5f5cbab72ae90b953f6dddec3b2263a171d5991abebf84f55dd9f3331f0bc1`.
- Runtime env: `QT_QPA_PLATFORM=offscreen`, `QT_FORCE_STDERR_LOGGING=1`,
  `QT_QPA_PLATFORM_PLUGIN_PATH=C:/msys64/ucrt64/share/qt6/plugins/platforms`, `DISPLAY` removed.
- Size `1200x750`, per-invocation timeout `40 s`, two bounded
  invocations, `shell=False`, stdout/stderr capped at 128 KiB per invocation.

## Exact command (run from the worktree root; source SHA `f800e576816cb2395cf2c66c4d3be3353d305a49`)

```
export QT_QPA_PLATFORM_PLUGIN_PATH=C:/msys64/ucrt64/share/qt6/plugins/platforms
python -m tools.qa.classic_keyboard_accessibility_gate \
  --source-root <worktree> \
  --expected-source-sha f800e576816cb2395cf2c66c4d3be3353d305a49 \
  --expected-binary-sha256 bf5f5cbab72ae90b953f6dddec3b2263a171d5991abebf84f55dd9f3331f0bc1 \
  --compiled-binary <scratch-build>/canopy-classic-spike.exe \
  --approved-art-dir <worktree>/prototype/classic/assets/approved \
  --self-test-size 1200x750 --timeout 40 \
  --artifact-dir <this-directory> \
  --json-out <this-directory>/gate-outcome.json
```

Observed stdout: `VERDICT PASS`, exit code `0`.

## Verdict from `gate-outcome.json`

- `verdict`: `PASS`
- `source_contract`: `PASS`
- `compiled_qt_offscreen.status`: `PASS`
- `execution`: `compiled-binary-self-test`, `invocations`: `2`,
  `steps_verified`: `11`
- `screen_reader`, `mint_acceptance`, `visual_owner_approval`: `NOT_RUN`
- Scope recorded by the gate: `compiled Qt offscreen self-test markers mapped to pinned keyboard steps; focus/name/width details from frozen source contracts`

### Step-to-marker mapping observed in this run

| pinned step | compiled marker required |
|---|---|
| `dock_arrow_next` | `SELF_TEST_PASS: dock icons horizontally/vertically centred` |
| `dock_return_activate` | `SELF_TEST_PASS: dock activation intent reaches host gate without false focus` |
| `dock_tab_focus` | `SELF_TEST_PASS: dock icons horizontally/vertically centred` |
| `files_escape` | `SELF_TEST_PASS: Files keyboard close and reopen bindings` |
| `files_tab_search` | `SELF_TEST_PASS: Files close control and dock reopen` |
| `grid_arrow_first` | `SELF_TEST_PASS: actual Qt launcher opens, searches and closes` |
| `grid_enter_files` | `SELF_TEST_PASS: Files dock hide/restore and activity indicator` |
| `overlay_escape` | `SELF_TEST_PASS: actual Qt launcher opens, searches and closes` |
| `overlay_open` | `SELF_TEST_PASS: actual Qt launcher opens, searches and closes` |
| `overlay_reopen` | `SELF_TEST_PASS: actual Qt launcher opens, searches and closes` |
| `overlay_tab_grid` | `SELF_TEST_PASS: actual launcher button image geometry centered` |

`gate-outcome.json` also carries the exact observed marker lines from both invocations
(`compiled_self_test.observed_marker_lines`), so no verdict string was copied by hand.

Offscreen screenshots produced by the compiled binary in this run (SHA-256 recorded in
`gate-outcome.json` and matched against the on-disk PNGs):
- `canopy-keyboard-desktop.png`: `fd988a1b1f4bc30d1e55228731b60bf68848278c4564b152f17055d3c877ce63`
- `canopy-keyboard-launcher.png`: `e4f653a088f3d52f378fe3a52113134ae9876ca85e8eec8b5665a5c09d76a251`

Screenshots are functional-render evidence only; the live top-bar clock makes their bytes
time-dependent, so they are not byte-stable across separate runs. No visual approval is claimed.

## Negative controls

The deterministic tests in `tests/test_c100_classic_keyboard_accessibility.py` prove that
the adapter fails closed on: a missing required marker, a duplicated marker, a drifted step
map, a failing source contract, a `SELF_TEST_FAIL` marker, a nonzero process exit, an
out-of-range/invalid size, and a compiled-mode CLI invocation without a binary SHA-256 pin.
All pre-existing driver/report negative controls remain active. Targeted module run at the
source SHA above: 18 tests, `OK`.

## Full-suite comparison

- Pristine worktree at live base `4e504db`: 3394 tests,
  `OK (skipped=45)`, 282.859 s. Log `suite-newbase.txt`,
  SHA-256 `05698d488a0a8ee9126dcbbd4cf9e94afc28f3994496e40392210226ca0b9251`.
- Same worktree with this change (source SHA `f800e576816cb2395cf2c66c4d3be3353d305a49`): 3399 tests,
  `OK (skipped=45)`, 283.482 s. Log `suite-head.txt`,
  SHA-256 `8517a2e1b5e491a95cf09935c97292c271f5c40b98ed98950fbe4a46cbd7f183`.
- Delta: +5 tests, zero new failures/errors;
  FAIL/ERROR name sets are both empty.
- Earlier comparison at the task-pinned tip `d53f0e7`: 3361 tests base versus
  3366 tests candidate, both `OK (skipped=45)`; logs `suite-base.txt`
  (SHA-256 `e174b13cb24acc76c1d33716f70b0803f964ca44cc32f0a262b45c53b942c944`) and `suite-candidate.txt` (SHA-256 `a1492798348cd7d813e11bbd1b4325f7f322181775044ced4aefcc45e87366c9`).

## Artifact SHA-256 index

- `gate-outcome.json`: `a74c72a9b33fbdd0658d3fcef32978f70184306c44b0a403c156d0ef5c212aef`
- `gate-stdout.txt`: `06e78cf06db1b87d7dcd86029e9c125c6f5c304857e25f54e50cd0f8b0872245`
- `self-test-markers.txt`: `fd53196918cba337426f58c23c07ef409a90b2522d2a7adabbb195fb993281b9`
- `raw-launcher-stderr.txt`: `d827aa67f2078dbbfe5005655233be4988a749e03e64efbad1a634ed7dff9d97`
- `raw-activation-stderr.txt`: `f29b1a583d1e1131eeb80c90c50e6a5d7d65e87451e0c0488a2880793ac75ab6`
- `canopy-keyboard-desktop.png`: `fd988a1b1f4bc30d1e55228731b60bf68848278c4564b152f17055d3c877ce63`
- `canopy-keyboard-launcher.png`: `e4f653a088f3d52f378fe3a52113134ae9876ca85e8eec8b5665a5c09d76a251`

## What this does not prove

No OS-level key dispatch, no screen reader, no Mint guest acceptance, no owner visual
approval, no sustained resource measurement. A green Python suite and this offscreen
run do not authorize any merge into the integration branch.
