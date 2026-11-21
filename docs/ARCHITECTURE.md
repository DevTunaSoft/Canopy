# Canopy architecture — initial proposal

**Status: design proposal, not an implemented shell.**

## Deployment model
Start as a desktop shell/session on an existing Linux distribution, not as a forked operating system or custom installer. First target: Linux Mint-compatible installation, with packaging decisions validated against real Mint releases. A bootable installer is a later milestone.

## Layers
1. **Session integration:** login/session startup, lifecycle, crash recovery, settings integration.
2. **Desktop services:** app launching, window/workspace integration, notifications, search, accessibility, power and display state; reuse system services where practical.
3. **Shared shell state:** small event-driven state and IPC contracts with bounded queues and versioned interfaces.
4. **Presentation adapters:** Classic (macOS-inspired) first; Modern (Windows-inspired) later, both consuming the same contracts.
5. **Visual system:** original icon assets, typography, spacing, colors, motion, scaling, and focus states.

## Technology decisions to validate
Evaluate Qt 6/QML against GTK 4/libadwaita and native compositor integration with a working prototype. Compare measured idle memory, startup latency, animation frame pacing, accessibility, packaging, and maintenance cost. Do not lock a framework based on aesthetic assumptions alone.

A shell is not automatically a window manager or compositor. Prefer a proven Wayland compositor/session foundation instead of implementing window management from scratch. Document X11 fallback policy after compatibility testing.

## Initial vertical slice
- Launch a test session without replacing the user's normal desktop.
- Show a top bar with an original Canopy menu symbol, clock, and system indicators.
- Show a dock with launch, running-app state, and keyboard access.
- Expose basic theme/scaling settings through one shared state layer.
- Clean shutdown and restart without orphan processes.
- Measure cold start, warm start, idle memory/CPU, and interactions.

## Boundaries
No Apple logos, copied macOS icons, or proprietary assets. Similar interaction patterns may be researched; implement original designs. Avoid background polling, duplicated daemons, and unbounded caches.

## Canopy presentation switching (future goal)

Keep Classic and Modern as independently styled adapters on the same session/window-management integration and shared state. The *goal* is an accessible in-session mode switch, preserving application/window state and per-style customization without reboot, reinstall or parallel desktop daemons. Specify and test ownership transfer, event subscriptions, lifecycle cleanup, memory recovery, crash fallback and recovery to the previous mode. A compositor/session or third-party desktop-environment change may require logout/login; protect user work and clearly distinguish this from the Canopy live-switch target. No seamless switch is currently implemented or verified. See [LacOS vision](LACOS_VISION.md).

## LacOS distribution boundary (later phase)

Canopy first remains a reusable desktop shell/session. **Only after** Mint acceptance and visual/performance signoff, LacOS may be developed as a separate Mint-based distribution consuming the shared Canopy engine with both Classic and Modern experiences. Preserve upstream Mint security/update/hardware compatibility; optimize whole-system resources with before/after measurements and reversible changes. Add functionality without duplicate services or resource-heavy defaults. Maintain the existing Canopy performance, original-artwork, and engineering rules. See [LacOS vision](LACOS_VISION.md).
