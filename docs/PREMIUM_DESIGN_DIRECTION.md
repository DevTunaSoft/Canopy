# Canopy Classic — Premium Desktop Design Direction

**Status: mandatory design brief.** This is the intended quality bar, NOT a claim about the current technology spike.

## Visual rejection and course correction — November 20, 2026

**Decision: the screenshots from PR #69 are rejected as a design direction.**
The source may remain useful as a Qt test fixture, but its visual choices are not
acceptable for Canopy Classic. Do not merge it as the user-facing desktop design
or call it "premium" because it compiles or takes screenshots.

The current evidence at 1200x750 and 760x500 exposes the specific failure:
- The hand-painted angular mountain/lake image reads as low-detail clip art.
  Replace it with a professionally composed **original** full-resolution
  wallpaper asset. Prefer a static prepared image over per-frame effects.
- The seven dock tiles are near-identical rounded squares containing crude
  white glyphs. Commission/design coherent **original** multicolor application
  icon artwork with appropriate geometry, depth, silhouette and optical size.
  Icons must remain legible across 32/48/64/128 px and high DPI. No Apple icons.
- The dock is an opaque rounded white rectangle without believable material
  hierarchy. Redesign its proportions, icon placement, separators, indicator
  geometry, subtle elevation, light/dark materials and the scaling behavior.
  Static fallback materials must still look deliberate when blur is disabled.
- The top bar is visually underpopulated and lacks contextual menu behavior and
  real state-based status affordances. An actual working implementation should
  drive menus and status; do not paint fake controls.
- The fake Files window is a sparse card with simplified colored folders, not
  an authentic polished file experience. Build a realistic representative
  window (toolbar/actions, sidebar hierarchy, content density, selection,
  scroll, resize, keyboard navigation, consistent chrome) and a viable path
  to a **real** Linux file manager. Demo data must remain clearly nonfunctional.
- Current visuals read as a small demo running inside a single application
  window rather than a cohesive **desktop shell**. The end-state design must
  own the real top-bar/dock/window theme integration in a Linux Mint session.

**Design target:** On first glance, a person familiar with macOS should
immediately recognize the desktop's layout, polish and interaction language,
while every brand mark, glyph, wallpaper, icon, font choice and packaged asset
is either original or explicitly licensed for Canopy redistribution. Do not
substitute cartoon artwork, flat pastel tiles or a simplified design just
because they are easier to implement. Do not copy Apple's proprietary assets.

### Visual proof gate — required BEFORE additional polish claims

1. Produce a clearly labeled design reference board comparing representative
   macOS desktop patterns with Canopy's proposed **original** equivalents:
   menu bar, launcher, dock, application iconography, window, wallpaper,
   popovers, typography, spacing, light/dark modes. Record chosen references
   and any rights/license review.
2. Approve one cohesive light-theme desktop composition **before** broad
   component implementation. Then author an equally complete dark appearance.
   The existing unapproved mockups and Qt screenshots are NOT the target.
3. Use authored artwork from a documented asset pipeline (e.g. source SVG
   icons exported to necessary pixel sizes, color-managed wallpaper with
   multiple resolution variants), not low-effort primitive emoji/glyph icons.
   Preserve original source and license manifest, never bundle copied Apple art.
4. Implement a representative *real render-path* scene with an authentic
   desktop-like menu bar, dock, at least one credible interactive window,
   realistic content density and tested keyboard/focus behavior.
5. Capture 760x500, 1200x750, 1920x1080 and a high-DPI Mint VM screenshot;
   review at 100% scale against the approved reference board. Flag plastic
   textures, toy-like icons, blank window regions, misaligned chrome, harsh
   borders, simplistic wallpaper and inconsistent spacing as **visual failures**
   even if functional CI is green.
6. Measure startup, five-minute idle CPU, PSS, frame responsiveness and
   software-rendering fallback. Performance profiles may turn off optional
   visual effects, but **must not** substitute an inferior icon set or layout.
7. Visual acceptance needs a specific recorded human approval on actual
   application screenshots. A green Qt build is an engineering gate, never
   aesthetic approval. Never silently promote this rejected branch's imagery
   as a release design.

### Engineering handoff

Do not throw away Qt build/runtime tests, screenshot infrastructure, regression
logic or VM tools. Separate that infrastructure from the rejected wallpaper and
placeholder visuals. Plan the redesign in a focused design-review branch, then
implement it in bounded, testable commits. Keep #69 draft/rejected while
design work proceeds. No main-branch merge without the visual gate.

## Product identity

Canopy Classic is a genuinely refined, macOS-inspired desktop shell for Linux Mint.
The resemblance should be immediately apparent from desktop structure, proportion,
visual hierarchy and interaction—not from borrowing Apple trademarks, icon packs
or proprietary imagery. The current giant geometric wallpaper, four utility tiles
and bare menu strip are **rejected prototype visuals**, not a low-performance mode
or the intended final skin.

Tagline for documentation and marketing only:
**The Familiar Feel. The Freedom of Linux.** Do not plaster it on the desktop.

## Appearance: default light, user-selectable dark

- Light is the default first-run experience: elegant neutral materials, carefully
  chosen wallpaper, restrained translucency where supported and readable dark text.
- Dark mode must be equally authored, not a palette inversion or the sole design.
- Prefer a beautiful original photographic/illustrated landscape wallpaper with
  controlled visual contrast, or an equally accomplished original artwork. A large
  rotated gradient rectangle alone is not a release-quality wallpaper.
- Design a coherent color/typography/spacing/elevation system that can be applied
  throughout the shell. No arbitrary per-component colors.
- Keep the desktop uncluttered. Desktop identity comes from the menu bar, dock,
  windows and actual working system affordances, not decorative marketing text.

## Essential macOS-inspired desktop language

### Menu bar
- Thin edge-to-edge bar with precise type scale, optical alignment, subtle surface
  depth and separations only where useful.
- Original Canopy penguin mark at left, app identity and contextual menus.
- Right side reserved for genuine status capabilities (clock, audio, network,
  battery where applicable), not fake permanently painted status symbols.
- Desktop and window scaling must preserve alignment, text legibility and
  accessible hit targets.

### Dock
- Real floating dock: proportionally sized, tasteful material, deliberate
  padding, coherent high-resolution original app artwork, subtle active-app dots.
- Distinguish pinned applications, currently running applications and system
  tools. Do not falsely imply that inert demo buttons launch apps.
- Treat dock icons as first-class brand assets, not monochrome text glyphs or
  four identical generic pastel tiles.
- Hover/motion must be optional, modest and low-cost; no permanent animation loop.

### Windows, surfaces, file experience
- Actual window chrome, controls, shadows, corners, resizing and focus states
  must be designed together and tested with a representative real application.
- Design a cohesive file-manager theme or extension path that respects native
  Linux application behavior; no claim of global window theming from a Qt demo.
- Menus, popovers, selection states, dialogs, sliders, scrollbars and notifications
  need authored components and accessibility coverage.
- Plan for Classic and future Modern skins sharing underlying services.

## Performance must not cheapen quality

- All performance profiles share the same visual identity and assets. Lower tiers
  reduce optional blur, dynamic shadows or motion, **not visual care, spacing,
  coherent iconography or typography**.
- Default to static cached assets, GPU-friendly drawing and idle-zero animations.
  Measure idle PSS/CPU/GPU; document effects before enabling them.
- Do not create a background daemon merely to draw decoration.
- No unverified statements such as "macOS quality" based on a successful CI run.

## Required proof for design sign-off

1. Real application screenshots at 1200×750, 760×500, 1920×1080 and high DPI,
   captured from the actual rendering path rather than AI concept art.
2. Design review against a representative macOS reference: composition,
   alignment, contrast, density, icon craft, material and interaction feedback.
   References are visual guidance, not sources for copyrighted artwork.
3. A representative interactive desktop scene: menu bar, populated dock,
   working controls and a themed application window. A blank desktop cannot
   demonstrate window-system or application quality.
4. Accessibility: keyboard focus, contrast, scaling, reduced motion and usable
   hit targets.
5. Repeatable performance evidence for this design, plus Mint VM measurements.
6. Reviewer explicitly accepts the visual result. CI is necessary but never
   sufficient for premium design acceptance.

## Immediate remediation

- Do not promote the existing visual treatment as a completed skin.
- Replace placeholder artwork with an original art direction and asset pipeline.
- Build a representative, interactive desktop composition with a real window.
- Inspect resulting screenshots and iterate until visual acceptance; then expand
  the design system to remaining components.
- Preserve regression tests and keep PRs draft until runtime and visual gates pass.
