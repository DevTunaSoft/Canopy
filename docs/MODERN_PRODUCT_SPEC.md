# Canopy Modern — product and interaction specification

Status: PROPOSED / planning only. No runtime, mockup or final artwork approval claimed. Builds on [planning charter](MODERN_PLANNING.md).

## Product intent

A premium, Windows-familiar, Linux-native desktop experience without mandatory online accounts, advertising, intrusive effects or duplicated services. Modern is the second presentation of Canopy, not a fork of Classic, a compositor, or a new distribution. It should feel immediately familiar to Windows users while respecting Linux applications, accessibility and user control.

## Visual direction for owner review

Proposed baseline: full-width bottom taskbar, centered app group, left or centered Canopy/Tux application-menu control, right-aligned tray and clock. App menu opens above its button, with search, pinned apps and an all-apps view. System controls and notifications open from the tray; no permanent secondary dock. Use original iconography, a restrained frosted treatment where inexpensive, readable type, coherent corner radii and crisp focus/selected states. Offer opaque fallback and high contrast; never require continuous blur, animated wallpaper or expensive shaders. No copied Windows logos, glyph assets or proprietary fonts. Keep the existing Canopy Classic visual identity untouched.

Draft tokens (not approved): 48 logical-pixel taskbar, 36 logical-pixel icon target with at least 44 logical-pixel hit area where practical, 8-point spacing rhythm, 12-pixel panel radius, 16-pixel overlay radius, system sans-serif font, short optional 120–180 ms transitions. Adapt to DPI, font scaling, available work area and touch needs instead of hardcoding physical pixels. Use semantic theme tokens rather than hardcoded colors; propose a neutral charcoal/ivory palette with Canopy green accent. Treat all values as starting points for actual screenshot review.

### Concept layouts

A: centered premium taskbar; balanced app group and right tray, compact menu with pinned grid and all-apps view. B: traditional left-aligned taskbar and left application menu. Both should share controls and geometry logic; B is a setting, not a separate runtime or mandatory new Shell Pack. Default proposed A; owner chooses after visual review.

## Functional requirements

| ID | Feature | First usable version acceptance |
| --- | --- | --- |
| M01 | Taskbar and app menu | Open/close from keyboard and pointer, stable app IDs, pin/unpin/reorder, accessible state, correct running/active markers; overflow on narrow screens. |
| M02 | Local application discovery/search | Real installed desktop entries from trusted host, no duplicate index, ranked bounded search, launch through existing authorized host, visible failure/empty states. |
| M03 | Window interaction | Focus/minimize/restore native windows via host, stable grouping by app, actual workspace and active-window state; no fake running indicator. |
| M04 | Window snapping and previews | Capability-gated snap positions, keyboard action and screen-aware bounds; previews only while visible with bounded memory and privacy handling; no capture in locked/protected contexts. |
| M05 | Tray and clock | Event-driven real network/audio/power/battery/session state where supported, correct date/time and timezone/resume behavior, unavailable states explicit. |
| M06 | Quick settings and notifications | Host-owned actions and notification source, action outcome visible, safe authorization, no second notification daemon; no fictitious status. |
| M07 | Files | Launch native file manager through trusted shared host; reuse bounded file model only where appropriate. Do not imply full file explorer operations until separately tested. |
| M08 | Personalization | Per-pack taskbar alignment, pins, size, auto-hide, accent and appearance; common wallpaper catalogue and theme preferences where appropriate. Persist atomically; validate and recover corrupt settings. |
| M09 | Display and input | Single/multi-monitor work area, HiDPI, narrow resolution, keyboard-only navigation, pointer, accessible names, screen reader and reduced motion. Do not capture global shortcuts without negotiation. |
| M10 | Performance | Shared five profiles and Auto Mode, feature-level override, transparent resource tradeoffs, on-demand overlays, bounded caches and no duplicate always-on services. |
| M11 | Session and recovery | One compositor/session owner, reversible install/uninstall, crash recovery, lock/logout/re-entry without data loss. |
| M12 | Switching | Trusted compatible Classic/Modern packs switch transactionally, preserve windows/app work, release old subscriptions; clearly warn when logout is required. |

M01–M03, M05–M07, M08 basic settings, M09 and M11 form initial usable Modern. M04 advanced previews and M12 depend on real host support; do not force implementation with unsupported compositor tricks. Full release includes all applicable quality gates. Keep feature flags fail-closed and never count a disabled placeholder as functional.

## Settings and privacy

Shared scope: accessibility preferences, approved wallpaper catalogue, system-control policy, application identity and notification state. Pack scope: pins, order, taskbar placement, alignment, sizes, menu layout and pack visual tokens. Define schema/version and migration before writing; no settings overwrite across packs. No telemetry, external search, web recommendations, ads or mandatory online accounts. Never log sensitive notification text, filenames or window contents unnecessarily.

## Explicit non-goals

No Windows binary compatibility layer bundled by default, no new file manager/compositor/notification daemon solely for Modern, no replacement Linux distribution, no arbitrary third-party executable QML loading, no Windows branding, no unmeasured performance claims, no Classic default changes.

## Visual acceptance matrix

Owner reviews proposed A/B concept, original app menu icon, taskbar states, menu/search, tray/quick controls, notification center, settings, window snap hints and dark/light/high-contrast variants. Later require actual compiled screenshots at 1920x1080, 1200x750, 760x500 and scaled/multi-monitor cases. Inspect optical icon alignment, transparency, accessible focus, clipping, localization and keyboard paths. Concepts are not runtime evidence. Hermes may implement bounded refinements only under the established owner-authorized engineering workflow.
