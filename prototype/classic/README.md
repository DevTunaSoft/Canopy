# Classic Qt Quick technology spike

This is a **standalone demonstration window**, not a Linux desktop session, window manager, dock replacement, installer, or completed product. Dock icons are visual demonstrations except the Search tile, which opens the in-app launcher. No operating-system app-launch capability is claimed. The Files window is a nonfunctional visual composition with static demo folders; it cannot browse the disk. The screenshot self-test now rejects a missing, clipped or overlapping preview, but is not a human aesthetic review.

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

Open or close with **Ctrl+Space**, click the penguin at the top-left, or select the dock Search icon. Search filters the bundled demonstration app catalog, and keyboard Up/Down, Enter and Escape work within the launcher. Enter or clicking an app only displays its preview selection; it never executes an application. The launcher covers (but does not destroy) the Files preview. Use Escape to return to the desktop.

In CI, `--self-test-launcher --self-test-screenshot PATH` captures the real launcher under Xvfb at standard and compact resolutions and rejects dock overlap or truncated rows. These are geometry/runtime tests, not human visual approval.

## Acceptance and measurement
Record distro, Qt version, CPU, GPU, session type, and driver. Run cold and warm starts; sample process proportional set size (PSS) via /proc/PID/smaps_rollup, CPU utilization over five minutes idle, and interaction responsiveness. Capture screenshots for 1080p, HiDPI, keyboard focus, and dark mode. Compare to a minimal GTK alternative before selecting a production toolkit.

GitHub Actions on Ubuntu 24.04 compiles the Qt application and runs a five-second Xvfb smoke test that requires the QML root to create a visible window. This is automated headless startup verification, **not** a screenshot review, visual-quality certification, Linux Mint acceptance, desktop-session test, or performance measurement. See `.github/workflows/classic-qt.yml` and `docs/MINT_VM_ACCEPTANCE.md` for the remaining acceptance work.

## Visual quality gate
See [`docs/VISUAL_ACCEPTANCE.md`](../../docs/VISUAL_ACCEPTANCE.md) for visual-review and performance criteria. Successful headless screenshots verify capture, not visual polish.
