# ND-041 — native settings/controls state wiring into compiled Classic

## Scope and ownership

Base tip: `7535c0e9bc030d8fdf500967e56e385530bede96`
(`integration/canopy-classic-20261123`, fetched live from `origin`).

Branch: `feat/nd041-settings-controls-wiring-7535c0e9`. Draft PR only; no merge
into `main` or the integration branch is requested or performed.

Exactly four tracked paths change:

- `prototype/classic/SettingsPanel.qml`
- `prototype/classic/QuickControlsOverlay.qml`
- `tests/test_nd041_native_settings_controls_wiring.py` (new)
- `tests/test_classic_status_a11y.py` (pin sync only — two SHAs and their comment)

Not touched: `main.cpp`, `CMakeLists.txt`, `FileModel`, `LauncherModel`,
`WindowActivationState`, assets, wallpaper, dock geometry, manifests,
workflows, any pure Python contract, or any other panel. No new event topic,
service, daemon, transport, privilege or host-device access is added.

## What was wired

The compiled shell already registers two read-only, in-process bridges as QML
context properties: `canopySettingsPreferences` and `canopyHostState`. It also
injects the same objects as the panels' `controller` / `hostState` properties
at creation time. Before this change the panels consumed only the injected
property; a QML harness or any future host that registers the context source
without `initialProperties` saw the fail-closed fallback.

The owned panels now resolve state in a fixed, bounded order:

| Panel | Resolution order | Contract mirrored |
|---|---|---|
| Settings | injected `controller` → `canopySettingsPreferences` → no store | `canopy_features/settings/persisted_preferences.py`, `canopy_features/accessibility/reduced_motion_contract.py` |
| Quick controls | injected `hostState` → `canopyHostState` → injected `controller` → no status | `canopy_features/quick_controls/host_state.py`, `canopy_features/system/quick_controls_state.py` |

Both gates are synchronous view calls: no timer, polling loop, subscription,
socket, file read, process or duplicate service. The injected controller stays
first, so the compiled shell's `viewChanged` rebinding keeps its existing
event-driven behavior. When no trusted object is present, the panels keep the
pre-existing fixed `Unavailable — …` disclosure; `None` is never coerced into
`false`, `0` or a previous value, and no control becomes enabled.

New validation is fail-closed before anything reaches a rendered label:

- Settings: `try/catch` around `view(key)`, exact key match, bounded
  title/value/disclosure/source strings, printable-ASCII source token, and an
  empty value for every row that is not the one contract-backed preference.
- Quick controls: exact domain match, enumerated per-domain status token, the
  fixed label for that token, bounded provenance token, boolean observation,
  `AVAILABLE`/`UNAVAILABLE` availability, and a decision pair whose `allowed`
  flag, reason and disclosure all match the merged `DISCLOSURES` vocabulary.
  Detail kind/value bounds from the previous revision are retained.

The single preference write path still uses `setPreference(key, value)` on the
trusted controller and only for `reduced_motion` in
`{unset, full, reduce}`. No privileged quick-control action is enabled:
`suspend` and `lock` remain denied and the existing opt-in system-launch bridge
is still the only working action.

## Visual lock

`tests/test_nd041_native_settings_controls_wiring.py` pins the SHA-256 of every
byte from `visible: opened` to EOF in both panels — the half that contains all
geometry, colours, fonts, object names, text and component order. Those two
digests are unchanged from the base tip:

| Rendered visual half | SHA-256 |
|---|---|
| `SettingsPanel.qml` | `38f1cf1512dff833dee7f8e1f844724682b2a1319bb3c798c501de0ebbbf192c` |
| `QuickControlsOverlay.qml` | `257e00bb5f337495bcd46ba97c34cbdb33d68ac99566802e7bd92f0e4d4fd02b` |

The older `test_classic_status_a11y` projection hashes the *whole* file minus
accessibility lines, so adding behavior above the visual boundary necessarily
changes them. Their two values were synced to the new bytes in the same PR; the
rendered-byte pins above are the stronger, unchanged visual guard. No visual
source, asset or typography input was edited.

## Verification — SYNTHETIC / NOT_RUN

Environment: Windows 11, Python 3.14.9, MSYS2 UCRT64 `qmllint` 6.12.0. All
logs are at the absolute cache-scratch directory
`C:/Users/X1/AppData/Local/hermes/cache/scratch/nd041_evidence/`; the
repo-relative `scratch/nd041_evidence` is `ABSENT` (`sha256=null`).

| Check | Command | Result | Log SHA-256 |
|---|---|---|---|
| RED at exact base tip (new test only, copied into detached `7535c0e9` worktree) | `PYTHONPATH=. python -m unittest tests.test_nd041_native_settings_controls_wiring` | rc=1, 10 tests, 26 failures + 2 errors (all wiring/gate markers absent) | `270e087f4f6c7c32ff7697d2a16a272d74539114b2f015552ea6e784ac0c4846` |
| Targeted GREEN | `PYTHONPATH=. python -m unittest tests.test_nd041_native_settings_controls_wiring tests.test_classic_status_a11y tests.test_quick_controls_host_state tests.test_classic_quick_controls_state tests.test_quick_controls_host_injection tests.test_c100_settings_persisted_preferences` | rc=0, 108 tests, OK | `241506c414c7b24c5b5fd278f4ecf63b0029978b4e1a0a8fe0f9d398f5d3d007` |
| Strict QML lint | `qmllint --unqualified disable prototype/classic/SettingsPanel.qml prototype/classic/QuickControlsOverlay.qml` | rc=0, empty output (no warnings) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Foundation check | `python tools/check_foundation.py` | rc=0, `PASS: foundation files, tagline, and local Markdown links` | `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad` |
| Foundation tests | `PYTHONPATH=. python -m unittest tests.test_foundation tests.test_foundation_link_scope_guard` | rc=0, 12 tests, OK | `6a0db8c58a9ed9fb6c4bd0c5eb5c74dc2424aef37d5854cf18bd779b83c9c7d3` |

`SHA256SUMS.txt` in that directory carries the LF-only sidecar lines for all
five logs. No full suite, VM, Qt build, desktop session or native device read
was run.

## Resource impact

- Measured: `SYNTHETIC` Python source gates plus strict `qmllint`. No timing
  or sustained idle measurement is claimed as a performance win.
- `NOT_RUN`: real-Mint idle PSS/CPU, compositor wakeups and power draw.
- Screen-reader behavior (`screen-reader`): `NOT_RUN`. The accessibility lines
  and announcement blocks are byte-identical; the new code emits no UI,
  announcement or accessibility metadata of its own.
- Bounded by construction: three/four synchronous `view()` calls per resolved
  domain, no retained state, no cache, no timer, no thread and no new service.
  Nothing here trades stability, security, accessibility or approved visuals
  for a minor performance gain.

## Honest limits and blocker

This proves QML-side consumption and validation of the already-registered host
bridges. It does not prove compiled binary behavior, real NetworkManager /
PulseAudio / UPower readings, or Linux Mint acceptance; those need a Qt build
and a real session, which are deliberately out of this task's scope.

Native audio/network/power probing or privileged control would require owner
authorization for host device and session access. No such access was attempted:
this change stays read-only and fail-closed and therefore reports no blocker
for the work performed. Any follow-up that enables real device reads or
privileged actions is `BLOCKED_OWNER_AUTHORIZATION` until the owner grants it.
