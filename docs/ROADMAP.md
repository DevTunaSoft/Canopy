# Canopy roadmap

Status legend: PLANNED / IN PROGRESS / VERIFIED / BLOCKED.

1. **Foundation — IN PROGRESS:** agent rules, architecture, quality budgets, design tokens, repository CI.
2. **Technology spike — PLANNED:** compare Qt/QML and GTK/native compositor integration using a small instrumented prototype.
3. **Classic vertical slice — PLANNED:** launchable isolated session, premium top bar and dock, application launch, keyboard access, original Canopy symbol.
4. **Desktop completeness — PLANNED:** workspaces, window interactions, notifications, search, settings, multi-monitor, power behavior, accessibility.
5. **Mint deployment — PLANNED:** reversible installer/package, safe session selection, upgrade and rollback, real-hardware acceptance.
6. **Modern presentation — PLANNED:** Windows-inspired adapter over shared services without duplicating core logic.
7. **Distribution — PLANNED:** signed releases, reproducible builds, user guide, support matrix.

No milestone is VERIFIED until implementation and evidence are recorded.

## Integration discipline (issue #132)
Draft PRs are temporary working states. Promote verified PRs to ready-for-review only after their exact SHA passes all required checks and dependencies/conflicts are cleared. Green CI alone never authorizes a merge. Integrate eligible nonvisual work incrementally through the integration branch with regression tests; keep Classic Qt final integration draft until real Mint acceptance and owner visual approval are complete. Maintain two isolated, non-overlapping workstreams (integration/QA and feature development) whenever independent work exists.

## Expandable desktop experiences — FOUNDATION

- **FOUNDATION:** versioned Shell Pack manifest, strict read-only checker,
  developer starter and regression tests, isolated from unapproved Classic
  visual history. Documentation and metadata checks do not implement loading.
- **PLANNED:** implement stable host service contracts and an actual
  secure/runtime-approved pack lifecycle.
- **PLANNED:** complete and test Classic; build Modern using shared services;
  prove app-preserving switching or clearly warn when logout is required.
- **PLANNED:** support a **third entirely different presentation** without
  changing the core; test accessibility, modes, rollback and memory cleanup.
- **LATER:** validated separate LacOS Linux Mint-derived distribution with
  measurable optimization, security/update and VM/hardware evidence.

See [Shell Pack architecture](SHELL_PACK_ARCHITECTURE.md) and
[LacOS product vision](LACOS_VISION.md).
