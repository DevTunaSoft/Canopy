# Canopy Classic — Design System v0.1

Status: design specification, not a shipped or tested desktop.

## Product identity
**Canopy** — *The Familiar Feel. The Freedom of Linux.*

Classic is the first macOS-inspired experience. Modern is a future Windows-inspired experience. Both MUST use the same underlying session, services, settings, accessibility, and app integrations; only presentation patterns differ. Avoid Apple trademarks, copied icons, proprietary assets, or claims of macOS compatibility.

## Visual direction
- Premium, calm, readable: crisp typography, precise spacing, restrained gradients, purposeful depth, harmonious light and dark palettes.
- Dock: centered, bottom-aligned, intelligent hide behavior and active-app indications; never require a polling animation loop.
- Menu bar: thin top strip; Canopy penguin mark at top-left (original art only), active-app menus, system indicators.
- Launcher: optional grid overlay with keyboard search; do not spawn an extra continuously resident service solely for its animation.
- Window surfaces: restrained translucency in small areas (dock, top bar); opaque main application content for clarity and performance.
- Folder/file UI: familiar navigation patterns, but use existing Linux file manager integrations rather than fork file-management internals.
- Original icons: consistent silhouette/optical weight and recognizability. No Apple icon tracing.

## Tokens (proposed)
- Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 px.
- Corner radius: 10 px controls, 16 px panels, 20 px primary windows, 24 px launcher.
- Menu bar height: 32 px. Dock icon baseline: 48 px, scalable 36–64 px.
- Typography: system sans, 13 px body / 12 px metadata / 16 px headers; explicit minimum accessible scaling.
- Light surface: #f6f7fb; ink: #1a2234. Dark surface: #161b2b; light ink: #edf1f9.
- Accent: #5489ec. Contrast: AA minimum for text/UI where applicable; contrast must be measured in implemented themes.
- Shadow: limited low-cost static layer; avoid constantly animating blur radius.
- Motion: 140–220 ms transitions, transform/opacity preferred; respect reduced-motion and disable on constrained GPUs.
- Wallpaper: original artwork licensed for redistribution and offered in static resolution variants.

## Behavioral constraints
- Fully keyboard navigable, semantic focus indicators, readable labels.
- No wallpaper-based controls; UI must remain legible on user-selected backgrounds.
- No animation or telemetry loop when idle.
- Graceful fallback for machines without compositor blur support.
- Do not inject effects into third-party apps; prioritize native styling integration.
- Provide a low-effects mode with the same content/layout affordances.

## Design acceptance
1. Compare prototype screenshots at 1366×768, 1920×1080, 2560×1440, light/dark, 100%/150% scaling.
2. Verify launcher keyboard search, Escape dismissal, dock navigation, focus visibility, and reduced motion.
3. Test on integrated graphics and a 4 GB RAM device, not just a powerful workstation.
4. Record measured idle RSS/PSS, CPU, wakeups and compositor behavior before claiming performance goals are met.
5. Document differences between static mockups and actual Linux behavior.
