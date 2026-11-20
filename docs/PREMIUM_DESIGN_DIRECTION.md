# Canopy Classic — Premium Desktop Design Direction

**Status: mandatory design brief.** This is the intended quality bar, NOT a claim about the current technology spike.

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
