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

## Repeatable guest capture (new helper)

After configuring the dedicated Linux Mint VM and manually installing the
required Qt packages, run **inside its actual graphical session**:

```sh
bash tools/mint_vm_capture.sh /path/to/original-landscape.png /path/to/approved-art ~/canopy-mint-evidence
```

Omit the approved-art argument only for unapproved six-icon engineering tests
(you can specify a custom output path only when all preceding arguments are
provided). The helper refuses non-Mint hosts and headless sessions, builds in
`build/mint-vm-acceptance/`, validates the photo using the C++ loader, captures
desktop, launcher, compact and filtered-search screenshots, and collects a
short CPU/PSS baseline with the **same photo and icon mode**. It does not
install packages, replace your session, set wallpaper preferences, touch login
services or reboot. It may skip full HD if the guest display does not advertise
1920×1080.

Successful helper output establishes repeatable standalone Qt rendering only.
**Still required manually:** VM snapshot/revert, Mint reboot checks, HiDPI
and visual assessment, real interaction, five-minute CPU/PSS measurements,
license review, explicit owner visual acceptance, and eventual shell-session
integration. No Mint guest execution evidence exists yet.

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
