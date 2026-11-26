# Canopy Modern — engineering dossier and Hermes transition plan

Status: PLANNING ONLY. Initial source audit pinned to Classic integration commit 16569c46876013e6e47c29452a2ab36fa82f1cc8. No coding, tests, benchmarks, visual approval or Mint acceptance performed for Modern. The [product specification](MODERN_PRODUCT_SPEC.md) is proposed, not a release claim.

## Governing constraints

Classic stays the active priority; do not divert its workforce, modify approved artwork, change its default shell or merge to main. Read [engineering contract](../AGENTS.md), [quality gates](QUALITY.md), [Shell Pack architecture](SHELL_PACK_ARCHITECTURE.md), [LacOS vision](LACOS_VISION.md) and [Classic completion matrix](PRODUCT_COMPLETION_MATRIX.md). Modern is a presentation on a shared host, not a separate desktop engine. Reuse actual validated functionality, not merely tests or names.

## Source-grounded reuse inventory (initial baseline, re-audit before implementation)

| Component | Existing candidate | Gap / decision |
| --- | --- | --- |
| Native app launching | [SystemAppLauncher.h](../prototype/classic/SystemAppLauncher.h) | Named dock-label GIO bridge, not general desktop-ID launching. Generalize only through reviewed host capability; verify actual GIO-enabled Mint launch. |
| Launcher search/catalog | [LauncherModel.h](../prototype/classic/LauncherModel.h) | Bounded Qt search and catalogue model; catalogue runtime injection not proven by the model. Avoid second index and redundant QML filtering; verify real host feed and safe app ID dispatch. |
| Window activation | [WindowActivationState.h](../prototype/classic/WindowActivationState.h) | Validated snapshot and intent resolver; does not observe/focus windows. Generalize away from Classic labels only after real backend is proven. Review Q_INVOKABLE mutation boundary; pack code must not manufacture trusted snapshots. |
| File navigation | [FileModel.h](../prototype/classic/FileModel.h) | Home-scoped bounded 500-entry QAbstractListModel, synchronous navigation, no full file-operation engine. Reuse native file manager launch first; profile before generalizing. |
| Qt shell wiring | [main.cpp](../prototype/classic/main.cpp), [CMakeLists.txt](../prototype/classic/CMakeLists.txt) | C++17/Qt6 Quick/QML prototype, context properties and providers. Build defines GIO when detected, otherwise disabled fallback. Classic-specific bootstrap/artwork must not become a permanent host API. Do not copy main.cpp to create Modern. |
| Presentation lifecycle | [shell_host.py](../canopy_core/shell_host.py) | In-memory trusted presenter lifecycle and capability reports, not real Qt/session switch. Implement runtime ownership and rollback only after dependency gate. |
| Installer recovery | [install_recovery_plan.py](../canopy_features/mint/install_recovery_plan.py) | Bounded user-level dry-run planner and verifier; do not claim executed native installation/rollback. Reuse ownership rules. |
| Controls, notifications, preferences, workspaces | [Classic completion matrix](PRODUCT_COMPLETION_MATRIX.md) | Existing contracts and scoped compiled wiring; native status, notification source, workspace actuation and durable shared settings remain gates. Recheck live source before claiming reusable service. |

The pinned CMake target lists Classic presentation QML and selected host adapters; it does not establish a Modern target or public runtime pack API. Some header comments and status docs may lag merged code. Inspect actual build graph, bootstrap registrations, live branch and runtime evidence rather than trusting stale comments. Proposed extraction must be small, dependency-driven and independently regression-tested against Classic.

## Target architecture (proposal)

One session/compositor integration -> one shared host -> versioned typed capability interface -> one active presentation (Classic or Modern or later pack). Shared host owns native app discovery and launch, real window/session state, settings, notifications, system actions, permissions, lifecycle and recovery. Presentation owns taskbar/menu/visual layout and pack-specific settings. Do not create a second daemon or compositor. Inactive packs unload UI and remove subscriptions; limited candidate preparation permitted only for transactional switch with bounded resources.

Treat host-provided identity, sequence, capabilities and mutation requests as separate trust boundaries. Deny unknown version/capability, stale/malformed snapshots, forged origin, unsafe paths and unauthorized actions. Host owns privilege mediation. No pack-supplied shell commands or raw D-Bus permissions; no untrusted QML execution based on metadata. No network service required for local switching. Review provenance, signing, isolation and upgrade compatibility before third-party packs.

## Dependency-ordered implementation backlog

| ID | Work item | Depends on | Exit evidence |
| --- | --- | --- | --- |
| D00 | Refresh branch from then-current verified Classic integration, capture SHA, inspect current open work and docs | Classic functional/Mint gates + owner start authorization | clean ancestry, no overwritten planning commits, recorded reuse audit |
| D01 | Freeze approved Modern visual direction and acceptance matrix | owner visual concept review | approved A/B layout, tokens, assets provenance |
| D02 | Audit/extract minimal host-facing contracts and pack-scoped preference schema | D00 | Classic regression green; typed read/action boundary, explicit capability errors |
| D03 | Modern Qt presentation vertical slice and original launcher identity | D01,D02 | compiled taskbar/menu/tray, exact-SHA screenshots; no duplicate services |
| D04 | Connect real app catalogue, search, pins and launch | D02,D03, native app bridge | real Mint app launch, pin/reorder/restart, empty/failure cases |
| D05 | Native window/taskbar/workspace state, focus, minimize, restore | D04, verified compositor adapter | actual app/window state and failure tests |
| D06 | Settings, wallpaper catalogue, quick controls, notification integration | D02,D03, verified host services | native data and action tests; persistence and privacy |
| D07 | Snap layouts, bounded previews, taskbar auto-hide and multi-monitor | D05,D06 | real WM capability, DPI/work area, lock/privacy checks |
| D08 | Accessibility, themes and profile adaptation | D03-D07 | keyboard/screen-reader, contrast, scale, reduced-motion and profile evidence |
| D09 | Pack lifecycle and transactional Classic/Modern switch | D02-D08, compatible session | running apps survive, old presenter disposed, failure rollback and fallback |
| D10 | Reversible installation/upgrade/uninstall, recovery, performance | D03-D09 | native Mint session and package evidence, PSS/CPU/GPU, failure recovery |
| D11 | Independent QA, owner acceptance and release dossier | all applicable prior gates | no unresolved P0, exact SHA reports, explicit release authorization |

Independent tasks can overlap after prerequisites without owning the same files. Do not treat a plan or fixture as runtime completion. Defer a feature only with explicit reason, affected scope and evidence; unsupported functionality must disclose unavailable state.

## Proposed budgets and benchmarking

Inherit current quality gate targets: <=200 MiB shell-owned incremental idle PSS and <=1% average shell-owned CPU over five minutes on the reference machine, with compositor/existing-service exclusions reported. Aspirational stretch: below 100 MiB and 0.1% of one core where feasible; not verified targets achieved. Compare Classic and Modern on identical Mint hardware, workload, session, compositor, resolution, profile and instrumentation. Include total system PSS where practical, GPU activity, wakeups, cold/warm start, frame times, battery/power where applicable and repeated switching memory growth. Measure before/after; no assumed savings or percent promises. No background polling, mandatory effects or duplicate resident service. Prefer signals, lazy overlays, bounded image caches and no inactive-pack timers. Do not sacrifice stability, privacy or accessibility for marginal savings.

## Acceptance checklist

- Build, exact source SHA and actual Qt screenshots at approved resolutions, light/dark/high contrast and scaling; owner visual acceptance separate.
- Actual Mint application launch, window focus, minimize/restore, workspace and snap actions; explicit unsupported behavior.
- Native system controls, notification and settings interactions, persistence through restart, rejection of unsafe input.
- Keyboard-only, focus return, accessibility names, screen reader where supported, reduced motion; narrow and multi-display behavior.
- Crash/service failure, lock/unlock, logout/re-entry, suspend/resume, display hot-plug, install/uninstall/upgrade rollback.
- At least 50 proposed repeated compatible switch cycles for stress coverage (adjust with evidence); preserve unsaved application work, release old UI/subscriptions, recover after injected failures. Incompatible compositor/session requires warned logout/login, not fake live switch.
- Five-minute native idle resource evidence and comparative workloads; record hardware, compositor, exclusions, commands and logs. Separate SYNTHETIC, CI-SCOPED and native acceptance.
- Exact-SHA independent review, CI, serialized authorized integration, post-merge regression, durable handoff. Never merge main without owner authorization and required gates.

## Hermes handoff (activate only when prerequisites satisfied)

Continue Classic without interruption. Modern planning work stays isolated on planning/canopy-modern and does not start production coding. At transition, confirm owner authorization and required Classic functional/Mint acceptance; refresh planning branch from current verified Classic integration without force-pushing shared history. Reconcile instructions and obtain an explicit Modern implementation integration target before PR merges. Do not assume the planning branch is release authorization.

Assign bounded dependency-ready tasks to the existing authorized workforce; use isolated worktrees and independent reviewer. Preserve approved visuals and project rules; no new duplicate supervisor or unbounded worker growth. Continue eligible independent work autonomously, commit/push verified changes, record exact SHAs, recover interrupted tasks, and never stop because one task is blocked. Blocked work is recorded, not marked complete. Prioritize actual runtime wiring over more offline-only validators. Keep Classic regression checks whenever shared interfaces change. Reuse the existing 99-gate reliability audit; no tests are claimed to have run in this planning dossier.

## Open owner decisions

Modern visual concept A/B, taskbar/menu identity, token palette and original artwork; exact scope of snap/previews; taskbar placement options; approved runtime integration target and transition authorization. Backend/compositor support, real shared API extraction and final resource thresholds require measured engineering evidence. LacOS and additional packs remain later phases.
