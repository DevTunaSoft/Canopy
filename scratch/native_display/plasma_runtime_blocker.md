# M4 native Plasma display-response verification blocker

**Status:** `NATIVE_RUNTIME = NOT RUN`. This is an exact, evidence-backed
blocker, not a claim that the product works or fails on a real desktop.

**Base:** `ec910d7a7275296ecbc8b5e5c459d356205165d1`
(`integration/canopy-plasma6-20261127` live tip when this work started).
**Directive:** SHA `79e30d79a580...`, section 7 / M4 (multi-monitor, HiDPI),
section 11 evidence labels.

## What was actually checked

| Check | Command / artifact | Observed |
| --- | --- | --- |
| Compiled or host consumer of the response module | `grep -rn -E 'handle_recovery_result\|handle_logical_dpi_change' prototype canopy_features` → `blocker_consumer_search.txt` | Only the two defining methods in `display_change_response.py`; zero C++/QML/host callers at this base. |
| Existing scope note | `docs/CLASSIC_DISPLAY_CHANGE_RESPONSE.md` lines 89-99 | Explicitly records compiled Qt wiring as `NOT_RUN` and a separate change. |
| VM availability | `VBoxManage list runningvms` → `blocker_vbox_runningvms.txt`; `showvminfo Canopy-Test-Plasma6 --machinereadable` → `blocker_vbox_vminfo.txt` | `Canopy-Test-Plasma6` is registered and `VMState="running"`, `nic1="nat"`, no forwarding rules. |
| Guest-side execution readiness | `VBoxManage guestproperty enumerate Canopy-Test-Plasma6` → `blocker_vbox_guestprops.txt` | Only host-provided properties (`/VirtualBox/HostInfo/*`, `HostGuest/Sysprep*`); no guest-additions channel. A direct `guestcontrol run --exe /bin/uname` attempt failed with `VBOX_E_IPRT_ERROR: The guest execution service is not ready (yet)`. |
| Host SSH material | `ls -la C:/Users/X1/.ssh` | `known_hosts` only; no private key or supplied guest login in this session. No credentials were guessed or used. |
| In-repo host seam | source read of `canopy_features/dock/display_change_response.py` | The module only returns decisions. It never polls, connects Qt signals, resizes a window or changes a binding. |

## Exact blocker

A Plasma 6 VM image exists and is running, but no compiled Qt/host adapter at
this exact base consumes `DisplayChangeResponse.handle_recovery_result` or
`handle_logical_dpi_change`. There is therefore no path for a real
`screenAdded` / `screenRemoved` / `primaryScreenChanged` /
`geometryChanged` / device-scale signal to reach the response module, and no
way to observe a real monitor add/remove or HiDPI change through it. The VM
additionally exposes only NAT with no forwarding rule and no guest-additions
execution channel, and this session was given no authorized guest login.

Adding that adapter would require compiled C++/QML changes outside this
task's owned file set and a separate reviewable change; it was deliberately
not fabricated here. All display-response evidence in this PR is therefore
`SYNTHETIC` decision-logic testing on the Windows host. Screen-reader and
accessibility announcement behavior is `NOT_RUN`.

## Next action to close the blocker

1. Land a small compiled host adapter that connects the five Qt/KWin screen
   signals to a topology producer calling `handle_recovery_result`, and a
   device-scale producer calling `handle_logical_dpi_change`; apply only
   `KIND_RELAYOUT` plans to the existing window geometry.
2. Provision authorized guest access (guest additions plus a supplied login
   or console access) and serialize the VM work with other agents.
3. Inside the real Plasma session run
   `python3 scratch/native_display/guest_probe.py --adapter '<adapter command>'`
   and attach its JSON, the adapter log and real screenshots at 1920x1080,
   1200x750 and 760x500, plus 150%/200% scale captures.
4. Only then label the result `NATIVE_RUNTIME PASS`/`FAIL`; a green source
   test or a structural probe never substitutes for that label.
