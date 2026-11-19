# Classic Qt Quick technology spike

This is a **standalone demonstration window**, not a Linux desktop session, window manager, dock replacement, installer, or completed product. Dock buttons are deliberately inert; no app-launch capability is claimed.

## Prerequisites
CMake 3.21+, C++17 compiler, Qt 6.4+ with Qt Quick and Qt Quick Controls, a working graphical Linux session.

## Build and run
```sh
cmake -S prototype/classic -B build/classic -DCMAKE_BUILD_TYPE=Release
cmake --build build/classic --parallel 2
./build/classic/canopy-classic-spike
```

Use a throwaway build directory; do not replace your normal desktop session.

## Acceptance and measurement
Record distro, Qt version, CPU, GPU, session type, and driver. Run cold and warm starts; sample process proportional set size (PSS) via /proc/PID/smaps_rollup, CPU utilization over five minutes idle, and interaction responsiveness. Capture screenshots for 1080p, HiDPI, keyboard focus, and dark mode. Compare to a minimal GTK alternative before selecting a production toolkit.

No Qt compilation or graphical acceptance was performed by the authoring agent. The repository CI currently validates source contracts only.
