# Native window/workspace management (M3, 2026-11-27)

Owner directive: `Canopy_LacOS_Integrated_Execution_Directive_2026-11-27.md`,
SHA-256 `79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083`.
Base: `ec910d7a7275296ecbc8b5e5c459d356205165d1`. Code evidence head:
`9ba055870120c4f5998a858fdcf48fe8646ceaec` (the final head adds this document
only; no production source changed after the probe).

## Scope and ownership

Owned paths only:

- `canopy_features/windows/native_window_management.py` (new decision boundary)
- `scratch/native_windows/test_native_window_management.py` (scoped tests)
- `scratch/native_windows/guest_probe.sh`,
  `scratch/native_windows/probe_native_windows.py`,
  `scratch/native_windows/evidence/**` (guest probe and evidence)
- `docs/NATIVE_WINDOW_MANAGEMENT.md` (this contract)

No tests outside `scratch/native_windows/` were added or modified: `tests/` is
owned by another workstream. The scoped tests are therefore run explicitly
with the worktree root on `PYTHONPATH`, not through `unittest discover -s tests`.
No visual asset, QML, C++, compiled input, settings value, compositor, service
unit or workflow was changed.

## Facilities reused (no duplicate compositor or service)

| Need | Facility actually present on the stock Plasma guest | Use in this change |
| --- | --- | --- |
| Workspace inventory | KWin D-Bus `org.kde.KWin` `/KWin` `currentDesktop() -> i`; FreeDesktop session bus name ownership | Read-only snapshot input; the module never queries the bus itself |
| Workspace switching | KWin D-Bus `setCurrentDesktop(i) -> b` | One allowlisted command descriptor, read back with `currentDesktop` |
| Window activation | FreeDesktop EWMH root `_NET_ACTIVE_WINDOW` | One allowlisted command descriptor, read back with the same property |
| Focus recovery | EWMH `_NET_CLIENT_LIST` / `_NET_ACTIVE_WINDOW` plus the one authoritative snapshot | Fallback chosen from the current workspace only; read back with `_NET_ACTIVE_WINDOW` |

KWin 6.6.4 on the verified guest does **not** expose a D-Bus
`activateWindow` method; activation descriptors correctly target EWMH rather
than inventing a method. `org.kde.KWin` `queryWindowInfo` is interactive and
was **not** used: an exploratory call timed out and must not be repeated while
other agents use the same X display.

`NativeWindowManager` is a single-threaded fold over one authoritative
`DesktopSnapshot`. It validates every field (strict types, bounded UTF-8 text,
ordered containers, duplicate ids, cross-field consistency), emits immutable
`NativeCommand` descriptors from a closed facility/operation allowlist, and
updates state only from trusted read-back values that already exist in that
snapshot. There is no polling, timer, thread, socket, process launch, environment
read, second compositor, second service or hidden event source. Plans are
decision-only: `executed=False`, `observation=NOT_PERFORMED`, `runtime=NOT_RUN`,
`screen_reader=NOT_RUN`, `duplicate_compositors=0`. Legacy workspace and
activation modules are not modified or duplicated.

## Local checks (SYNTHETIC)

Run at the final code head with `PYTHONPATH` pinned to the worktree root:

```text
python3 scratch/native_windows/test_native_window_management.py
Ran 16 tests in 0.006s ... OK; rc=0
python3 tools/check_foundation.py
PASS: foundation files, tagline, and local Markdown links; rc=0
python3 -m unittest tests.test_c100_windows_workspace_inventory \
  tests.test_pe102_window_activation_contracts tests.test_c100_windows_focus_intents
Ran 76 tests in 0.048s ... OK; rc=0
```

The 16 scoped tests cover ordered/bounded snapshot parsing, hostile Unicode,
wrong types (including `bool` as an ordinal), duplicate ids, cross-field
contradictions, allowlisted KWin/EWMH commands, no-op and unknown targets,
off-workspace activation rejection, focus-recovery fallback selection and empty
recovery, hostile read-back rejection without mutation, bounded history and
closed-state behavior. These are pure Python checks: `SYNTHETIC`, not runtime
acceptance. A full `unittest discover -s tests` was deliberately not launched
concurrently with another agent's in-flight full suite on this host.

## Real Plasma verification (SCOPED_ON_GUEST_RUNTIME)

Guest `Canopy-Test-Plasma6`, stock X11 Plasma session reached through the
existing NAT SSH forward `127.0.0.1:2223` with the pre-existing scratch key.
No VM start/stop/snapshot/revert, package, compositor, service, desktop,
window, desktop entry or persistent setting was changed by this work.

Command: `bash /home/canopy/native_window_management_20261127/probe/guest_probe.sh`
(host orchestrator: `scratch/native_windows/probe_native_windows.py`).

| Check | Result | Evidence |
| --- | --- | --- |
| P01 real Plasma X11 session (`startplasma-x11`, `kwin_x11`, `plasmashell`) | PASS | guest log `SESSION` |
| P02 exactly one `kwin_x11` and one `plasmashell`, before and after | PASS | guest log `COMPOSITOR COUNT` / `... AFTER` |
| P03 KWin D-Bus exposes `currentDesktop` and `setCurrentDesktop(i)->b` | PASS | guest log `KWIN INTROSPECT` |
| P04 `org.kde.KWin` owned on the FreeDesktop session bus (PID 5384) | PASS | guest log `FREEDESKTOP BUS NAME`, `KWIN BUS OWNER` |
| P05 read `currentDesktop` = `i 1`; no-op `setCurrentDesktop(1)` = `b false`; read-back unchanged `i 1` | PASS | guest log `CURRENT DESKTOP`, `SET SAME DESKTOP (1)`, `CURRENT DESKTOP AFTER` |
| P06 EWMH `_NET_ACTIVE_WINDOW` / `_NET_CURRENT_DESKTOP` read-back | **NOT RUN** | `EWMH_RC=124` (bounded 8 s `xprop -root` timeout) |
| P07 X client liveness for activation/focus recovery | **NOT RUN** | `WMCTRL_RC=124` (bounded 8 s `wmctrl -l` timeout) |

Overall probe verdict: `PASS_WITH_NOT_RUN` (5 PASS, 0 FAIL, 2 NOT_RUN).

**Exact blocker for P06/P07 (NOT RUN, not a product failure).** At
`2026-11-28 06:16:41 UTC` another agent's X automation chain held the shared
guest X display: bash PID `54982` running a sequence of `xdotool key` /
`xdotool mousemove ... click 1` / `scrot` commands for an M3 tray task, with an
`xdotool` child process in `S` state. Both bounded X read attempts returned
124 while every D-Bus check succeeded. That process is not owned by this work
and was deliberately not terminated. Therefore real window activation,
multi-window focus recovery and EWMH state read-back are `NOT RUN` with this
exact blocker, never reported as PASS.

Multi-desktop *crossing* was also `NOT RUN`: the stock session has one virtual
desktop (`kwinrc` has no `[VirtualDesktops]` section), so `setCurrentDesktop(1)`
is a correct no-op (`b false`). Creating a second desktop or restarting the
compositor to force a switch would change shared session state and is outside
this bounded increment.

## Evidence and labels

- `scratch/native_windows/evidence/guest_probe.log` — SHA-256
  `b2c2f76053159e751b29f5e77fd5dbc7a5290874ef48d5e5a172348d4c32d2b2`.
- `scratch/native_windows/evidence/native_window_probe.json` — SHA-256
  `c110dd92d4d9f320190592f37f2296e13aafe947699c374e029aba5128738e8e`;
  schema `canopy.native_window_management_probe/1`, exact `head_sha`
  `9ba055870120c4f5998a858fdcf48fe8646ceaec`, verdict `PASS_WITH_NOT_RUN`.
- `scratch/native_windows/evidence/SHA256SUMS.txt` — SHA-256
  `3eec1c4861fc6ca0a8535c0a44c8e598b9a8dc3d5e9874a4b409a5bf679c807a8`;
  verified with `sha256sum -c` from its own directory, rc=0.
- `scratch/native_windows/tests.log` — SHA-256
  `47cbd4438c5430d55fecc32e64801601cedf00c00002ad76e4af79b182fae123`.
- `scratch/native_windows/foundation.log` — SHA-256
  `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad`.
- `scratch/native_windows/targeted_existing.log` — SHA-256
  `fed465d2796fed28b439258483a41e0aa515fb6cf7389f176b5541440ee7e44d`.

`SCOPED_ON_GUEST_RUNTIME`: the five D-Bus checks above on the real Plasma guest.
`SYNTHETIC`: the 16 pure-Python tests and the 76 existing targeted tests.
`NOT_RUN`: real EWMH activation/focus recovery, screen-reader and assistive
technology behavior, automatic CI-on-guest acceptance, real shell-owned PSS/CPU
measurement, owner visual acceptance, release and any merge/self-approval.

Resource impact: one bounded pure-Python module (two `deque`s capped at 16,
lazy immutable snapshots, no background work) exercised only on explicit calls.
No process, timer, long-lived cache, daemon, polling loop, GPU effect or visual
asset was added, so no stability, security, accessibility or approved visual
quality was traded for performance. This is a scoped draft PR; it does not
merge, approve itself, alter protected `main`, or claim native desktop
acceptance.
