# Canopy engineering decisions and open decisions

## Chronology and rationale

### Product definition (agreed)
Canopy is a Linux desktop shell, not a separate OS/distro. Start with Linux Mint and preserve Cinnamon as fallback; provide familiar macOS workflow first. A future Windows-inspired layout must share core services, settings, performance engine and platform integrations.

### Name and brand (agreed)
Canopy, official tagline **The Familiar Feel. The Freedom of Linux.** Earlier tagline candidates were retired and must not be mistaken for the current tagline. Visual direction: premium green canopy/C-leaf identity with original white Tux-inspired upper-left menu artwork. Do not distribute copyrighted Apple/Microsoft icons or claim existing generated concepts are finished printable vectors.

### Safety and privilege (agreed)
Run shell unprivileged. Ask for administrator authorization only when needed using established polkit/system services. No stored admin passwords and no pervasive root daemon. Preserve working Cinnamon login and safe uninstall before full session ambitions.

### Performance (agreed)
Five profiles: Ultra Lite, Efficient, Balanced, Enhanced, Ultimate. Auto Mode and per-feature Auto/On/Off. Overrides take precedence over cosmetic optimizer within safety, accessibility and compatibility limits. No unmeasured performance promises.

### Implementation architecture (provisional)
ADR-001 chooses Python standard library for configuration model, not final application language. ADR-002 chooses GTK3 as a safe **preview**, not as the final toolkit or window manager. Both need further measurements and platform tests.

## Outstanding decisions that require ADRs and tests
- Best long-term integration path: Cinnamon-based extensions/applets vs distinct desktop session/compositor vs alternative toolkit. Compare total resource impact and Linux Mint support; preserve Cinnamon fallback.
- Wayland/X11/XWayland support and realistic global-menu constraints.
- Target Mint releases, Ubuntu bases, desktop libraries, packaging/installation and graphics hardware test matrix.
- UI language/toolkit, animation strategy, app search/indexing, dock and top-bar architecture.
- Repo software license and license compatibility of all third-party code, Tux assets and icon pack.
- Settings schema migration, backup, settings locking/concurrent updates, performance telemetry and thresholds.
- Accessibility, localization, screen reader support and first-run migration experience.
- Repo owner transition from DevTunaSoft to planned BulldogSoft after organization is established; no immediate transfer required.
- Ponytail plugin/skill integration after reviewing original repository, preserving AGENTS.md and other agent configurations.

## Decision record template
Date, context, alternatives, evidence/tests, choice, consequences, compatibility/recovery implications, rollback, affected requirements and follow-up work. Never erase rejected alternatives or previous decision history; mark superseded.

### Session integration evaluation (proposed, 2026-11-18)

[ADR-003](ADR-003-SESSION-CANDIDATES.md) compares Cinnamon extension integration, an independent compositor, and a Labwc-backed session. Trial Cinnamon first in a disposable target session. The shipping compositor and toolkit remain open pending accessibility, recovery, compatibility and performance evidence.

### Classic dock pin persistence (provisional, 2026-11-18)

Use versioned layout-specific pins within the shared preferences model, with the existing Gio desktop entry IDs and a bounded GTK dock view. Preserve version 1 settings on load, retain unavailable pins until explicitly removed, and serialize Canopy writers through an advisory lock. This supports a reversible user-level preview without committing to a production Cinnamon applet or compositor. See [ADR-001](ADR-001-SETTINGS.md). Mint integration and backup design remain open.
