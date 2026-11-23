# Canopy Classic — optical balancing candidate (third visual pass)

**Scope:** icon rendering only. Original eight icon PNGs, SHA-256 master manifest, blue-wave test fixture, penguin launcher, QML dock geometry, and nonvisual application code remain unchanged.

## Why this approach

The successful compiled Qt captures in draft PRs #280 and #284 confirm the outer 54px icon slots are **mathematically centered**. The remaining mismatch comes from the *internal illustrations*: bright areas in Mail and Settings sit higher, while Calendar and Music are bottom-heavy. A uniform source crop merely zooms some figures and can clip feet.

Measured from the real 1920×1080 Qt screenshot, relative bright-art centers ranged around 23–29 pixels vertically inside the 54px slots even though each fixed card outline was correctly centered. The earlier 324px crop and 333px source-fit therefore do not yield a consistent result.

## Experiment: gentle non-cropping optical compensation

`--dock-optical-balance-review` is **off by default** and uses *only the eight SHA-locked originals*. Each original PNG is scaled with its entire source visible into a 160px maximum art rectangle inside the **same** fixed 168px rounded alpha mask, with a small per-icon translation (at most 5px in the 192px cached provider). This creates consistent breathing room and compensates for asymmetric content weight without changing the 58×70 QML buttons or 54px art slots.

The new provider renders **one image per icon at startup**, caching eight 192×192 results; no persistent timers, extra threads, effects, shader passes, or repeated image allocations. Terminal's optional separately refined transparent-square candidate stays on its original path.

All preview flags are mutually exclusive: no combination of old and new framing modes can silently change what the owner sees. The default renderer is unchanged, and no original image bytes are touched or uploaded as new masters.

## Review and acceptance

CI captures, using the **same compiled Qt binary**, the untouched baseline plus the 324px, 333px and gentle optical-centering candidates at 1920×1080, 1200×750 and 760×500. Pixel-isolation checks reject all non-dock changes (except the right-hand clock minute rollover); source contract checks fail on altered default rendering or unlocked icon geometries.

The pass condition for this branch is strict: real Qt compile and test evidence, zero unexpected changed pixels, and genuinely more consistent icon appearance on full-size screenshots. If remaining visible issues originate in baked-in original artwork, document them rather than claim pixel isolation is an optical-quality guarantee. No merge to the default branch or final visual signoff is implied by automated tests.

Historical blue-wave wallpaper remains a test fixture. The separate alpine landscape candidate is **not included** in this icon-specific PR.
