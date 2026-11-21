> **Reference-correction notice (November 20, 2026).** The user rejected
> PR #72's claim that its combined tree+penguin emblem and colored penguin
> matched supplied icons. The current prototype instead uses a traced
> white-on-dark penguin launcher from a recovered reference image and
> six moodboard application *categories* (not verified master artwork).
> See [VISUAL_REFERENCE_PROVENANCE.md](../../docs/VISUAL_REFERENCE_PROVENANCE.md).
> Visual sign-off remains pending.\n\n# Classic Qt Quick technology spike

## Files window content alignment

The screenshot-driven Qt preview now models the same eight **sample** folder
categories as the newly accepted desktop concept (Desktop, Documents,
Downloads, Music, Pictures, Public, Templates, Videos), rather than the
previous six unrelated names. This remains local demo content: no filesystem
contents or privacy-sensitive directory information is read. The sidebar uses
a clipped, vertically scrolling navigation area so compact preview resolutions
cannot silently lose entries. The internal folder pictogram is original
`assets/ui/folder-blue.svg`; it is a generic file-content symbol,
**not a substitute for the exact user-approved Files dock PNG**.

## Exact approved artwork integration (new)

The old six-icon SVG Dock remains an **unapproved legacy test scene** when
this demo runs without art arguments. To launch the true eight-icon visual
candidate, download `Canopy_Classic_Exact_Artwork_Runtime.zip` from
ChatGPT Library → Canopy, extract to an `approved-art` directory, then run:

```sh
./build/classic/canopy-classic-spike \
  --approved-art-dir /absolute/path/to/approved-art \
  --self-test-approved --self-test-size 1200x750 \
  --self-test-screenshot approved-classic.png
```

The program rejects the entire set before rendering if any of the eight
PNG images or blue-wave background differs from the canonical SHA-256.
The new approved mode does **not** switch to the hand-painted SVG demo
icons on missing files. The PNGs are *not yet present in this GitHub branch*
because the connector's text-file operations cannot transfer binary art;
they are preserved in the user's Canopy Library ZIP. Full exact-image Qt
screenshot acceptance is blocked until the package is supplied to the
runner. See [canonical artwork](../../docs/CLASSIC_CANONICAL_ARTWORK.md).



This is a **standalone demonstration window**, not a Linux desktop session, window manager, dock replacement, installer, or completed product. The Files dock button now shows or hides the existing demonstration Files window and its active dot follows visibility. The automated screenshot smoke test invokes the dock's actual QML click signal, verifies both hide and restore, then captures the original visible scene. Other app tiles remain inert; no app-launch capability is claimed. The Files window is an interactive visual-only composition: sidebar navigation, sample-folder selection and name filtering work on local demonstration data, but no live directory browsing or disk access is implemented. The screenshot self-test rejects a missing, clipped or overlapping preview, verifies the original wallpaper fills the window and that all seven dock icons exist, but is not a human aesthetic review. The original Canopy launcher and the seven dock concepts are visual-only; no app launch or desktop services are implied.

## Prerequisites
CMake 3.21+, C++17 compiler, Qt 6.4+ with Qt Quick and Qt Quick Controls, a working graphical Linux session.

## Build and run
```sh
cmake -S prototype/classic -B build/classic -DCMAKE_BUILD_TYPE=Release
cmake --build build/classic --parallel 2
./build/classic/canopy-classic-spike
```

Use a throwaway build directory; do not replace your normal desktop session. The Blue Current wallpaper is a static cached SVG image loaded by Qt. Measure rasterization memory at high DPI; avoid expensive refresh effects.

## Acceptance and measurement
Record distro, Qt version, CPU, GPU, session type, and driver. Run cold and warm starts; sample process proportional set size (PSS) via /proc/PID/smaps_rollup, CPU utilization over five minutes idle, and interaction responsiveness. Capture screenshots for 1080p, HiDPI, keyboard focus, and dark mode. Compare to a minimal GTK alternative before selecting a production toolkit.

GitHub Actions on Ubuntu 24.04 compiles the Qt application and runs a five-second Xvfb smoke test that requires the QML root to create a visible window. This is automated headless startup verification, **not** a screenshot review, visual-quality certification, Linux Mint acceptance, desktop-session test, or performance measurement. See `.github/workflows/classic-qt.yml` and `docs/MINT_VM_ACCEPTANCE.md` for the remaining acceptance work.

## Wallpaper asset candidate

The draft Blue Current static SVG source is packaged in the Qt binary using
`qt_add_resources`. On Linux systems Qt's SVG image-format plugin (Ubuntu 24.04:
`libqt6svg6`) is required at runtime. The screenshot self-test refuses
the fallback solid background when SVG decoding fails. A plain Qt build does
not establish that the wallpaper is visually acceptable or memory-efficient.

The main preview now has lightweight *working demo menus* for showing/hiding
the sample Files window, resetting sample selection and opening an About
dialog. These actions do not control the Linux desktop. Sample folders reuse
one consistent authored blue folder SVG rather than the rejected pastel tiles.
There is no real file browser, launcher or system menu integration.

The older Canvas dock artwork was rejected and replaced on the separate icon
candidate branch with six original source-controlled SVG candidates. The new
family's readiness is checked at runtime and its source safety is checked with
`tools/check_icon_set.py`, but it still requires human aesthetic review. The
previous generic Home/Mail/Calendar lineup is no longer used. The brandboard-aligned concepts now include Canopy, Files, Browser, Photos, Settings, Terminal and Trash, plus a separate penguin launcher. These icons are still *visual candidates*, not approved production masters. This is not
an accepted redesign. See
[`docs/CLASSIC_VISUAL_REBUILD.md`](../../docs/CLASSIC_VISUAL_REBUILD.md)
for references, provenance, rollout criteria, and remaining work.

## Visual quality gate
See [`docs/VISUAL_ACCEPTANCE.md`](../../docs/VISUAL_ACCEPTANCE.md) for visual-review and performance criteria. Successful headless screenshots verify capture, not visual polish.
