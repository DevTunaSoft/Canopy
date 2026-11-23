# Canopy Classic — optical balancing candidate (third visual pass)

**Scope:** icon rendering only. Original eight icon PNGs, SHA-256 master manifest, blue-wave test fixture, penguin launcher, QML dock geometry, and nonvisual application code remain unchanged.

## Why this approach

The successful compiled Qt captures in draft PRs #280 and #284 confirm the outer 54px icon slots are **mathematically centered**. The remaining mismatch comes from the *internal illustrations*: bright areas in Mail and Settings sit higher, while Calendar and Music are bottom-heavy. A uniform source crop merely zooms some figures and can clip feet.

Measured from the real 1920×1080 Qt screenshot, relative bright-art centers ranged around 23–29 pixels vertically inside the 54px slots even though each fixed card outline was correctly centered. The earlier 324px crop and 333px source-fit therefore do not yield a consistent result.

## Experiment: gentle non-cropping optical compensation

**The optically balanced renderer is selected by default when the eight exact approved PNGs are loaded.** The opt-in `--dock-optical-balance-review` remains as reproducible reference, while `--dock-original-fit` restores the old renderer on demand. Both use *only the immutable SHA-locked originals*. Each original PNG is scaled with its entire source visible into a 160px maximum art rectangle inside the **same** fixed 168px rounded alpha mask, with a small per-icon translation (at most 5px in the 192px cached provider). This creates consistent breathing room and compensates for asymmetric content weight without changing the 58×70 QML buttons or 54px art slots.

The new provider renders **one image per icon at startup**, caching eight 192×192 results; no persistent timers, extra threads, effects, shader passes, or repeated image allocations. Terminal's optional separately refined transparent-square candidate stays on its original path.

Dock preview modes remain mutually exclusive, and the `--dock-original-fit` rollback cannot be combined with another dock preview flag. The launcher-only review mode is independent. The approved-art **in-memory rendered appearance** is the only selected default change; no original image bytes, manifests, QML geometry, wallpaper or other source artwork were changed.

## Review and acceptance

CI captures, using the **same compiled Qt binary**, the untouched baseline plus the 324px, 333px and gentle optical-centering candidates at 1920×1080, 1200×750 and 760×500. Pixel-isolation checks reject all non-dock changes (except the right-hand clock minute rollover); source contract checks fail on altered default rendering or unlocked icon geometries.

The successful real Qt captures show horizontal bright-art center spread reduced **1.09px → 0.73px (33%)** and vertical spread **1.87px → 1.17px (37%)** at 1920×1080. A new pure-stdlib CI quality gate requires improvement on both axes at all three sizes and verifies that a normal approved-art Qt launch renders the chosen default exactly like the explicit optical-mode preview (other than the minute-changing clock). This mechanical improvement is **not** proof of perfection: different baked-in highlight bands and icon illustrations cannot be entirely normalized without redesigning the source artwork. Default-mode CI must pass before any integration; no unverified visual merge is authorized.

Historical blue-wave wallpaper remains a test fixture. The separate alpine landscape candidate is **not included** in this icon-specific PR.
