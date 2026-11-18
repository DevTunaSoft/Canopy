# Canopy architecture — initial engineering plan

**Current implementation status:** No runnable Linux desktop shell has been verified. The initial prototype is a static browser-based design reference, not a Linux session.

## Scope and delivery strategy
First deliver Classic, a macOS-inspired experience on Linux. Keep a shared core compatible with later Modern (Windows-inspired) UI. Use mature desktop components instead of developing a new compositor, window manager, login manager, or file-manager backend in v1.

### Proposed layers
1. Linux distribution base / package management (initially target Linux Mint, verify feasibility of selected desktop stack before committing to installer).
2. Desktop session/compositor: select after comparative testing (KDE Plasma/Qt is a candidate, not a finalized mandate). Prefer upstream-supported settings APIs, theming, widgets, and global shortcuts.
3. Shared Canopy services: configuration, theme and wallpaper, accessibility, application discovery, desktop launch integration.
4. Presentation profiles: `classic` (first) and `modern` (future); implement separate layouts configured against shared service interfaces.
5. Distribution integration: packaging, installer/ISO integration, rollback path, licensing attribution.

## Non-negotiables
- Clean, modular code and low memory footprint. No duplicates of services already provided by the desktop.
- Preserve user configuration across updates; keep defaults reversible.
- Avoid polling; use event-driven change notification.
- No network dependency for desktop startup.
- All packaged artwork/fonts/icons must have redistribution rights.
- Shell and compositor crash recovery must not delete user state.
- Support high-DPI, keyboard-only interaction and screen-reader accessibility in chosen toolkit.
- Follow feature-branch + review + tests + verified-green commits/merges workflow. Do not merge on unverified test claims.

## Candidate architectural decision to validate
KDE Plasma is a practical benchmark for compositing, launcher, dock and desktop integrations; Cinnamon, lightweight Qt and other options remain comparison candidates. Measure before choosing a base. Avoid simultaneously shipping a full alternate compositor or double desktop shells.

## Proposed milestone order
- M0 (this PR): architecture/design/performance acceptance contract and browser reference prototype.
- M1: working Classic session proof of concept on a pinned Linux image, with real screenshots and measured idle performance.
- M2: dock/menu/launcher integration and safe reversible installation.
- M3: polished file manager/theme/icons, keyboard and accessibility regression suite.
- M4: reproducible installer image and low-end hardware acceptance.
- M5: Modern layout as a distinct presentation profile backed by shared services.

## Open decisions
Supported Mint edition/release, chosen compositor/toolkit, global menu behavior for GTK/Qt applications, installer strategy, original artwork pipeline, required hardware test devices. These are decisions requiring evidence, not assumptions.
