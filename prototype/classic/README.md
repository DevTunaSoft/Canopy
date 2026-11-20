# Classic Qt Quick technology spike

This is a **standalone demonstration window**, not a Linux desktop session, window manager, dock replacement, installer, or completed product. The dock displays the eight approved application **names** (Browser, Mail, Files, Calendar, Photos, Music, Terminal, Settings), but currently renders lightweight fallback Canvas glyphs, not the user's approved premium icon images. Dock clicks do not execute applications. No operating-system app-launch capability is claimed. The Files window is a nonfunctional visual composition with static demo folders; it cannot browse the disk. The screenshot self-test now rejects a missing, clipped or overlapping preview, but is not a human aesthetic review.

## Prerequisites
CMake 3.21+, C++17 compiler, Qt 6.4+ with Qt Quick and Qt Quick Controls, a working graphical Linux session.

## Build and run
```sh
cmake -S prototype/classic -B build/classic -DCMAKE_BUILD_TYPE=Release
cmake --build build/classic --parallel 2
./build/classic/canopy-classic-spike
```

Use a throwaway build directory; do not replace your normal desktop session.

## App launcher (prototype)

Open or close with **Ctrl+Space** or click the penguin at the top-left. Search filters the same eight-app preview catalog shown in the dock, and keyboard Up/Down, Enter and Escape work within the launcher. Enter or clicking an app only displays its preview selection; it never executes an application. The launcher covers (but does not destroy) the Files preview. Use Escape to return to the desktop.

In CI, `--self-test-launcher --self-test-screenshot PATH` captures the real launcher under Xvfb at standard and compact resolutions and rejects dock overlap or truncated rows. An additional `--self-test-search --self-test-screenshot PATH` mode opens the launcher and checks case-insensitive matching (`mUsIc`), empty results for an unknown app, and restoration of all eight results before capturing the screenshot. These are geometry/runtime tests, not human visual approval.

## Acceptance and measurement
Record distro, Qt version, CPU, GPU, session type, and driver. Run cold and warm starts; sample process proportional set size (PSS) via /proc/PID/smaps_rollup, CPU utilization over five minutes idle, and interaction responsiveness. Capture screenshots for 1080p, HiDPI, keyboard focus, and dark mode. Compare to a minimal GTK alternative before selecting a production toolkit.

GitHub Actions on Ubuntu 24.04 is configured to compile the Qt application, capture nonblank 1200×750, 760×500 and 1920×1080 screenshots, exercise the launcher layout, sample a short informational CPU/PSS baseline, and run a headless QML smoke test. Confirm each workflow's status and artifacts for the exact commit before claiming these checks passed. These are automated structural/runtime checks, **not** human screenshot review, visual-quality certification, Linux Mint acceptance, a desktop-session test, or reproducible five-minute performance acceptance. See `.github/workflows/classic-qt.yml` and `docs/MINT_VM_ACCEPTANCE.md` for the remaining acceptance work.

## Visual quality gate
See [`docs/VISUAL_ACCEPTANCE.md`](../../docs/VISUAL_ACCEPTANCE.md) for visual-review and performance criteria. Successful headless screenshots verify capture, not visual polish.
