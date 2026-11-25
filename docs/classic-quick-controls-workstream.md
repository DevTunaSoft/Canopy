# Classic quick controls — fail-closed workstream

**Scope:** new files only. This workstream adds a pure state model, a QML
overlay, regression tests and this note. It does **not** edit `main.cpp`,
`CMakeLists.txt`, `Main.qml`, `Theme.qml`, `ShellMenuBar.qml`, assets or any
owned file, and it does not merge into `main`. Base: `a3327fb` (integration
tip reported to this agent: `9cf39eb`, both ancestors of this branch).

## What the user actually gets

- Four labelled quick-control domains — Network, Sound, Power, Session — with
  status text taken **only** from a trusted host observation. With no
  observation the status is `Unknown — no host status`; it is never guessed.
- A visible, stable disclosure under every domain. Unavailable direct controls
  say why (`no host control interface`, `host control bridge disabled`, or
  `privileged host changes are not performed`). Buttons are disabled in that
  state, so no visible control pretends to work.
- One genuinely functional action today: **Open Settings**, which goes through
  the existing host-owned `canopySystemLauncher` bridge. It is enabled only
  when the host says the bridge is enabled and `canLaunch("Settings")` is true;
  a failed `launch()` reports failure rather than success.
- An optional trusted adapter contract: `controller.view(domain)` supplies a
  view (`status`, `status_label`, `source`, `observed`, `control`, `settings`);
  `actionBridge.request(domain, action)` may accept direct control intents.
  Neither adapter exists in the preview by default, hence fail closed.
- Escape closes the overlay; every button has an `Accessible.name` and the
  disabled control button has an `Accessible.description` with the disclosure.

## Fail-closed model

`canopy_features/system/quick_controls_state.py` is pure, bounded and offline:

- No socket, subprocess, service, thread, compositor call or privileged host
  change. No polling, no timers, no caches that grow from untrusted input.
- Observations must be one of a fixed token set per domain, with a bounded
  source; wrong types, unknown tokens, oversized/non-ASCII sources and
  duplicate domains are rejected. Session observations reuse the existing
  `canopy_features.reliability.lock_session_events.SessionState`; the
  `session.state.changed` name is checked against the existing
  `canopy_core.host_events` topic contract. No second event bus is created.
- `suspend` and `lock` are denied even when a caller supplies a grant and
  interface flags: this component has no authority to change the host session.
- Direct `toggle_wifi`/`toggle_mute` need both an explicit domain grant and a
  matching host bridge flag; missing either yields a stable denial reason.
- Only enumerated status tokens and fixed disclosure strings reach the UI.
  Caller-supplied text is never interpolated into a label.
- `snapshot()` is a `MappingProxyType`; `observe()` returns a new state.

## Registration dependency (owner-owned files, deliberately not changed)

The overlay is **not reachable from the shipped preview yet**. Integration
requires the owning agent to:

1. Add `QuickControlsOverlay.qml` to `QML_FILES` in
   `prototype/classic/CMakeLists.txt`.
2. Instantiate it in `Main.qml`, wire an opener (button/shortcut) to
   `openControls()`, and pass a trusted host adapter as `controller` and, only
   if one is reviewed and exists, `actionBridge`.
3. Keep the approved top bar/dock geometry, theme tokens and wallpaper
   unchanged; the overlay uses existing palette values and no new assets.

No such edit was made here. Until it is, the overlay is compiled-testable but
not user-reachable in the product binary. This is recorded as BLOCKED, not as
an integration claim.

## Evidence (exact commands and outputs)

Environment: Windows 11, Python 3.14.9, Qt 6.12.0 (MSYS2 UCRT64), GCC 16.2.0,
CMake 4.5.1. Commands run at the branch root unless noted.

| Check | Command | Result |
|---|---|---|
| New unit/contract suite | `python -m unittest discover -s tests -p 'test_classic_quick_controls_state.py'` | **PASS** — `Ran 23 tests`, `OK`, 0.044s |
| Full offline Python suite | `python -m unittest discover -s tests -p 'test_*.py'` | **PASS** — `Ran 3237 tests`, `OK (skipped=43)`, 77.416s |
| QML syntax | `qmllint.exe prototype/classic/QuickControlsOverlay.qml` | **PASS** exit 0; 27 non-fatal `unqualified` warnings (host context properties and nested delegates) |
| Strict QML syntax | `qmllint.exe --unqualified disable prototype/classic/QuickControlsOverlay.qml` | **PASS** exit 0, no output |
| Compiled QML | scratch copy of `prototype/classic`, scratch-only `CMakeLists.txt` adds `QuickControlsOverlay.qml` to `QML_FILES`; `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --parallel 4` | **PASS** — 45 build steps; generated `...QuickControlsOverlay_qml.cpp` and compiled its `.obj` |
| QML runtime harness | scratch `tst_quickcontrols.qml`; `qmltestrunner.exe -input tst_quickcontrols.qml -o result.txt,txt` with `QT_QPA_PLATFORM=offscreen` | **PASS** — `4 passed, 0 failed, 0 skipped`, 16ms; checks four disabled rows/buttons, disclosure strings, and that a supplied controller view is used |

Scratch harness path: `C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy-qc-compile-a3327fb`
(temporary; may be pruned). It is not part of the repository. The source-level
test file is not a substitute for the compiled harness above.

Source hashes (SHA-256, at this workstream's implementation commit
`64b41aecd504a832d0a55995d03df89746516e40`; the PR head SHA is recorded in the
draft PR body):

- `prototype/classic/QuickControlsOverlay.qml` — `292be15cbc84412dc3bf5456bd7a1b0079a685f40d2a0bf8619ac33b78b24a2d`
- `canopy_features/system/quick_controls_state.py` — `8e49bb5439ac416e57ec7c46747a7d828bb533729ae5c836586b4d0437e0ffd1`
- `tests/test_classic_quick_controls_state.py` — `a5e8033466d1a9d2603310efd14a60ec1fd6e5f87a64120104b2b93bf4910962`
- scratch `tst_quickcontrols.qml` — `854b762b295f5b29f138ec972025af2b0ad8705531505d3e66ce55fc2b5f87d5`

## Honest limits

- **BLOCKED:** no host audio/network/power control bridge or session action
  interface exists in the preview. All such controls stay visibly unavailable;
  no fake toggles, no new service/daemon, no privileged host change.
- **BLOCKED:** product integration needs owner edits to `CMakeLists.txt` and
  `Main.qml`; not performed here.
- **NOT RUN:** real Linux Mint NetworkManager/PulseAudio/UPower/logind queries;
  real Settings launch inside Mint; live compositor/window-manager session
  actions; 1920x1080/1200x750/760x500 screenshots of this overlay; owner visual
  acceptance; end-to-end keyboard/screen-reader session test; CI job for this
  branch if not triggered.
- Source-level Python QML string tests are contract checks only. The Qt 6.12
  qmllint/compile/qmltestrunner results are real but were produced in a scratch
  build, not in the registered product binary.

No performance, compatibility, Mint, release or visual-approval claim is made.
