# Canopy Classic — premium visual reset (reference-locked)

Status: approved direction from two user-supplied visual mockups, dated 2026-11-19. This is an **implementation target**, not a claim of pixel match or working desktop-session features.

## Visual source priority
- **Mockup 2 (Files desktop):** desktop composition, saturated indigo/purple/blue abstract wallpaper, translucent floating dock, deep dark menu bar, large refined file-browser window with pale lavender surfaces, sidebar, toolbar, distinctive blue folders and appropriate whitespace.
- **Mockup 1 (application launcher):** future centered application-grid overlay, rounded search control, app labels, disciplined icon grid and calm translucent material. This is a separate *launcher* state, not a replacement for the Files window. Do not display both full-scale overlays simultaneously.
- Preserve Canopy's own penguin mark and trademark identity; avoid copying Apple's icons, branded imagery, trade dress artwork or proprietary source. Recreate general layouts and UX with original assets.

## Reference-locked geometry at 1200×750
- Menu bar 34–40px: left penguin + Canopy + File/Edit/View/Go/Window/Help, right real system providers only once implemented; preview clock may be labeled as demo. Top-bar contrast must work on a dark indigo background.
- Desktop fills all available screen area with flowing, smooth cobalt/plum/violet abstract bands, not jagged vector mountains or a collection of disconnected shapes. Original cached wallpaper should remain visually crafted at 760×500, 1200×750 and 1920×1080.
- Files window: approximately 72% of desktop width at standard size, generous visible wallpaper border, softly rounded outer edge, pale-lavender light material, sidebar around 23% of window width, toolbar aligned to content. Accessible dark text and exact visual hierarchy. Compact version may hide lower-priority chrome, not clip content.
- Dock: center bottom, icons consistent optical size, 8 or more distinct high-resolution original icons, material separate from background, reasonable padding and running indicators only for actual state. Icon artwork quality is a blocker; basic flat glyphs do not pass acceptance.
- App launcher (next phase): centered translucent panel, search above 6-column grid on standard screen, sensible compact grid fallback, matching icon system, focus and reduced-motion access.

## Implementation rules
1. Quality comes from typography, icon craft, color harmony, optical alignment and static shadow placement. **No** continuous wallpaper animation, expensive fullscreen live blur, background decoration daemon, or new polling loop.
2. Use static or lazily cached abstract wallpaper illustration; validate full HD memory footprint before choosing raw full-size RGBA caches. Canvas.Image may consume approx. width × height × 4 bytes, before Qt overhead; 1920×1080 is about 7.9 MiB per surface.
3. Dynamic status icons must be bound to providers when implemented; do not pretend a static demo has real Wi-Fi/battery state.
4. UI visuals must not imply fully working file management, app launch or session ownership until wired and verified.
5. One shared theme/asset system for Classic and future Modern. Light/dark are authored variations, not separate daemons.

## Required visual and performance acceptance
- Evidence from *actual compiled Qt* at 760×500, 1200×750, 1920×1080, and high DPI; do not substitute AI concept images for runtime screenshots.
- Manual visual review against both user mockups: silhouette, wallpaper quality, application-window proportion, material, dock spacing, icon sophistication, typography, content density. Reject generic/placeholder-grade work despite passing CI.
- Automated checks for QML diagnostics, screenshot validity, window/dock geometry, basic text clipping, event-driven redraw, and no heavy effects.
- Mint VM: cold/warm startup, 5-minute idle CPU/PSS/wakeups plus graphics mode details, interaction tests and actual desktop integration. Quantitative thresholds must be based on measurement.
- Keep work on draft PRs until CI passes on exact head and human visual acceptance is complete.

## Milestones
- VR-1: original abstract wallpaper, restrained surface theme, screenshot gate (this first increment).
- VR-2: bespoke vector/raster icon family and polished dock with reliable indicators.
- VR-3: refined Files view with real actions via a safe integration layer.
- VR-4: application launcher overlay with keyboard search/grid/focus; hide when Files is foreground by default.
- VR-5: actual Linux Mint session bridge and measured performance/UX.
