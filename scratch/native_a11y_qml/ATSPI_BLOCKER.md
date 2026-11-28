# Real-Plasma AT-SPI verification: exact `BLOCKED` / `NOT_RUN`

**Status:** `AT_SPI_NATIVE = BLOCKED`; `SCREEN_READER = NOT_RUN`;
`PASS` is not claimed anywhere in this change.

Scope demanded by the task: verify the accessible names/descriptions and the
Window/Help compact-width reachability with AT-SPI inside the real Plasma 6
guest, or record the exact blocker. The blocker below was re-probed fresh for
this branch; raw command output is in `atspi_native_blocker_probe.txt`.

## Fresh probe (host, UTC stamp in the probe file)

| Check | Command | Observed |
| --- | --- | --- |
| Guest VM state | `VBoxManage list runningvms`; `showvminfo Canopy-Test-Plasma6 --machinereadable` | `VMState="running"`, `nic1="nat"`, SSH forward `guestssh -> 127.0.0.1:2223`. |
| Guest execution channel | `guestproperty enumerate Canopy-Test-Plasma6` | Only `/VirtualBox/HostInfo/*` and `HostGuest/Sysprep*` host-provided properties; no guest-additions execution channel. |
| Direct guest command | `guestcontrol Canopy-Test-Plasma6 run --exe /bin/uname ...` | `VBOX_E_IPRT_ERROR: The guest execution service is not ready (yet)`. |
| Authorized credentials | `ls -la C:/Users/X1/.ssh` | `known_hosts` and `known_hosts.old` only; no private key and no supplied guest login. None was guessed or used. |
| Host AT-SPI stack | `python -c 'import pyatspi'` | `ModuleNotFoundError`; host is Windows with no `DISPLAY` / `QT_QPA_PLATFORM`, so no native AT-SPI bus is available on the host either. |
| Screen reader | process scan | No Orca / screen-reader process started or queried. |

## Exact blocker statement

The Plasma 6 image is running, but this session has **no usable guest
execution channel** (guest additions service not ready) and **no supplied
guest login**. Reaching the guest desktop to launch
`canopy-classic-spike` with `QT_ACCESSIBILITY=1` and query AT-SPI therefore
requires credentials the task did not provide. Guessing credentials or
claiming a native result is prohibited. No VM state, snapshot, guest file,
session or setting was changed.

## What is nevertheless verified here

- `STATIC/SYNTHETIC`: `verify_owned_a11y_qml.py` — 11/11 checks PASS
  (accessibility-only edits, compact-width shortcuts, no geometry/art change,
  rendered-input bytes frozen).
- `STATIC/CI-SCOPED`: 42 targeted source-contract tests PASS, including
  `test_classic_status_a11y.test_visual_inputs_are_byte_frozen` and
  `test_classic_qt_source.test_approved_artwork_matches_locked_manifest`.
- `STATIC/CI-SCOPED`: 132 `test_c100_accessibility_*` pattern tests PASS.
- Prior native evidence at the same base (`PR #740`, SHA
  `819aa075…` / `4b19f09a…` / `e07272aa…`) remains the **only** AT-SPI
  evidence for the resting tree; it was captured before this QML change and
  is explicitly **not** re-labelled as verification of this head.

## Next action to close the blocker

1. Supply an authorized guest login or enable the guest-additions execution
   service, and serialize VM use with the other native agents.
2. Rebuild this exact head in the Plasma guest and run the AT-SPI probe at
   1920x1080, 1200x750 and 760x500 with `QT_ACCESSIBILITY=1`, including an
   actual Tab/Alt+W/Alt+H activation of the Window and Help menus.
3. Only then replace `BLOCKED` with `PASS_SCOPED` / `FAIL` for this head.
