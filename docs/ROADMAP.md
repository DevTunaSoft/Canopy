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

## Future distribution goal: LacOS — PLANNED

**After** Canopy is working, visually approved and tested, create a separate Linux Mint-based LacOS distribution: leaner and more refined than stock Mint while adding meaningful functionality for users migrating from Windows or macOS. Benchmark identical hardware against Mint, preserve updates/security/reliability and rollbacks, and validate both shell modes and repeated switching before release. This is a future goal, **not an existing distribution**. See [LacOS vision](LACOS_VISION.md).
