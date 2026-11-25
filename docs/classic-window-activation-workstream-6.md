# Workstream 6 — Classic window-activation / running-indicator adapter

DRAFT, non-visual, no merge authorization. Classic Qt final integration stays
draft until real Mint acceptance and owner visual approval.

## What this adds

A new, self-contained C++/QML host adapter for the Classic dock's missing
running-app / activation workflow:

- `prototype/classic/WindowActivationState.{h,cpp}` — event-driven, fail-closed
  state. A trusted host applies one bounded snapshot; the class derives
  running indicators, active-window state and a dock-click **intent**
  (`FOCUS` / `LAUNCH` / `REJECT` / `IGNORE`). It never observes a desktop,
  launches a process, focuses a window, polls, calls the network or draws.
- `prototype/classic/WindowActivationIndicators.qml` — non-visual `QtObject`
  adapter exposing `indicatorsAvailable`, `runningApps`, `activeApps`,
  `running()`, `active()` and `activation()`. No Item, image, geometry, color,
  timer, animation or shortcut is added, so no approved visual identity is
  changed.
- `prototype/classic/window_activation/` — standalone compiled self-test,
  14 cross-language contract vectors and a QML behavioural check.
- `tests/test_classic_window_activation_contract.py` — 8 deterministic tests
  checking that C++ allowlists/bounds/statuses match the Python contracts and
  that QML stays non-visual and fail-closed.

Contract sources (unchanged): `canopy_features/dock/dock_running_indicators.py`
(bounded owner fold, duplicate-PID rejection), `canopy_features/dock/click_intents.py`
(approved dock names, FOCUS/LAUNCH/REJECT/IGNORE), `canopy_features/windows/focus_intents.py`
(deny-by-default cross-app authorization and decision statuses), and
`canopy_features/windows/window_state_capabilities.py` (known backend ids).

Fail-closed rules: unknown backend, wrong schema or sequence type, unapproved
app id, duplicate PID, PID bound breach, missing required keys and malformed
focus/grants all clear every indicator and set status `UNAVAILABLE`. Stale
sequences are ignored. A running app still requires explicit same-app or
recorded-grant authorization before `FOCUS`; a disabled launcher yields
`IGNORE` and an uninstalled target yields `REJECT`.

## Wiring dependency (deliberately not applied)

The owning workstreams keep `prototype/classic/CMakeLists.txt`, `main.cpp`,
`DockTile.qml`, `RoundedDockIconProvider.cpp`, workflow, assets and
`docs/GUI_ENGINEERING_DOSSIER.md`. This workstream does **not** edit them.
To make the adapter live in the shipped shell, the owner must:

1. instantiate `WindowActivationState` in `main.cpp` and feed it host-owned
   snapshots (no new observation code belongs in the adapter);
2. add `WindowActivationIndicators.qml` to the owned `CMakeLists.txt` QML list
   and expose the state object to QML;
3. bind the non-visual adapter into `DockTile.qml` indicator properties.

PR #564 (merged) already owns `CMakeLists.txt` registration for
`ShellMenuPopupSet.qml`; no line in that file was changed here. The standalone
`window_activation/CMakeLists.txt` is a new, separate target and is not
registered by the shell build.

## Evidence (exact SHAs)

- Directive tip `b31c995a650202b66c08064a7cc3b7b4f0609d2d`; live integration
  tip re-queried before branching: `8cf0dad58f33020d2eba0e38539db68de55c58af`
  (`b31c995` is its ancestor). Branch base is the live tip so the draft PR is
  not stacked on already-merged PRs #564/#567/#569/#570.
- Toolchain: `C:/msys64/ucrt64/bin/cmake.exe` (Ninja, GNU 16.2.0), Qt 6 from
  `C:/msys64/ucrt64/lib/cmake/Qt6`. Configure and build succeeded with no
  compile errors; executable SHA-256
  `0f01b3d22ce3ddce6d71d0243b84cfd11286d4ff2d61181a64d69bb66e275c25`.
- Compiled run (offscreen, real Qt/QML engine, exit 0): 14/14 vectors pass and
  `QML_PASS untrusted`, `QML_PASS ready`, `QML_PASS cleared`, final marker
  `WINDOW_ACTIVATION_SELF_TEST_PASS cases=14 qml=ok`. Log SHA-256
  `57da42d9095b948823eeaca2ba387f6f38bc3d22ac215a65ca3c309b48c457bd`.
- Full local suite on a private pristine worktree pinned at the same base:
  base `Ran 3228 tests`, `OK (skipped=43)`, log SHA-256
  `a52fe70a5d4a7964a576307268b2d0db00c92f1f71cfc2d7ddaf29805066e04e`;
  candidate `Ran 3236 tests`, `OK (skipped=43)`, log SHA-256
  `91bc268de0fe12a7f29f3c663d31f39a7e2455f76d18adf78121a3327356b801`.
  Delta is exactly the 8 new tests; no FAIL/ERROR name was introduced.
- Component source SHA-256: header `823053457861c4a47384610a17822c5c06cfa42e3ce32b1a1f0b369abd8ab13f`,
  implementation `f3ad4325cc072f7a750cbe0a07d7d38bf421a7db6d69d57b9a55274d5cbaf4e4`,
  QML adapter `f855e34c2817ad8bd1ed1c7112476c13ec57a5320b873c7ea1c1755e82526739`,
  self-test QML `18e2bb1f7195d3e0b64fbf2c42e20279088257e46790533ec1e55cf3417565d4`,
  vectors `ff95931fa4086cb5a96352ddd19f3999837502519ac99d60235787d2076a3c79`,
  Python test `19801a3b4d3da3703677f5b62b26fd2a2ce806d6757a299c543e1c0603fd771f`.

## Resource / evidence note

Measured: **SYNTHETIC** — Windows ucrt64 offscreen software-raster Qt engine,
short standalone self-test and deterministic source/vector checks; compiled
exit code and full-suite counts are real command results on this host.
NOT_RUN: Linux Mint guest, real compositor/window-manager activation, GPU or
compositor timing, 5-minute idle CPU/PSS, ETW context switches, screen-reader
announcements, CI-on-guest acceptance and owner visual approval.
The adapter adds no timer, poll, worker, cache or continuous rendering and
holds only bounded snapshots (64 apps, 8 PIDs/app, 256 grants); it does not
trade stability, security, accessibility or approved visuals for a minor gain.
Screen-reader behaviour is unchanged: the component exposes no visual or
announceable element until the owner wires it.
