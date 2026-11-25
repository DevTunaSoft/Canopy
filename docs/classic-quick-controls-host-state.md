# Classic quick controls — real host-state wiring (33d8d1b)

## Scope and ownership

Branch `feat/classic-quick-controls-host-state-33d8d1b` is based on the
integration tip `33d8d1bf6709abfd82f3b55829ad2cd75a3d43ad`. Only these owned
paths changed:

- `canopy_features/quick_controls/**` (new read-only adapter package)
- `prototype/classic/QuickControlsOverlay.qml`
- `tests/test_quick_controls_host_state.py`
- this note and `docs/evidence/classic-quick-controls-host-state-33d8d1b/`

No C++, CMake, `Main.qml`, asset, workflow or other source file was edited.
No merge is authorized; this is a draft PR against the integration branch.

## What was actually wired

The pre-existing fail-closed model
(`canopy_features/system/quick_controls_state.py`) is pure and does no I/O.
PR #582 produced it, PR #590 registered the overlay in the compiled shell, but
the shell passes no controller, so all four rows stay `Unknown — no host
status`. This change adds the trusted, read-only boundary that was missing and
lets the overlay render observations supplied through the existing controller
contract.

| Host fact | Existing contract reused | Quick-control view |
|---|---|---|
| network connected / disconnected | bounded `network_connected` boolean in a delivered `canopy_core.host_events.HostEvent` | Network status label |
| audio muted / unmuted | bounded `audio_muted` boolean in the same event contract | Sound status label |
| volume 0–100 | bounded `volume_percent` integer in the same contract | `Sound on · Volume N%` (fixed token + bounded integer) |
| display brightness 0–100 | bounded `brightness_percent` integer in the same contract | power row detail `Brightness N%` (no new row, no new asset) |
| battery charging / discharging | bounded `battery_charging` boolean | Power status label |
| session active / locked / suspended | existing `canopy_features.reliability.lock_session_events.SessionState` via `observation_from_session` | Session status label |
| Settings bridge | existing `canopySystemLaunchEnabled` + `SystemAppLauncher.canLaunch("Settings")` in QML | only genuinely available action |

`HostStateSnapshot.from_host_event` accepts only an already-delivered
`HostEvent` on an allowlisted `TOPICS` entry. It never emits, subscribes, opens
a socket, starts a service, spawns a process or creates a daemon. No new topic,
field name, domain, status token, disclosure or QML row was introduced. The
topic name `session.state.changed` is still checked against
`canopy_core.host_events` by the existing model.

Fail-closed rules:

- A missing fact stays `unknown` with `source: "none"` and the fixed
  `Unavailable — …` disclosure. `None` is never coerced to `False` or `0`.
- Wrong types, out-of-range percentages, non-ASCII/oversized sources and
  lookalike session objects raise `HostStateError` rather than being displayed.
- Direct toggles still require an explicit grant and matching bridge; neither
  exists, so those buttons stay disabled. `suspend` and `lock` remain denied
  even if a caller supplies a grant.
- The overlay validates every adapter view: `status_label` must be a string of
  at most 64 characters, detail kind must be `volume`/`brightness`/empty and
  detail value a bounded integer. Hostile or broken adapters fall back to the
  fail-closed view. No caller text is interpolated into a label.
- Approved visual identity is unchanged: same four rows, colors, geometry,
  buttons and assets. Real values only replace the status text inside the
  existing label, and only when a trusted adapter supplies them.

## Evidence (real commands and outputs)

Environment: Windows 11, Python 3.14.9, MSYS2 UCRT64 Qt 6.12.0, CMake 4.5.1,
Ninja 1.13.2, GCC 16.2.0, `QT_QPA_PLATFORM=offscreen`. The GIO dev package was
absent, so the compiled build used the existing disabled-native-launch fallback.

| Check | Command | Result |
|---|---|---|
| New adapter tests | `python -m unittest discover -s tests -p 'test_quick_controls_host_state.py'` | PASS, 24 tests |
| Prior quick-controls tests | `python -m unittest discover -s tests -p 'test_classic_quick_controls_state.py'` | PASS, 23 tests |
| Strict QML lint | `qmllint --unqualified disable prototype/classic/QuickControlsOverlay.qml` | PASS, exit 0, no warning |
| Compile Qt | `cmake -S <worktree>/prototype/classic -B <scratch> -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build <scratch> --parallel 4` | PASS, 52/52 steps, including `QuickControlsOverlay_qml.cpp.obj` |
| Compiled overlay fixture | `canopy-classic-spike.exe --approved-art-dir <art> --self-test-approved --self-test-quick-controls` | PASS — `QUICK_CONTROLS_FIXTURE_PASS: opener wired, four domains fail closed, approved visuals unchanged` |
| QML runtime harness (real adapter JSON injected) | `qmltestrunner -input tst_quickcontrols_host.qml` | PASS — 5 passed, 0 failed; renders `Connected`, `Sound on · Volume 42%`, `On battery · Brightness 68%`, `Locked`; fail-closed fallback and hostile-adapter rejection also pass |

The harness JSON is generated from `HostStateController` in the worktree, so
the runtime assertion covers Python contract → QML view → instantiated label,
not just source text. The scratch harness
(`C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy-qc-harness`) is not part
of the repository.

### Three screenshots (compiled binary, approved art, offscreen)

Each invocation used
`--approved-art-dir <art> --self-test-approved --self-test-size SIZE
--self-test-screenshot <png>` and exited 0 with
`SELF_TEST_PASS: nonuniform window screenshot captured`.

| Capture | SHA-256 |
|---|---|
| `classic-1920x1080.png` | `47fb376c92ed15be01c0763f44c26bf6f00f8c9d82a67cc0bc8b61ecef2e1833` |
| `classic-1200x750.png` | `4b17ad5f8382705182656e1e7f5cc29324c3a8703ab7911650aebe3f19659bb1` |
| `classic-760x500.png` | `c22d945ae543e4a1f6c45685369188c24cf5a802121e6073b26f93cc97fb5b96` |

Full capture logs and PNGs are in
`docs/evidence/classic-quick-controls-host-state-33d8d1b/`. The captures show
the approved resting desktop: the quick-controls overlay remains hidden in the
shipped binary, so approved visuals are provably unchanged. They are functional
render evidence only, not owner visual approval.

### Full suite comparison

FULL_SUITE_SECTION

### Source and artifact hashes

| Artifact | SHA-256 |
|---|---|
| `canopy_features/quick_controls/__init__.py` | `1d5e35d0b6d6a85970ae0e380a016a5ac82bb91605d3fd33bb8e69a3c433fb7c` |
| `canopy_features/quick_controls/host_state.py` | `29ff739fabbb5d69c1f14930199cfc13c9e31ee9a79ea5142f5556d8d2ad46d5` |
| `prototype/classic/QuickControlsOverlay.qml` | `b7550612d97cd029f28ec6c2ce61d971760431f7f0afa74e4b71ee233986023b` |
| `tests/test_quick_controls_host_state.py` | `6e1084047713e470d65e80c869e372ca30dc6ddc153a99df618808566837d333` |
| compiled `canopy-classic-spike.exe` | `22f6e51820dfbed4e8fdf8ec0030284a2511a768491be1f1b714b80a75c3b12c` |
| harness `tst_quickcontrols_host.qml` | `5182667ee9ddd0baa371beb64a77332724a707335b28613f16969abeba06d466` |
| harness `result.txt` | `2ad866f8130d50dca8d9aad1c605c6f55454b1b775e0a4a9aef1846a9606d01b` |

## Resource impact

- Measured: `SYNTHETIC` Python unit tests and a `SYNTHETIC` QML harness under
  offscreen software rendering; no sustained idle PSS/CPU sampling was done.
- `NOT_RUN`: real-Mint idle PSS/CPU, compositor wakeups and screen-reader
  output. Screen-reader behavior is unchanged from the existing overlay: the
  same `Accessible.name` and `Accessible.description` bindings are retained on
  the same controls, and no new announcement is introduced.
- The adapter is pure, bounded and event-driven: one immutable snapshot of at
  most four observations, no polling, timer, cache growth or background thread.
  QML uses the existing four-row repeater, so no extra delegates or bindings
  are created. This does not trade stability, security, accessibility or
  approved visuals for a performance gain.

## Honest limits

- The shipped C++ shell still passes no controller to the overlay. Injecting
  the production host-state controller requires an owner-owned change in
  `prototype/classic/main.cpp` (which Hermes owns); this change deliberately
  does not touch it. Until that injection exists, the product binary shows the
  fail-closed disclosure, which is truthful, not a live host reading.
- No Linux Mint NetworkManager/PulseAudio/UPower/logind query was performed.
  This work consumes bounded observations from already-defined contracts; it
  does not discover hardware or perform a privileged host change.
- No owner visual approval, real Mint acceptance, screen-reader session test or
  merge authorization is claimed.
