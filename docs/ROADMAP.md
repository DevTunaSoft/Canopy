# Canopy roadmap

Status legend: PLANNED / IN PROGRESS / VERIFIED / BLOCKED.

1. **Foundation — IN PROGRESS:** agent rules, architecture, quality budgets, design tokens, repository CI.
2. **Technology spike — PLANNED:** compare Qt/QML and GTK/native compositor integration using a small instrumented prototype.
3. **Classic vertical slice — PLANNED:** launchable isolated session, premium top bar and dock, application launch, keyboard access, original Canopy symbol.
4. **Desktop completeness — PLANNED:** workspaces, window interactions, notifications, search, settings, multi-monitor, power behavior, accessibility.
5. **Mint deployment — PLANNED:** reversible installer/package, safe session selection, upgrade and rollback, real-hardware acceptance.
6. **Modern presentation — PLANNED:** premium Windows-familiar adapter over shared services without duplicating core logic.
7. **Distribution — PLANNED:** signed releases, reproducible builds, user guide, support matrix.

No milestone is VERIFIED until implementation and evidence are recorded.

## Cross-cutting goal: desktop freedom — PLANNED

Users must be able to switch **Canopy Classic ↔ Canopy Modern whenever they choose**, not solely during installation, with separate per-mode preferences and one common resource-efficient core. Aim for verified in-session live switching while retaining active apps and windows; use a clearly disclosed safe logout/login fallback when compositor/session boundaries make live switching impossible. No reinstall or reboot to choose a Canopy mode. Never keep duplicated desktop services running. See [LacOS vision](LACOS_VISION.md).

## Open-ended Shell Packs and developer experience — FOUNDATION IN PROGRESS

Classic and Modern are the first **two** presentations, not a hardcoded
limit. Architect the shared Canopy host to discover future versioned,
compatible Shell Packs, with one set of session/window/notification/app
services and **only one active shell**. New shells should be added from a
small manifest + UI starter, not by forking LacOS or changing host services.

- **FOUNDATION IN PROGRESS:** draft manifest v1, offline safe validator,
  example template, invalid-input regression tests and
  [Shell Pack design](SHELL_PACK_ARCHITECTURE.md).
- **PLANNED:** design/review stable typed host APIs and capability negotiation.
  Refactor Classic to become the first real Shell Pack only after the existing
  Classic functionality and visual quality are preserved.
- **PLANNED:** build Modern as the second pack using the *same* host.
  Prove Classic↔Modern transitions and rollback without duplicated services.
- **PLANNED:** load a **third distinct example pack** without modifying
  core code; verify user-controlled selection, accessibility, memory cleanup,
  packaging, updates, session recovery and original art.
- **PLANNED:** signed/audited community pack installation and optional
  discoverability/catalog, with explicit trust controls. Do not run arbitrary
  downloaded code based only on metadata.

No host loader, in-session switcher or third-party support is implemented.

## Future distribution goal: LacOS — PLANNED

**After** Canopy is working, visually approved and tested, create a separate Linux Mint-based LacOS distribution: leaner and more refined than stock Mint while adding meaningful functionality for users migrating from Windows or macOS. Benchmark identical hardware against Mint, preserve updates/security/reliability and rollbacks, and validate both shell modes and repeated switching before release. This is a future goal, **not an existing distribution**. See [LacOS vision](LACOS_VISION.md).
