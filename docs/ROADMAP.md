# Canopy roadmap

Status legend: PLANNED / IN PROGRESS / VERIFIED / BLOCKED.

## ACTIVE GOAL — Rev3 controlling directive (2026-11-28)

Sole controlling Canopy/LacOS goal: `C:/Users/X1/Downloads/Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md`, SHA-256 `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a` (short `1fba4b1e`). Workforce: project-scoped cap 8+Hermes (at most 8 Canopy/LacOS subagents plus Hermes, active project workers only); **no-global-change** — other projects and global Hermes settings are excluded and unchanged. **A0.1 finish-current-work protection:** let current assignments finish on their authorized branches/worktrees; never interrupt, cancel, restart, reassign or change branch merely to apply a directive, integration priority or cap; checkpoint, never mark complete. Integration authority: integration/main protection requires **1 distinct human approving review with `enforce_admins=true`** while only `DevTunaSoft` authors eligible PRs — a genuine external blocker; never self-approve or bypass protection; promote eligible PRs to ready, record the exact owner action and continue unrelated work. Guest ownership: **exclusive guest lease** with owner, heartbeat and recovery checkpoint for interactive VM/install/uninstall/display/suspend-resume/restart; serialize heavy builds, suites and VM work; timeouts are incomplete, not passes. This reconciliation PR is DRAFT: no merge, no self-approval.

## ACTIVE GOAL — 2026-11-26 supplemental directive
> SUPERSEDED_POINT_IN_TIME: this 2026-11-26 goal, its 12/10-agent ceiling and its external-directive SHA are retained as point-in-time history for cap, draft-only and integration-authority wording; Rev3 (`1fba4b1e`) above governs. Not retracted, not erased; security, visual, hold and release gates still bind.

Finish one installable, functional, secure, stable, premium, resource-efficient Linux Mint Classic desktop. Hermes has owner-granted GUI engineering authority; approved assets, wallpaper, geometry, colours and typography remain frozen with current status `AWAITING_OWNER_VISUAL_APPROVAL`. Workforce ceiling: up to 12 engineering subagents plus Hermes when productive non-overlapping work exists (newer owner directive, 2026-11-26; it supersedes the 10-agent ceiling in the external directive cited below, while all other wording and acceptance gates there remain in force); throttle heavy operations to protect orchestrator stability. Priorities: security/stability/data integrity; real Mint functionality; integration of existing components; installation/startup/recovery; premium GUI; low resources; independent verification; release documentation. No main merge or final release without explicit owner authorization. Authoritative directive (external, **NOT in the repository tree**): composer-pasted source at `private-evidence/scratch/canopy_master_supplemental_directive_20261126.md`, SHA-256 `f3ec49fba9317c01354dbd34cf1c5cfedb2625b604f25117c720ae0f44781eae` (recomputed from on-disk bytes); the bare filename is `MISSING` at exact tip `20fb694f2b4a0ea44e2f3032f316ac8c7e65a23a` (`git cat-file -e` fails in this isolated worktree) and was previously recorded `MISSING` at archived tip `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` per `private-evidence/scratch/final_git_tree_provenance_84684a0.json`.

1. **Foundation — VERIFIED for core contracts:** agent rules, architecture, quality budgets and repository CI are present and checked; continued maintenance remains in progress.
2. **Technology spike — IN PROGRESS:** Qt/QML prototype compiled and smoke-tested; GTK/native comparison remains open.
3. **Classic vertical slice — IN PROGRESS:** module-level launch, dock, keyboard and session work is integrated; launchable isolated session and end-to-end acceptance are not yet proven.
4. **Desktop completeness — IN PROGRESS:** bounded workspaces, window interactions, notifications, search and accessibility modules exist; integrated desktop behavior remains to be proven.
5. **Mint deployment — BLOCKED:** installer/recovery modules exist; real Linux Mint guest acceptance, packaging and rollback verification remain mandatory.
6. **Modern presentation — PLANNED:** Windows-inspired adapter over shared services without duplicating core logic.
7. **Distribution — PLANNED:** signed releases, reproducible builds, user guide, support matrix.

No milestone is VERIFIED until implementation and evidence are recorded.

## Governing workstreams

Work is selected from `docs/PRODUCT_COMPLETION_MATRIX.md` by dependency and product impact, not by module count:

- **A — Real desktop functionality:** connect existing launchers, dock, window, workspace, files, settings, notification, session and accessibility contracts to the compiled Qt runtime.
- **B — Linux Mint and system integration:** reversible session registration, compositor interoperability, install/uninstall, lifecycle, suspend/resume, display changes and recovery in isolated VMs.
- **C — Performance and resource efficiency:** profile the actual desktop first; reduce shell-owned PSS, CPU, GPU proxy, wakeups, disk I/O, startup latency and leaks with measured evidence.
- **D — Integration and quality assurance:** reproducible Classic builds, compiled-runtime tests, real Mint evidence, security/accessibility validation, independent review and regression prevention.

Standalone security and reliability defects remain eligible, but increasingly granular synthetic validators do not displace core integration work.

## Integration discipline (issue #132)
Draft PRs are temporary working states. Promote verified PRs to ready-for-review only after their exact SHA passes all required checks and dependencies/conflicts are cleared. Green CI alone never authorizes a merge. Integrate eligible nonvisual work incrementally through the integration branch with regression tests; keep Classic Qt final integration draft until real Mint acceptance and owner visual approval are complete. `SUPERSEDED_POINT_IN_TIME`: maintain at most eight project-scoped Canopy/LacOS subagents plus Hermes under Rev3 cap 8+Hermes; under A0.1 let current assignments finish on their authorized branches and do not reassign merely to fill a slot. Verify the five-minute watchdog is operational.

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
