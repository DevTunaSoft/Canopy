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
- Live integration tip at PR creation: `684f706af7a5526e6f64786da9e13ff057532bc4`;
  its delta touches only CI/docs/test files, none of them owned here or under
  `prototype/classic`. This branch was rebased onto that tip; the gate run used source SHA
  `9d2370f2da62a65758aa068594b9409719b451fa` (the code commit before evidence finalization).
  No code changed afterwards; the final PR head is recorded in the PR body only.
- Compiled binary: `canopy-classic-spike.exe`, SHA-256 `40c9724fef73815b9578391d2842792e718c8bd3c581470902ba6fb1b2de714b`.
- Runtime env: `QT_QPA_PLATFORM=offscreen`, `QT_FORCE_STDERR_LOGGING=1`,
  `QT_QPA_PLATFORM_PLUGIN_PATH=C:/msys64/ucrt64/share/qt6/plugins/platforms`, `DISPLAY` removed.
- Size `1200x750`, per-invocation timeout `40 s`, two bounded
  invocations, `shell=False`, stdout/stderr capped at 128 KiB per invocation.

## Exact command (run from the worktree root; source SHA `9d2370f2da62a65758aa068594b9409719b451fa`)

```
export QT_QPA_PLATFORM_PLUGIN_PATH=C:/msys64/ucrt64/share/qt6/plugins/platforms
python -m tools.qa.classic_keyboard_accessibility_gate \
  --source-root <worktree> \
  --expected-source-sha 9d2370f2da62a65758aa068594b9409719b451fa \
  --expected-binary-sha256 40c9724fef73815b9578391d2842792e718c8bd3c581470902ba6fb1b2de714b \
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
- `canopy-keyboard-desktop.png`: `d0b4475b66f8bdfad6ae104329ef6973fc8eca913b56b4a53035a922ff915159`
- `canopy-keyboard-launcher.png`: `9e8bc700d7dbe648c58d6dd89227b2af06f8c2216da1cad9b3be3ca4074a7639`

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

- Pristine worktree at live base `684f706`: 3380 tests,
  `OK (skipped=45)`, 359.199 s. Log `suite-livebase.txt`,
  SHA-256 `f91fc13d8808829646c1096f8d54446cab589b1991668edf7b2a9f8fd385e029`.
- Same worktree with this change (source SHA `9d2370f2da62a65758aa068594b9409719b451fa`): 3385 tests,
  `OK (skipped=45)`, 362.084 s. Log `suite-final.txt`,
  SHA-256 `dd8827fae89b817bc6c730052a82d68304b7c370764b6564e97cce1993bbca94`.
- Delta: +5 tests, zero new failures/errors;
  FAIL/ERROR name sets are both empty.
- Earlier comparison at the task-pinned tip `d53f0e7`: 3361 tests base versus
  3366 tests candidate, both `OK (skipped=45)`; logs `suite-base.txt`
  (SHA-256 `e174b13cb24acc76c1d33716f70b0803f964ca44cc32f0a262b45c53b942c944`) and `suite-candidate.txt` (SHA-256 `a1492798348cd7d813e11bbd1b4325f7f322181775044ced4aefcc45e87366c9`).

## Artifact SHA-256 index

- `gate-outcome.json`: `c2c546d9da8f21e8686e8153cf6eefe76cf324a7d052feb55a7777cf164a2b73`
- `gate-stdout.txt`: `06e78cf06db1b87d7dcd86029e9c125c6f5c304857e25f54e50cd0f8b0872245`
- `self-test-markers.txt`: `4ed96774d308e288aeda31f0d49a283e1092d0c01cacf7f47b865207cf12cdfb`
- `raw-launcher-stderr.txt`: `5c9ff7ca535859c73e9d6724c2bef3c1e6c3f86cc305979c9acddcc7834414da`
- `raw-activation-stderr.txt`: `5997fd188e38fbc3d49736bb8f26ca2a3f844ff230da03e5ea6d1c3c21032254`
- `canopy-keyboard-desktop.png`: `d0b4475b66f8bdfad6ae104329ef6973fc8eca913b56b4a53035a922ff915159`
- `canopy-keyboard-launcher.png`: `9e8bc700d7dbe648c58d6dd89227b2af06f8c2216da1cad9b3be3ca4074a7639`

## What this does not prove

No OS-level key dispatch, no screen reader, no Mint guest acceptance, no owner visual
approval, no sustained resource measurement. A green Python suite and this offscreen
run do not authorize any merge into the integration branch.
