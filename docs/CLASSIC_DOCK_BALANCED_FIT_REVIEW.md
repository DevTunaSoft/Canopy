# Canopy Classic — full-height dock artwork candidate (visual-only review)

**Unapproved. Default OFF. No merge authorized.** This is a second conservative alternative to the [prior inner-art preview #280](https://github.com/DevTunaSoft/Canopy/pull/280), following [visual issue #85](https://github.com/DevTunaSoft/Canopy/issues/85).

## Problem seen in compiled Qt screenshots

The earlier `--dock-inner-framing-review` used square 324×324 crops from opaque 345×333/334 user-approved PNG source sheets. That enlarged illustration detail (roughly 2.8% relative to a 333×333 sampling window), which risks crowded visuals and losing portions of the penguins near the bottom. The original masters have inconsistent horizontal dark gutters. Neither the original nor the 324px preview achieved an owner-approved, uniformly balanced icon set.

## Candidate C: preserve the complete original height

New opt-in `--dock-balanced-fit-review` samples exactly 333px vertically, centered in each 333/334px original source. This **preserves the entire source height** and only trims the side gutters to form a centered 333×333 square. Per-icon horizontal sample centers reuse the existing audited source-art measurements. Drawn into the same fixed cached 168px rounded rectangle, inside the unchanged 54px QML image slot. The separately proposed Terminal-v3 transparent source is excluded from re-framing.

- All eight on-disk original PNG bytes, SHA-256 values and manifest stay untouched.
- Default without any review flag is identical to the base PR renderer.
- The previous `--dock-inner-framing-review` remains available independently; the two flags cannot be combined.
- No dock geometry, QML, wallpaper, launcher, hover state or active-dot changes.
- No new services, timers, shaders, frame animations or recurring allocations.

## Real Qt evidence required

The draft branch's CI builds one Qt6 binary and captures three variants using the same original approved icons, software renderer and resolution: unchanged default `classic-SIZE.png`, prior `dock-inner-review-SIZE.png`, and new `dock-balanced-fit-SIZE.png`. Each variant is captured at 1920×1080, 1200×750, and 760×500. Independent pixel-diff reports verify every changed pixel is inside an icon image rectangle (except the known right top-bar clock rollover), and that every icon genuinely uses the candidate rendering.

Automatic geometry checks and green CI **do not prove optical perfection** or replace review of the actual screenshot at 1× display size. Compare the three versions side-by-side, paying particular attention to Calendar/Settings/Terminal outer card silhouettes and Browser/Files/Music Tux artwork extending toward the lower edge. If this candidate still does not look correct, reject it; do not silently rewrite masters or claim complete visuals.

The historic blue-wave wallpaper is a reproducible test fixture only. A separate unapproved alpine/autumn candidate is available but has not been integrated in this branch.
