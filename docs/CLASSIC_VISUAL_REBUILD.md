# Canopy Classic — Visual Rebuild Track

**Gate:** VISUAL_REVIEW_PENDING. **Do not merge as approved UI.**
**Base:** PR #69 is a failed visual direction retained as an engineering fixture.
**First isolated art milestone:** original `Blue Current` wallpaper loaded through Qt's SVG image plugin.

## Why this track exists

Actual 1200×750 and 760×500 Qt renders were rejected on November 20, 2026:
cartoon mountain wallpaper, colored generic-square dock glyphs, sparse toy-like
Files preview, and insufficient desktop coherence. These are not suitable for a
premium, instantly macOS-familiar Linux shell. Passing CI never overrides the
user's explicit visual rejection.

## Reference patterns, not redistributable assets

These public sources serve solely as **visual and interaction comparison
references**. Never copy or trace screenshots, Apple icons, wallpaper imagery,
product marks, proprietary fonts, or application code.

- [Apple desktop, menu bar and Dock guide](https://support.apple.com/guide/mac-help/desktop-menu-bar-and-dock-mchlws12345m2/mac)
  — hierarchy of a full-width top bar, active application menus, center workspace
  and anchored floating Dock.
- [Apple's annotated macOS desktop/Finder guide](https://www.apple.com/business/enterprise/docs/resources/Mac_Employee_Starter_Guide.pdf)
  — high-density Finder window, differentiated side navigation, toolbar actions,
  status controls, application icon scale and window geometry.
- [macOS Tahoe release announcement](https://www.apple.com/newsroom/2025/06/macos-tahoe-26-makes-the-mac-more-capable-productive-and-intelligent-than-ever/)
  — restrained translucent material and depth without flattening controls.

## Agreed design language (Classic)

- Full-bleed original wallpaper with authored gradients/color grading, not
  illustrated mountains or random QML rectangles; light by default.
- Top menu bar visually integrated with wallpaper; original penguin launcher,
  active app identity, contextual menus and only **real** system status.
- A centered Dock with believable material depth and individually composed,
  original multi-size icons; visual size 52–64 px at common desktop scales,
  balanced 8–12 px internal rhythm. No off-brand cartoon square/glyph grid.
- Windows with disciplined titlebar, toolbar, controls, sidebar and content
  density. No marketing labels or dummy system status painted as features.
- Prefer static cached wallpaper/icon rasterization. Effects are optional;
  no permanent blur jobs, animation loops or parallel state-polling daemons.
- Classic and future Modern skins share services, data and launch semantics.

## Blue Current artwork — source manifest

| Asset | Source | License/ownership | Runtime | State |
| --- | --- | --- | --- | --- |
| Blue Current wallpaper | `prototype/classic/assets/wallpapers/blue-current.svg` | Original Canopy-authored curves, gradients, no third-party media | Embedded Qt resource, static SVG image decode via QtSvg image plugin | Candidate, **not yet approved** |
| Original dock icon family (7) | `prototype/classic/assets/icons/*.svg` | Seven independently authored Canopy vectors; no copied Apple artwork | Embedded QtSvg images with per-tile readiness checks | **Candidate, unapproved** |
| Previous dock glyphs | Replaced from `prototype/classic/DockTile.qml` | Old Canvas squares retired | No longer used on the icon candidate branch | **Rejected** |
| Existing folder demo tiles | `prototype/classic/FolderTile.qml` | Original test-fixture primitives | QML | **Rejected as visual design** |

The reference sources above are **not** asset licenses. The new SVG is original
and self-contained; source safety is checked by `tools/check_art_asset.py`.
Use a future asset/license manifest for every additional redistributable
wallpaper, icon or typeface. No Apple-owned visual assets may be imported.

## Runtime requirements and proof

1. Qt 6 build must embed the SVG and install `qt6-svg-plugins` on the test
   runner (Ubuntu 24.04: `libqt6svg6`, which contains `libqsvg.so`). Windows and Linux packaging must include the image-format plugin.
2. Headless runtime must confirm `Image.Ready`; a plain fallback rectangle
   must **fail** the screenshot test instead of passing unnoticed.
3. Capture actual screenshots of the compiled app at 760×500 and 1200×750.
   Review those at native scale. Then repeat at 1920×1080 and 2× DPI in the
   disposable Mint VM. **These are not AI concept screenshots.**
4. Report resource impact separately: initial/warm 5-minute idle PSS, CPU
   percentage and renderer; compare with prior image-backed Canvas technique.
   Do not claim a significant memory saving without measurements.
5. Explicit user approval of actual rendered images is necessary **before**
   advancing another design to production status. A source-quality check or
   GitHub green run is only engineering acceptance.

## Next isolated increments

- Replace generic Dock glyph tiles with an independently designed source SVG
  application icon family, showing original shapes, detailed optical sizing,
  hover/selection and running indicators.
- Bring menu bar and window materials/interaction toward the reference pattern.
  Implement actual actions instead of drawing fake system indicators.
- Integrate with real Cinnamon session and real file manager; standalone
  Qt window demos must not be described as a desktop shell.
