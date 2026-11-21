# Linux Mint VM acceptance protocol

**Status: prepared, not executed.** Do not claim Linux Mint acceptance from Ubuntu GitHub Actions alone.

## Safety and prerequisites
Use the dedicated Canopy-Test-Mint VirtualBox VM, not a production host. Confirm Mint is actually installed, VM snapshots work, and guest tools are available. Keep the standard Mint desktop as the default session. Never replace the login manager or compositor for this technology spike.

## Procedure
1. Record host/guest OS, kernel, Mint edition, VirtualBox version, vCPU, RAM, graphics controller, acceleration, Qt version, and commit SHA.
2. Snapshot the powered-off VM as `canopy-pre-spike`.
3. Clone the tested branch in the guest. Install Qt 6 build packages and QML modules from the Mint/Ubuntu repository; record exact package versions.
4. Run `cmake -S prototype/classic -B build/classic -DCMAKE_BUILD_TYPE=Release` and `cmake --build build/classic --parallel 2`.
5. Launch `./build/classic/canopy-classic-spike` from a terminal inside the normal Mint session. Confirm the window appears and closes cleanly.
6. Capture screenshots at 1920x1080 and available HiDPI settings; check dock alignment, top-bar readability, focus navigation, and clipping.
7. Record process PSS from `/proc/<pid>/smaps_rollup`, idle CPU over five minutes, launch time, and any QML warnings. Use repeatable commands and store raw measurements.
8. Restart guest, verify Mint still logs in normally, and revert snapshot if any unexpected change occurs.

## Evidence template
- Commit SHA:
- Guest and host environment:
- Build: PASS / FAIL / BLOCKED / NOT RUN
- Launch and shutdown:
- Visual review:
- Keyboard and accessibility:
- Five-minute idle CPU and PSS:
- Regression notes:
- Screenshot and logs:
- Reviewer and date:

## Exit criteria
No critical visual or session failures, no undocumented persistent host changes, reproducible build, and baseline metrics. This validates only a standalone window; a real Canopy session needs separate acceptance tests.

## Optional installed-application launch acceptance (new)

This is **not yet executed in a genuine Linux Mint guest**. After building
Canopy Classic and preserving the normal Cinnamon session, first test the
default preview remains isolated. Then, in the same guest session:

```sh
./build/classic/canopy-classic-spike --enable-system-apps
```

Confirm the Files dock opens installed Nemo (or reports it unavailable),
Browser opens the installed Firefox (or reports unavailable), and Terminal
launches a visible installed terminal. Distinguish GIO `launch accepted`
from actually functioning, focused application windows. Close each app
normally, relaunch repeatedly, and confirm Mint Cinnamon retains complete
session ownership. Check shortcuts, keyboard navigation, errors, idle
CPU/PSS, a reboot and rollback. No automated Ubuntu Xvfb smoke test can
replace this Mint evidence.
