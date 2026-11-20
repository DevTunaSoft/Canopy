# Canopy Classic — comparative Linux desktop design study

Status: research/design guidance, not a visual acceptance report or proof that a new shell is functioning. Research refreshed 2026-11-19.

## Purpose
Make Classic unmistakably macOS-inspired **through layout and behavior** while retaining original iconography, wallpaper, visual identity, and legally distributable assets. Keep Linux Mint as the target, preserve the shared Classic/Modern architecture, and optimize beauty and resource use together. Do not transplant other projects' source, artwork, trademarks, names or icon packs without separately verifying licenses and compatibility.

## Reference projects and transferable lessons

| Reference | First-party source | What Canopy should study | Avoid |
| --- | --- | --- | --- |
| elementary OS / Pantheon | https://docs.elementary.io/hig ; https://elementary.io/en/docs/learning-the-basics | Unified panel/dock/application language; consistent spacing, typography, icon silhouette, focus and actionable app controls | Superficial imitation of Pantheon icons; assuming Pantheon architecture directly suits Mint |
| Zorin OS / Zorin Appearance | https://zorin.com/os/ ; https://zorin.com/os/pro/ | Switchable desktop layouts and cohesive presentation presets, applicable to Classic and Modern sharing one core | Treating GNOME-specific extension internals as a drop-in Qt shell solution |
| pearOS | https://pearos-archlinux.github.io/pearOS-documentation/ | Visual familiarity and macOS-like proportions; compare KDE-derived themes to our independent Qt scene | Importing Apple-themed or pearOS imagery/assets, swapping Linux Mint's base |
| Cutefish Desktop | https://cutefish.org/about/ ; https://github.com/cutefishos ; https://github.com/cutefishos/cutefish-toolkit | Dock/component boundaries, rendering approach, toolkit architecture, possible lightweight alternatives | Blind source reuse or claiming new Skia toolkit is compatible with our Qt prototype |
| Budgie / Ubuntu Budgie | https://docs.buddiesofbudgie.org/user/getting-budgie/ ; https://ubuntu.com/desktop/flavors | Configurable panels and desktop workflow; focus on practical resource/feature tradeoffs | Assuming unmeasured performance superiority |

These are research references, NOT verified benchmarks or an endorsement of external licensing.

## Visual design decisions for Classic

1. **Desktop hierarchy:** top edge-to-edge menu bar, restrained app-aware menus at left, truthful dynamic status at right, original Canopy penguin launcher. Floating dock centered at bottom. No permanently painted fake Wi-Fi, battery, or active-app state.
2. **Professional wallpaper:** commission/create original landscape/artwork; color-manage, scale and cache it. Geometry-only rectangles are not premium; full-resolution screenshots must show the real Qt rendering, not concept art. Avoid ongoing repaint loops.
3. **Dock:** 8–12 distinct high-resolution original icons in a representative scene, consistent optical geometry and silhouettes, uniform baseline, app-running indicators tied to actual state. Distinguish preview imagery from working launch targets.
4. **Representative window:** real visual density: titlebar, carefully measured corners, sidebar, toolbar/search, nested content, compact and high-DPI layouts, keyboard focus. Not just pastel rectangles. Follow-up should connect this to an actual Linux application/window management route; do not label preview functionality as real.
5. **Palette and materials:** light first-run; dark equally authored; restrained cool-neutral surfaces, text hierarchy, hairlines, carefully layered static shadows, limited blur only when affordable. Low-resource mode removes *effects*, never visual craft.
6. **Shared architecture:** Classic and Modern presentation layers share app inventory, status providers, settings, notifications and accessibility services. Event-driven updates instead of redundant polling.
7. **Legality:** emulate general interface arrangements and behaviors, but retain original Tux/Canopy mark, wallpapers, icons, text, and controls. Check source and asset licenses before reuse.

## Engineering implementation order

- **P0:** Capture real 1200×750 and 760×500 Qt screenshot artifacts from the current head; review against visual reference, record specific defects. Add 1920×1080 and HiDPI acceptance targets; screenshots are not themselves aesthetic certification.
- **P1:** Replace the four placeholder dock tiles with a cohesive original icon set, better proportions, separators and indicators; prioritize working interactions before claiming app launches. Add source/QML and screenshot geometry regression checks.
- **P2:** Upgrade the preview-window component with a credible toolbar, finder-like navigation density without borrowing proprietary assets, distinctive folders, status feedback, focus/hover states, and a real integration route.
- **P3:** Add proper application/window/status integration incrementally and test in the dedicated Mint VM. A standalone ApplicationWindow is not a replacement desktop shell.
- **P4:** Measure actual cold/warm startup, five-minute idle PSS/CPU, GPU/software rendering and input responsiveness at each performance profile on Mint; no unsupported performance numbers.

## Acceptance gates

- CI: compile Qt, pass source contracts and QML diagnostic smoke tests, produce fresh screenshot evidence on the exact PR head, check window/dock/menu geometry at compact and standard resolutions.
- Human design review: compare composition, hierarchy, icon craftsmanship, density, type, contrast, responsiveness, and visual consistency against reference images. Reject "toy-like" rendering even if CI is green.
- Mint VM: prove session/runtime and interactions independently; preserve immutable evidence and avoid unapproved system/session replacements.
- Promotion: feature branches and draft PRs until verified; never describe screenshots from a different commit as proof of current code.

## Reference-image handling
Use reference screenshots as critical study material only. No screenshots, wallpaper, icon resources, proprietary artwork or other third-party assets should be committed as Canopy product assets without a license review. Reference URLs above are informational links, not an asset reuse grant.
