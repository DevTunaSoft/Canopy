# Classic Qt Quick technology spike

This is a **standalone demonstration window**, not a Linux desktop session, window manager, dock replacement, installer, or completed product. Dock buttons are deliberately inert; no app-launch capability is claimed. The Files window is an interactive visual-only composition: sidebar navigation, sample-folder selection and name filtering work on local demonstration data, but no live directory browsing or disk access is implemented. The screenshot self-test rejects a missing, clipped or overlapping preview, verifies the original wallpaper fills the window and that all seven dock icons exist, but is not a human aesthetic review. The calendar numeral and all other icons are visual-only examples, not live system integration.

## Prerequisites
CMake 3.21+, C++17 compiler, Qt 6.4+ with Qt Quick and Qt Quick Controls, a working graphical Linux session.

## Build and run
```sh
cmake -S prototype/classic -B build/classic -DCMAKE_BUILD_TYPE=Release
cmake --build build/classic --parallel 2
./build/classic/canopy-classic-spike
```

Use a throwaway build directory; do not replace your normal desktop session. The wallpaper is a single statically painted QML Canvas with an image backing store: verify its proportional memory cost on high-DPI displays before selecting this technique for production.

## Acceptance and measurement
Record distro, Qt version, CPU, GPU, session type, and driver. Run cold and warm starts; sample process proportional set size (PSS) via /proc/PID/smaps_rollup, CPU utilization over five minutes idle, and interaction responsiveness. Capture screenshots for 1080p, HiDPI, keyboard focus, and dark mode. Compare to a minimal GTK alternative before selecting a production toolkit.

GitHub Actions on Ubuntu 24.04 compiles the Qt application and runs a five-second Xvfb smoke test that requires the QML root to create a visible window. This is automated headless startup verification, **not** a screenshot review, visual-quality certification, Linux Mint acceptance, desktop-session test, or performance measurement. See `.github/workflows/classic-qt.yml` and `docs/MINT_VM_ACCEPTANCE.md` for the remaining acceptance work.

## Wallpaper asset candidate

The draft Blue Current static SVG source is packaged in the Qt binary using
`qt_add_resources`. On Linux systems Qt's SVG image-format plugin (Ubuntu:
`qt6-svg-plugins`) is required at runtime. The screenshot self-test refuses
the fallback solid background when SVG decoding fails. A plain Qt build does
not establish that the wallpaper is visually acceptable or memory-efficient.

The old Dock and folder demo art remains **explicitly rejected**. This is not
an accepted redesign. See
[`docs/CLASSIC_VISUAL_REBUILD.md`](../../docs/CLASSIC_VISUAL_REBUILD.md)
for references, provenance, rollout criteria, and remaining work.

## Visual quality gate
See [`docs/VISUAL_ACCEPTANCE.md`](../../docs/VISUAL_ACCEPTANCE.md) for visual-review and performance criteria. Successful headless screenshots verify capture, not visual polish.
