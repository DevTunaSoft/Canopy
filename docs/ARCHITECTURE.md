# Canopy architecture — native Plasma 6 direction

**Status: implemented Qt/QML prototype and growing shared module foundation; Classic product integration in progress. This is not a completed desktop session.** See `docs/PRODUCT_COMPLETION_MATRIX.md` for verified runtime maturity.

## Engineering governance
Follow [PLASMA6_PIVOT.md](PLASMA6_PIVOT.md), [AGENTS.md](../AGENTS.md) and [QUALITY.md](QUALITY.md) for the latest owner-approved transition, host-safe workforce, protected main integration and release gates. Named holds remain. Finish existing assignments before reassigning agents; preserve the legacy baseline. This document describes architecture, not acceptance evidence.

## Deployment model
Start as a desktop shell/session on an existing Linux distribution, not as a forked operating system or custom installer. First target: a native Plasma 6 extension and presentation stack on the Kubuntu LTS reference guest. Preserve Mint as a legacy baseline. KDE neon is an additional compatibility lane. LacOS is a later, separately tested immutable distribution with a read-only core, signed atomic deployments and rootless multi-package app environments; see [LACOS_IMMUTABLE_ARCHITECTURE.md](LACOS_IMMUTABLE_ARCHITECTURE.md).

## Layers
1. **Session integration:** login/session startup, lifecycle, crash recovery, settings integration.
2. **Desktop services:** app launching, window/workspace integration, notifications, search, accessibility, power and display state; reuse system services where practical.
3. **Shared shell state:** small event-driven state and IPC contracts with bounded queues and versioned interfaces.
4. **Presentation adapters:** Classic (macOS-inspired) first; Modern (Windows-familiar, Zorin-inspired) later, both consuming the same contracts.
5. **Visual system:** original icon assets, typography, spacing, colors, motion, scaling, and focus states.

## Technology decisions to validate
Use Qt 6/QML, KDE Frameworks 6, Plasma 6 native extension points and KWin; reuse mature upstream services rather than duplicating them. Compare measured idle memory, startup latency, animation frame pacing, accessibility, packaging, and maintenance cost. Do not lock a framework based on aesthetic assumptions alone.

KWin owns the compositor and window management. Canopy integrates native Plasma panels, containments, widgets and service adapters, not a standalone preview layered over a complete competing desktop. Document X11 fallback policy after compatibility testing.

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
examples, not an exhaustive pair. The shared Shell Host coordinates presentation lifecycle, settings, version/capability compatibility and recovery through existing Plasma/KWin window, session, notification and app discovery services; do not duplicate those owners. Individual
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
