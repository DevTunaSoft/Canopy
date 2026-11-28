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
(`private-evidence/scratch/canopy-qc-harness`) is not part
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

Run from pristine detached worktrees at the exact tip on the same Windows 11
host, with `PYTHONPATH=<worktree>` and
`python -m unittest discover -s tests -p 'test_*.py'`:

- Pristine base `33d8d1bf6709abfd82f3b55829ad2cd75a3d43ad`: **3412 tests,
  OK (skipped=45), 1772.117 s**; log `suite-base.txt`, SHA-256
  `bd667b94d98a4db7717e6f7c015d77ee4bb4b2d8f4376ad56181e38424da68b5`.
- Candidate worktree with this change: **3436 tests, OK (skipped=45),
  1754.980 s**; log `suite-candidate.txt`, SHA-256
  `af316e4270adc714d20063f72f8961ca293f3d1284964912a8f3f6ced6f9c051`.
- Delta: +24 tests, no new failure or error; the `FAIL:`/`ERROR:` name sets are
  both empty and skip counts are identical. The slower wall clock on the base
  run reflects contention from other agents' concurrent suites on this host.

Both logs were run under heavy host load (up to 14 concurrent unittest
suites); they are real runs with exact exit code 0, not synthesized counts.

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

---

## Compiled-shell injection of the host-state controller (SLOT 1)

Current head: recorded exactly in the draft PR body; the tested artifacts below
are pinned by SHA-256 so the evidence survives a later head change. Base: PR #615
head `b5a15b2c8a3d712d0141bac83845a23ded47696f` (queue integration tip
`8269ec9`). Only four paths are owned: `prototype/classic/main.cpp`,
`prototype/classic/CMakeLists.txt` (deliberately unchanged), the new
`tests/test_quick_controls_host_injection.py`, and this note. No merge is
authorized.

### What the compiled shell now does

- `main.cpp` defines `QuickControlsHostStateController`, an in-process `QObject`
  that exposes only `view(domain)` to QML — the same contract the Python adapter
  implements. It consumes bounded payloads through `applyHostEvent(topic,
  payload)` on the four existing `canopy_core.host_events` topics and the
  existing allowlisted field names (`network_connected`, `audio_muted`,
  `battery_charging`, `volume_percent`, `brightness_percent`, `settings_bridge`,
  `source`). No topic or field is added.
- The trusted shell delivers one startup payload on `capabilities.report`
  containing only `source` and the real `settings_bridge` value derived from
  `enableSystemApps && SystemAppLauncher.canLaunch("Settings")`. No
  network/audio/battery fact is invented by the shell. Session stays
  `unknown`: there is no reconciled session source in the compiled process.
- The controller is registered as `canopyHostState` and passed into the
  already-registered overlay as its `hostState` initial property. A validated
  update emits `viewChanged()`; the compiled shell rebinds that same property
  so QML bindings which call `view()` are invalidated. The connection's context
  object is the overlay and the controller is declared before
  `QQmlApplicationEngine`, so the controller outlives every object pointing at
  it and no raw context pointer dangles at shutdown.
- No daemon, event bus, D-Bus, socket, QProcess, privileged write, shell command,
  new QML file, `Main.qml`, asset or geometry change is introduced. Direct
  controls stay denied (`no-host-interface` for network/audio,
  `privileged-host-change` for power/session); only the existing Settings bridge
  can be honestly available.

Fail-closed details: validation is atomic — a wrong type (including a bool used
as an integer percentage), an out-of-range percentage, an unsupported topic, an
oversized/non-allowlisted source string or a malformed field rejects the whole
payload before any member changes. Unknown fields owned by other consumers are
ignored and never echoed. Missing facts remain `unknown` with
`source: "none"` and the fixed `Unavailable — …` disclosure; no caller text is
interpolated into a label.

### Evidence (real commands and outputs)

Environment: Windows 11, Python 3.14.9, MSYS2 UCRT64 Qt 6.12.0, CMake 4.5.1,
Ninja 1.13.2, GCC 16.2.0, `QT_QPA_PLATFORM=offscreen`,
`QT_FORCE_STDERR_LOGGING=1` (Windows GUI-subsystem binary). PATH was exported as
`/c/msys64/ucrt64/bin:$PATH` before every build; `libisl-23.dll` did not occur.
GIO dev packages are absent, so the existing disabled-native-launch fallback
applies and the Settings bridge is unavailable in these runs.

| Check | Command | Result / artifact SHA-256 |
|---|---|---|
| Clean configure | `cmake -S <worktree>/prototype/classic -B <build> -G Ninja -DCMAKE_BUILD_TYPE=Release` | exit 0; `cmake-config.log` `93400c9dd6fdd9726d6fcc2bb390c831a9c86d088bc0920248d8e90c9318f2d0` |
| Clean compile | `cmake --build <build> --parallel 4` | exit 0, 52/52 Ninja steps including `QuickControlsOverlay_qml.cpp.obj`; `cmake-build.log` `b31850749c3f284eaf814fd87bb7b70e0721d81571dd2cc4374e97faadbdbe56`; binary `canopy-classic-spike.exe` `19fe123ac8744d833cca47dd9cf392703defa5e885f620ce2719673f5f1339f0` |
| Existing fail-closed fixture | `canopy-classic-spike.exe --approved-art-dir <art> --self-test-approved --self-test-quick-controls` | exit 0; `QUICK_CONTROLS_FIXTURE_PASS: opener wired, four domains fail closed, approved visuals unchanged`; `selftest-qc.log` `8509965c47f27cac598931a71c16748934bddf868cada3c5eb45e253f591efcd` |
| New compiled injection fixture | `canopy-classic-spike.exe --self-test-quick-controls-host` | exit 0; renders `Connected`, `Sound on · Volume 42%`, `On battery · Brightness 68%`, `Unknown — no host status`; all direct controls disabled; malformed and unlisted-topic events rejected without mutating the view; `QUICK_CONTROLS_HOST_SELF_TEST_PASS: wired=ok details=ok privileged=denied hostile=rejected visuals=unchanged`; `selftest-qc-host.log` `f61106d849a053fa85eb6308ac3e630ea12d6808180aa9875b0cf8d688645e7d` |
| New targeted tests | `python -m unittest discover -s tests -p 'test_quick_controls_host_injection.py'` | 12 tests PASS (`test_quick_controls_host_injection.py` pinned below) |
| Full suite | `PYTHONPATH=<worktree> python -m unittest discover -s tests -p 'test_*.py'` | Pristine base at exact `b5a15b2c8a3d712d0141bac83845a23ded47696f`: **3436 tests, OK (skipped=45), 1265.704 s**, exit 0, log SHA-256 `30503ff30cab86571c553507900dceea709b5846edabe2de47ff0b7be041c4de`; candidate at the same tip with this change: **3448 tests, OK (skipped=45), 655.670 s**, exit 0, log SHA-256 `e0aacec069cd0530284022e8b7d9208ddb12aac4f28d2bfaa0ba1c4077162848`. Delta: +12 tests, identical skip count, empty FAIL/ERROR name sets on both sides. |

#### Three screenshots (compiled binary, approved art, offscreen)

Each invocation used `--approved-art-dir <art> --self-test-approved
--self-test-size SIZE --self-test-screenshot <png>` and exited 0 with
`SELF_TEST_PASS: nonuniform window screenshot captured`.

| Capture | SHA-256 | Log SHA-256 |
|---|---|---|
| `classic-1920x1080.png` | `30c236a51c7f404213ea1b963431c1d1c8bdf0f482b950276d620d0bc4289479` | `0f63bb0758dc076906bff5501e5e2034e4a9d32517762ae8c745d0943b000870` |
| `classic-1200x750.png` | `ea0426598530641e9a5980ac083e455b1d6a658dec8cf37b5ac5f022bcb09265` | `52f7ed6d222177c580e4d8b5b2456247665da877de4d1f734bc9b82569d3bd0c` |
| `classic-760x500.png` | `9a279e59a87fca8464a605d67a6379bf08310720c5c1d89e98460ec97dcfd847` | `8e22de45007e371cf6d7f226ef74fcae44cc6eaf19b18e1f59c550a3061aacdf` |

The images show the approved resting desktop with the Applications launcher in
its verified state; the quick-controls overlay remains hidden, so no approved
visual identity changed. Byte hashes differ from PR #615's captures because the
dynamic clock text and offscreen software rasterisation vary between runs; an
ffmpeg PSNR comparison against those captures is 55.61 / 51.80 / 48.00 dB at the
three sizes, with identical composition, dock geometry, icons, wallpaper and
panel state. These are scoped offscreen render checks, not owner visual approval.

### Artifact hashes (SLOT 1)

| Artifact | SHA-256 |
|---|---|
| `prototype/classic/main.cpp` | `160c35617b7d284710f8d6ae7866dc8cc06c6933dd5019c6a8ed8e805d5b1a0f` |
| `tests/test_quick_controls_host_injection.py` | `4f38fcf3a92880617c96589d4e94649459e1371e51785fe3bd2476978046c962` |
| `qmllint-strict.txt` (empty strict-lint output) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `targeted.log` (12 tests OK) | `1a5fb4aa964a63b203b4d8d82a7171d8bf6f2fd66cd38f35a1cfd2d49f47fc34` |

`prototype/classic/CMakeLists.txt` is unchanged (SHA-256
`4644f4cd3c2791e53d0312b3685028ac8fe75904aa123215c1bb65ec0ef97474`).

### Resource impact

- Measured: `SYNTHETIC` Python contract tests and a `SYNTHETIC` compiled
  offscreen self-test; no sustained idle PSS/CPU sampling was done.
- `NOT_RUN`: real-Mint idle PSS/CPU, compositor wakeups and screen-reader
  output. Screen-reader bindings are unchanged: the same
  `Accessible.name`/`Accessible.description` on the same rows, no new
  announcement.
- The controller holds bounded scalars, has no polling, timer, cache, thread or
  transport, and rebinds only the existing `hostState` property on a validated
  event. No stability, security, accessibility or approved visual is traded for
  a performance gain.

### Honest limits

- The fixture's `42`/`68`/`true`/`false` values are deterministic, bounded
  observations delivered in-process through the same API a trusted host uses;
  they are **not** real NetworkManager/PulseAudio/UPower/logind readings, which
  would require forbidden transports or privileged access.
- No Linux Mint acceptance, owner visual approval, screen-reader session test
  or merge authorization is claimed. CMake is intentionally unchanged: the
  controller is defined in `main.cpp`, which the existing target already builds.
