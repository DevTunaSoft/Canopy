# Canopy roadmap

Status legend: PLANNED / IN PROGRESS / VERIFIED / BLOCKED.

1. **Foundation — VERIFIED for core contracts:** agent rules, architecture, quality budgets and repository CI are present and checked; continued maintenance remains in progress.
2. **Technology spike — IN PROGRESS:** Qt/QML prototype compiled and smoke-tested; GTK/native comparison remains open.
3. **Classic vertical slice — IN PROGRESS:** module-level launch, dock, keyboard and session work is integrated; launchable isolated session and end-to-end acceptance are not yet proven.
4. **Desktop completeness — IN PROGRESS:** bounded workspaces, window interactions, notifications, search and accessibility modules exist; integrated desktop behavior remains to be proven.
5. **Mint deployment — BLOCKED:** installer/recovery modules exist; real Linux Mint guest acceptance, packaging and rollback verification remain mandatory.
6. **Modern presentation — PLANNED:** Windows-inspired adapter over shared services without duplicating core logic.
7. **Distribution — PLANNED:** signed releases, reproducible builds, user guide, support matrix.

No milestone is VERIFIED until implementation and evidence are recorded.

## Integration discipline (issue #132)
Draft PRs are temporary working states. Promote verified PRs to ready-for-review only after their exact SHA passes all required checks and dependencies/conflicts are cleared. Green CI alone never authorizes a merge. Integrate eligible nonvisual work incrementally through the integration branch with regression tests; keep Classic Qt final integration draft until real Mint acceptance and owner visual approval are complete. Maintain at least four concurrently active, isolated engineering subagents plus Hermes; assign another eligible independent task whenever one completes or is blocked. Verify the five-minute watchdog is operational.

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
