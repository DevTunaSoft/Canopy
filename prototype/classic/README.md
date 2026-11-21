> **Reference-correction notice (November 20, 2026).** The user rejected
> PR #72's claim that its combined tree+penguin emblem and colored penguin
> matched supplied icons. The current prototype instead uses a traced
> white-on-dark penguin launcher from a recovered reference image and
> six moodboard application *categories* (not verified master artwork).
> See [VISUAL_REFERENCE_PROVENANCE.md](../../docs/VISUAL_REFERENCE_PROVENANCE.md).
> Visual sign-off remains pending.\n\n## November 20 visual refinement — compiled Qt rendering

The owner requested fully **rounded** dock images with no pixels escaping
their rounded boundaries, less over-zoomed artwork, and a **full-color**
penguin at upper left. The source-locked eight PNGs are unchanged. On
approved-art startup the app validates their SHA-256 hashes, then creates
an antialiased 192px rounded **in-memory** image for each icon, using a
12px transparent inset and `Qt::KeepAspectRatio` (no cropping or zoom-to-fill).
`image://canopy-dock/<name>` supplies these cached images to QML. If any
source or clipping check fails, approved mode stops before creating the
desktop. No permanent derivative files, shader masks, render timers or
additional background services are introduced. The top-left icon uses a
static, original full-color SVG based on the earlier silhouette contour.

This is **not** visual acceptance: compile and screenshot the actual Qt
application with the original ZIP plus a cleared alpine wallpaper. Run
`--approved-art-dir DIR --landscape-wallpaper FILE --self-test-approved`
at 760×500, 1200×750 and 1920×1080. Review at native resolution. Linux
Mint VM tests and real desktop integration remain separate release gates.

## Dock alignment QA update

The earlier round-corner pass was **not sufficient to accept the visual**:
the 54px images were anchored 2px from the top of 70px buttons, leaving
unequal optical padding inside the 88px dock. It was too easy to confuse
successful PNG decode and corner clipping with good alignment.

The artwork and alpha-clipping logic stay unchanged. The app now centers
all eight QML image rectangles inside their buttons, centers the
hover/focus halo on the same position, and retains the separate active
indicator. In the **compiled Qt runtime** the screenshot self-test explicitly
checks the eight image midpoints against their tile centers, the dock
centerline, spacing, and vertical bounds. Bad alignment must fail CI
rather than being presented to the owner as approved. An aesthetic review
of the actual high-resolution screenshot is still required.

## Terminal icon — isolated visual candidate (not automatically approved)

The latest review narrows the remaining visual problem to **Terminal only**.
Keep Browser, Mail, Files, Calendar, Photos, Music, and Settings as-is and
preserve the SHA-locked original Terminal PNG. An optional candidate may be
loaded *only* for Terminal, after verifying all eight original master hashes:

```sh
./build/classic/canopy-classic-spike \
  --approved-art-dir /path/to/exact/approved-art \
  --landscape-wallpaper /path/to/alpine-landscape.png \
  --terminal-refinement /path/to/Canopy_Terminal_Candidate_Only.png \
  --self-test-approved --self-test-size 1920x1080 \
  --self-test-screenshot /path/to/terminal-real-qt.png
```

The candidate must be a local, square 256–2048px PNG with transparent outer
corners, no symlinks, at most 5 MB. It is *not* the new master icon and is
never loaded by default; the other seven original icons are never touched.
This is a bounded visual comparison, not visual approval or Mint acceptance.
Treat a mismatched, overglossy or off-center Terminal rendering as rejected.

# Classic Qt Quick technology spike

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



This is a **standalone demonstration window**, not a Linux desktop session, window manager, dock replacement, installer, or completed product. The Files dock button now shows or hides the existing demonstration Files window and its active dot follows visibility. The red titlebar control closes the demo Files window; the Files dock reopens it. The yellow and green titlebar dots remain decorative, not minimize/maximize functionality. Inside the focused demo, Ctrl+W closes Files and Ctrl+Shift+F reopens it; these are application-scoped keyboard shortcuts, not global desktop bindings. The automated screenshot smoke test invokes the dock's actual QML click signal, verifies both hide and restore, then captures the original visible scene. Other app tiles remain inert; no app-launch capability is claimed. The Files window is an interactive visual-only composition: sidebar navigation, sample-folder selection and name filtering work on local demonstration data, but no live directory browsing or disk access is implemented. The screenshot self-test rejects a missing, clipped or overlapping preview, verifies the original wallpaper fills the window and that all seven dock icons exist, but is not a human aesthetic review. The original Canopy launcher and the seven dock concepts are visual-only; no app launch or desktop services are implied.

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


## Exact icons + current alpine wallpaper integration

The latest owner-supplied wallpaper reference is a scenic alpine lake,
autumn-tree and snowy-mountain landscape, **not** the historical blue-wave
image. The screenshot reference contains desktop overlays and cannot be
redistributed as a standalone wallpaper. A separately original or properly
licensed photo-quality landscape is still required.

The exact eight selected app-icon PNG masters live in the archived
`Canopy_Classic_Exact_Artwork_Runtime.zip`. Install them without manual ZIP
extraction:

```sh
python tools/install_approved_art_zip.py \
  --archive /absolute/path/to/Canopy_Classic_Exact_Artwork_Runtime.zip \
  --destination /absolute/path/to/approved-art

./build/classic/canopy-classic-spike \
  --approved-art-dir /absolute/path/to/approved-art \
  --landscape-wallpaper /absolute/path/to/licensed-alpine-landscape.png \
  --self-test-approved --self-test-size 1200x750 \
  --self-test-screenshot /absolute/path/to/classic-real-qt.png
```

The ZIP importer verifies hashes, ZIP member safety, the archived manifest,
and atomic extraction. The Qt runtime separately verifies eight exact
icon hashes and the optional landscape file's actual PNG/JPEG format,
dimensions, size and path before creating the scene. Landscape rendering is
static and cached with bounded HiDPI dimensions; no background service or
continuous animation is added.

CI uses a synthetic test PNG only to prove actual Qt decoding and screenshot
behavior, **not** to establish aesthetic approval. The Linux Mint VM and
real-icon/real-landscape screenshots remain mandatory release gates.

## Live top-bar date/time (isolated functional improvement)

The Classic preview top bar now displays the machine's local date **and
time**, rather than a date value frozen at application startup.
`ClockLabel.qml` uses one **single-shot** timer aligned to the next wall-clock
minute. It recalculates and rearms once per minute, stops when hidden, and
refreshes when the Qt application becomes active again after a pause. There
is no second process, per-second polling, animated clock, background daemon,
location request or network call. The value has an accessible text label.

For this bounded prototype, the compiled Qt screenshot self-test changes
the QML clock's date property, verifies the displayed text reacts and fits
inside the top bar, then restores the original time before screenshot capture.
This is a real Qt binding test, **not** a full Linux Mint accessibility or
suspend/resume acceptance test. Source-only invariants are in
`tests/test_classic_clock.py`.

This does not change any approved icon PNG, background, dock tile, source art
hash or wallpaper selection. Visual signoff on the full desktop is still
required.

## On-demand original-icon application catalogue (new draft)

The existing Tux menu now offers **Browse applications**. The standalone
Classic preview also accepts **Ctrl+Space** to toggle a searchable, keyboard-
accessible application overlay and **Escape** to dismiss it. The overlay
reuses the verified original eight icons when approved-art mode is enabled;
the non-approved fallback uses only its original six legacy icons. The existing dock stays visible and unchanged while the modal
search overlays it. The launcher has no authority to hide or alter dock
items. Case-
insensitive filtering, zero-match feedback, focus and keyboard selection are
local QML operations that do not spawn processes, poll or require another
daemon. Opening **Files** only reopens the existing sample Files window; all
other entries clearly disclose that real launching is not connected.

The default closed overlay does not change the user's wallpaper, dock tile
placement, application list or desktop composition. Synthetic source-contract
tests run in `tests/test_classic_launcher.py`. Compiled Qt smoke tests
actually open the overlay, exercise the case-insensitive QML search binding,
verify zero and restored matches, close it, then capture the original
resting desktop at three resolutions. In addition, the real Qt build is run
with `--self-test-launcher-screenshot` at 1200×750, capturing an **open
launcher image** after the Qt frame repaints, alongside the closed desktop.
The workflow validates both PNGs and rejects pixel-identical files. They are
stored in the short-lived `canopy-classic-ui-evidence` GitHub Actions
artifact; they are not AI-generated mockups. These CI images still use
prototype art, **not the user's private approved icon/wallpaper bundle**.

This is an adaptation of the earlier draft launcher prototype (PR #60)
to the reviewed current Classic Qt branch, **not an endorsement of that
earlier prototype's rejected artwork**. Real OS app launch integration is
a different unmerged draft (PR #102); visuals and Mint acceptance are not
approved by this integration.

## Native Linux applications from the searchable launcher (opt-in)

The **searchable application overlay only** now supports requesting an installed
Linux desktop application through GLib/GIO, using the reviewed
`SystemAppLauncher` from draft PR #102. Use:

```sh
./canopy-classic-spike --enable-system-apps
```

**Without that flag**, every launcher category behaves exactly as in the
existing sample: Files opens the demonstration Files view, and other
categories say that real launching is not connected. With the flag, choosing
a known application name in the searchable overlay asks the host-owned GIO
service to launch one of a fixed allowlist of available `.desktop` IDs.
There is no user-supplied `Exec`, shell, URL bridge, external API, background
service, or arbitrary path input. If the system app is unavailable or fails,
Files still opens the sample view and other categories say why they did not
start. The app cannot claim a successful UI launch merely because GIO exists.

The **dock is intentionally and explicitly untouched**: no Qt appearance,
position, hover, size, art provider, clicking behavior or interaction in
`DockTile.qml` or the `canopyDock` section of `Main.qml` was modified.
This isolates launcher functionality from the owner-approved dock. The
original eight source PNG hashes are unchanged, and the experimental
launcher-only optical adjustments remain disabled by default.

### Automated verification

The Qt6 CI build links `gio-unix-2.0`, checks that malformed names and
injection-like category strings are rejected, then installs an isolated
temporary `nemo.desktop` under a disposable `XDG_DATA_HOME` whose `Exec`
only creates a harmless temp marker. It verifies that the **actual GIO**
launch request executes; no real user's browser, mail or other desktop app
is launched in CI. A **second real Qt/Xvfb test** opens the on-screen QML
launcher, calls its same `choose("Files")` action used by mouse or keyboard,
and verifies the disposable `nemo.desktop` runs and the sample Files
window is not accidentally reopened. `tests/test_classic_native_launcher_only.py` guards the
no-dock-change contract and the opt-in behavior. This does **not** prove
Nemo/Firefox/other apps can be visibly opened/focused inside a real Mint
guest; that is a separate release acceptance test.

See original independent GIO implementation PR #102. The work here adapts
it to the current Classic launcher rather than blindly merging the old
PR's **dock** interaction changes.

## Launch this actual Qt build from a Linux application menu

The project's existing stdlib registration utility on \`main\` provides
**non-root, reversible user application menu integration**. Its installed
\`.desktop\` entry points directly to a separately built Canopy Qt binary:

\`\`\`sh
python3 tools/register_classic_preview.py status
python3 tools/register_classic_preview.py install \
  --binary /absolute/path/to/canopy-classic-spike
python3 tools/register_classic_preview.py status
# When done (removes only its exact unmodified managed entry):
python3 tools/register_classic_preview.py uninstall
\`\`\`

Optional \`--approved-art-dir\`, \`--landscape-wallpaper\`,
\`--terminal-refinement\` and \`--enable-system-apps\` are forwarded to
supported builds. Neither the desktop entry nor this utility replaces
Cinnamon, switches sessions, starts a compositor, downloads software, or
installs anything system-wide. The existing \`DockTile.qml\` remains frozen.

\`tools/classic_menu_runtime_smoke.py\` now provides a separate **actual
runtime launch test**. The CI builds the real Qt6 program, registers it
in a disposable temporary \`XDG_DATA_HOME\`, validates the desktop entry,
executes it through \`gio launch\` under a fresh Xvfb display, and requires
both a process running that exact executable inode and a visible X11
Canopy window. The test kills only the newly observed executable process,
verifies ownership and unregisters the temporary menu entry; it never
touches the real user's desktop menu or installed applications. The test
is intentionally run as a normal, non-root user and must not be run
against an interactive working desktop while the user is relying on it.

Ubuntu/Xvfb completion **does not establish** Linux Mint guest support,
real GNOME/Cinnamon menu presentation, auto-login, compositing, an
installable shell/session, accessibility, or owner visual approval.
