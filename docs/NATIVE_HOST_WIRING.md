# Native host wiring (M2/M3 display response)

Status: **DRAFT for independent review**. No merge, no self-approval, no
protected-branch change by this worker.

Base: `ec910d7a7275296ecbc8b5e5c459d356205165d1`
(`integration/canopy-plasma6-20261127` live tip at branch point).
Owner directive: `Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md`,
SHA-256 prefix `1fba4b1e`, M2/M3 sections and evidence-label rules.

## What changed

1. `prototype/classic/main.cpp` adds one `NativeDisplayHostBridge` QObject:
   - connects `QGuiApplication::screenAdded`, `screenRemoved`,
     `primaryScreenChanged` and each `QScreen::geometryChanged`,
     `logicalDotsPerInchChanged`, `physicalDotsPerInchChanged`;
   - adapts each signal through the same decision table as
     `canopy_features/dock/display_change_response.py` and
     `canopy_features/dock/display_scaling_contract.py`, including the frozen
     dock-bounds check, nearest-supported-resolution clamp, half-up logical
     pixels, 150% trap, bounded 64-plan history and duplicate suppression;
   - applies **only** `relayout` plans to the existing `QQuickWindow`
     geometry; never creates a window, compositor, service or binding;
   - is inert unless `--native-display-host` is passed, so approved visuals,
     dock geometry, screenshots and every existing self-test are unchanged.
2. `canopy_features/quick_controls/native_display_contract.py` is the Python
   side of the shared wire contract: a `ScreenObservation` producer, one-shot
   `NativeDisplayProducer` entry points, bounded plan encode/decode and the
   canonical vector source. It imports no Qt, opens no file and starts no
   service; it does not add a host-event topic or a second bus.
3. `scratch/native_host_wiring/` contains the generated vectors, compiled
   self-test log, parity gate, contract tests, build/config logs, the exact
   Plasma blocker capture and this PR's evidence index.

`ShellMenuBar.qml` and `QuickControlsOverlay.qml` are in the assigned file set
but are deliberately **not edited**: the QML rendered halves are byte-pinned
by `tests/test_nd041_native_settings_controls_wiring.py` and
`tests/test_classic_status_a11y.py`, and no visual change is needed for a host
entry point. `canopy_features/dock/display_change_response.py` is likewise
unchanged; open PR #746 owns that file and this wiring consumes the contract at
its current base without duplicating that PR.

## Upstream service reuse and single-owner boundaries

- Observation is supplied by the running Plasma platform integration through
  Qt's screen API. There is no X11/Wayland probing loop, no KWin replacement,
  no additional compositor and no duplicated shell services.
- One bridge instance per process, one signal connection per screen, one
  bounded topology snapshot and one bounded plan history. The only periodic
  activity is the existing Qt event loop; there is no `QTimer`, thread,
  socket, process spawn or D-Bus service in the bridge.
- `--native-display-json` is a one-shot adapter command for a trusted
  read-only guest probe; it prints one bounded snapshot and exits. It is not a
  daemon and is not called automatically.
- The compiled host does not spawn Python. The Python producer and compiled
  bridge are two implementations of the same documented wire contract; the
  offline parity gate checks them against one generated vector set.

## Verification actually run

| Check | Command | Result |
| --- | --- | --- |
| Compile | `cmake -S prototype/classic -B <scratch build> -G Ninja && ninja -C <scratch build>` | MSYS2 UCRT64 Qt 6.12, rc=0; `cmake_configure.log`, `ninja_build.log` |
| Compiled self-test | `<build>/canopy-classic-spike.exe --self-test-native-display-host` (`QT_QPA_PLATFORM=offscreen`) | `CANOPY_NATIVE_DISPLAY_SELF_TEST_PASS: vectors= 13`, rc=0 (`compiled_self_test.log`) |
| Python/compiled parity | `python scratch/native_host_wiring/parity_check.py` | `verdict=PASS`, 13/13 vectors, zero wiring-marker or visual-path findings (`parity_report.json`) |
| Wire-contract tests | `python -m unittest discover -s scratch/native_host_wiring/tests -p 'test_*.py'` | `Ran 11 tests ... OK`, rc=0 (`contract_tests.log`) |
| Existing targeted suites | `python -m unittest tests.test_pe025_display_change_response tests.test_pe075_display_scaling_contracts tests.test_c100_reliability_screen_topology_change tests.test_quick_controls_host_state tests.test_quick_controls_host_injection tests.test_classic_status_a11y tests.test_nd041_native_settings_controls_wiring` | `Ran 109 tests ... OK`, rc=0 (`targeted_tests.log`) |

| Full suite | `PYTHONPATH=<worktree> python -m unittest discover -s tests` | `Ran 4671 tests in 680.816s`, `OK (skipped=49)`, rc=0 (`full_tests.log`, `full_tests.rc`) |

All of the above are **SYNTHETIC** source/offline checks on the Windows 11
host. The compiled binary is a Windows PE (`MZ`, `.exe`), not a Linux binary.

## Native runtime: `NOT_RUN`

Exact blocker and captured commands are in
`scratch/native_host_wiring/plasma_runtime_blocker.md`. No real Plasma screen
signal, monitor add/remove, DPI change, compositor behavior, screenshot or
screen-reader announcement was observed or claimed. The adapter flag exists,
but the guest has no supplied authorized login, its guest-execution service is
not ready, and no Linux build at this exact head was run in the guest.

## Resource / evidence note

- `SYNTHETIC`: compile result, 13 compiled vectors, 11 wire-contract tests,
  109 targeted Python tests, the 4671-test full suite and static source checks.
- `NOT_RUN`: real Plasma session, real monitor
  and scale changes, compiled Qt frames, screenshots, 24-hour endurance,
  PSS/CPU/GPU/wakeup measurement and screen-reader behavior.
- Deliberate bounds: one QObject, one bounded `QVector` (64), no cache,
  timer, thread, daemon, animation, artwork or visual edit. No stability,
  security, accessibility or approved-visual tradeoff is made.
- Screen-reader behavior: `NOT_RUN`. No announcement is added by this change.
