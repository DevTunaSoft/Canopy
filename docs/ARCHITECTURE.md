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

## Extensible Shell Host boundary (future)

Presentation modes are **Shell Packs**, with Classic and Modern as initial
examples, not an exhaustive pair. The shared Shell Host owns session
lifecycle, window state, compositor integration, notifications, app discovery,
settings, version/capability compatibility and crash recovery. Individual
packs own original artwork and UI layout, never duplicate a system service
or start a parallel compositor.

The future mode switch should be transactional: validate trusted installed
pack and API, prepare target with bounded memory, transfer presentation
ownership without affecting apps/windows, clean up old resources, and
roll back safely on failure. Compositor/session changes may require explicit
logout/login. No live switch is implemented today.

The first draft metadata format covers Qt/QML `presentation` packs, but
other UI engines may need an independently designed and measured IPC/embedding
adapter. A validated JSON manifest must not be treated as permission to load
untrusted QML. See [Shell Pack design](SHELL_PACK_ARCHITECTURE.md) and the
[LacOS vision](LACOS_VISION.md).
