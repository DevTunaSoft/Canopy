# Canopy agent engineering contract

Read README.md and docs/ARCHITECTURE.md and docs/QUALITY.md completely before making changes. Preserve existing project instructions; this file supplements rather than replaces them.

## ACTIVE GOAL — Rev3 controlling directive (2026-11-28)

Sole controlling Canopy/LacOS goal: `C:/Users/X1/Downloads/Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md`, SHA-256 `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a` (short `1fba4b1e`). Earlier master, supplemental and 2026-11-27 directives are `SUPERSEDED_POINT_IN_TIME` where they set older caps, draft-only rules or integration authority; retained as history, not retracted or erased. Security gates, approved visual assets/hash locks, named PR holds #151/#278/#279 and branch protection are not weakened.

- **A0.1 — finish current work:** let every current Canopy/LacOS assignment finish on its authorized branch and worktree. Do not interrupt, cancel, restart, reassign or change branch merely to apply this directive, an integration priority or a workforce cap. Narrow exceptions only: genuine external blocker, unrecoverable stall, security/safety incident, resource emergency, or demonstrably obsolete/duplicated work. Preserve commits, evidence and pending obligations; checkpoint, never mark complete.
- **Project-scoped cap 8+Hermes:** maximum 8 concurrent Canopy/LacOS subagents plus Hermes; count active project workers, not queued or inactive sessions. Finish valid in-flight assignments naturally if over cap and dispatch no new or replacement project worker until capacity exists. **no-global-change:** other Hermes projects and global agent settings are excluded and must not be modified (do not run `hermes config set delegation.max_concurrent_children ...`). This reconciliation PR is DRAFT: no merge, no self-approval.
- **Integration authority / distinct-human-approval blocker:** integration branch and `main` protection require 1 distinct human approving review with `enforce_admins=true`; the only authenticated account (`DevTunaSoft`) authors the eligible PRs, so this is a genuine external blocker. Never self-approve, impersonate a reviewer or bypass protection. Promote eligible PRs to ready, record the exact owner action required, and continue unrelated eligible work. An individual worker's no-self-approval rule does not block the authorized integration lead, who still needs a real distinct human approver when protection requires one.
- **Exclusive guest lease:** use an exclusive guest lease (exclusive session lease with owner, heartbeat and recovery checkpoint) for interactive VM, install/uninstall, display changes, suspend/resume and session restart. Serialize heavy builds, full suites and VM work; never terminate unrelated work to acquire a lock; a timeout is incomplete, not a pass.

## Governing product-completion priority

The governing objective is one coherent, functional, secure, stable, resource-efficient and premium Canopy Classic desktop product. Workstreams are: 1 product integration/functional engineering; 2 premium GUI/artwork engineering; 3 Linux Mint/session/deployment; 4 independent QA/performance/release evidence. Prioritize security/stability/data integrity, explicit owner decisions and approved visual identity, actual product functionality, clean architecture, continuous autonomous execution, and evidence-backed acceptance. Do not optimize for commit, PR, module or test counts. Use `docs/PRODUCT_COMPLETION_MATRIX.md` and `docs/GUI_ENGINEERING_DOSSIER.md` to select dependency-aware work and record verified maturity. Do not continue generating increasingly granular standalone validators while core desktop integration remains incomplete. The 2026-11-25 master product-completion/GUI-takeover directive supersedes earlier lower-priority queues and the prior ChatGPT-exclusive visual ownership rule, but does not weaken security, quality, accessibility, resource, release-gate or final-owner-acceptance requirements.

## Authority and continuous execution

The owner authorizes Hermes to perform routine engineering, GUI and visual refinement, testing, legitimate dependency installation, GitHub operations, independent agent review, PR promotion and integration into `integration/canopy-classic-20261123` without repeated permission. Preserve `main` branch protection, specific PR holds, security requirements and release acceptance gates. Do not merge to `main` without explicit owner authorization and all release gates.

Hermes must maintain at least four concurrently active engineering subagents
in addition to itself (five agents total) with isolated worktrees, explicit
file ownership, bounded assignments and non-overlapping responsibilities.
When an agent completes or is blocked, immediately assign another eligible
independent task. Verify the five-minute watchdog is operational and restore
the workforce or recover interrupted work when it is not.

> SUPERSEDED_POINT_IN_TIME: the "at least four ... (five agents total)" floor and the automatic reassignment rule above are pre-Rev3 directives. Rev3 (`1fba4b1e`) governs with the project-scoped cap 8+Hermes and A0.1 finish-current-work protection; retained as history, not retracted or erased.

Draft PRs are temporary development states, not permanent holding areas. After exact-SHA checks, dependency/ancestry verification, independent review, green required checks and a post-merge regression run, promote eligible changes to ready and integrate them promptly. Verified nonvisual and bounded non-substantive visual-refinement work may integrate into the designated integration branch; substantial identity changes and final visual acceptance remain owner-gated. Do not leave verified work indefinitely in draft. Do not stop merely because a PR was created, a test completed, a milestone was reached, one agent was blocked, final visual acceptance is pending, or a recoverable error occurred.

> SUPERSEDED_POINT_IN_TIME: "integrate them promptly" is bounded by the Rev3 integration authority above. Promotion to ready is allowed; merging is blocked until 1 distinct human approving review with `enforce_admins=true` exists and owner gates pass. Green CI alone is never merge authorization.

## Mission
Build a polished, familiar Linux desktop shell. Classic is macOS-inspired without copying proprietary artwork, assets, or trademarks. Modern is a later Windows-inspired presentation using shared services. Tagline: “The Familiar Feel. The Freedom of Linux.”

## Non-negotiables
- Premium visual quality and accessibility with low idle CPU, RAM, GPU, and wakeups.
- Original iconography and legally distributable assets only.
- Small, modular components with clear ownership; avoid duplicated background services and polling.
- Prefer event-driven updates, caching with explicit invalidation, lazy initialization, and graceful fallback when graphics acceleration is absent.
- Keep display styles independent from shared desktop services and state.
- Secure defaults, no unnecessary telemetry, no secrets in logs, and least-privilege integration.
- No unsupported performance, compatibility, or test claims.

## Workflow
1. Fetch origin/main and the designated integration branch; use the current integration tip for independent Classic engineering, or main for explicitly main-targeted work; inspect existing work, open PRs, tests, and docs before choosing a task.
2. Select one bounded milestone, avoid duplicated concurrent work, and use an isolated feature branch; reuse an existing scoped PR where appropriate. Draft status never prevents commits or pushes.
3. Implement tests alongside code. Run available formatting, linting, unit, integration, and packaging checks; distinguish PASS, FAIL, BLOCKED, NOT RUN.
4. On failure diagnose root cause, fix it, add regression coverage, and rerun affected tests.
5. Update README, architecture, quality budgets, and status docs when behavior changes.
6. Commit and push verified changes to GitHub; never merge failing or unverified work. Continue to the next eligible independent task without waiting for unrelated release gates.
7. Record measured performance with machine details, methodology, and baseline; do not invent numbers.

## Visual ownership and acceptance

Hermes now owns GUI development, visual design engineering, artwork processing, icon correction, Qt/QML presentation, usability, accessibility and visual QA. The previous ChatGPT-exclusive visual ownership rule is superseded by the owner's 2026-11-25 directive. Preserve the approved Canopy design identity: original icon artwork, approved alpine lake wallpaper, Tux launcher identity, centered dock, top menu bar, Classic layout, branding and macOS-familiar interaction language. Hermes may professionally refine optical alignment, proportions, spacing, typography, hierarchy, contrast, transparency, shadows, surfaces, controls, focus/hover/selected states, high-DPI behavior and unfinished interface components without requesting approval for each minor refinement. Substantial identity changes, artwork replacement or fundamental layout changes require owner approval. Final owner visual acceptance remains required. Do not copy proprietary artwork or substitute unapproved wallpapers/icons. Visual QA must inspect actual compiled Qt screenshots at 1920x1080, 1200x750 and 760x500, plus relevant crops and transparency tests; unit tests alone are not visual acceptance. Pending final acceptance never blocks functional engineering.

## Definition of done
Functional behavior, accessibility, no known regressions, documented resource measurements, reproducible build/test steps, independent review of the exact head SHA, integration into the designated branch with post-merge regression evidence, and a PR with evidence.

## Owner-approved roadmap expansion: LacOS and future Shell Packs

Classic is the first desktop presentation, Modern a planned second, and
there must be **no hardcoded two-shell limit**. Read
`docs/LACOS_VISION.md` and `docs/SHELL_PACK_ARCHITECTURE.md`.
New Shell Packs should share one versioned Shell Host for window/session
ownership, app launching, notifications, settings and accessibility rather
than duplicating compositors or background daemons. Keep inactive modes
unloaded whenever safe, with bounded memory and subscription cleanup.

The v1 offline `tools/check_shell_pack.py` is metadata validation **only**;
it is not a runtime loader, permission sandbox, security approval or evidence
of same-session switching. The Qt starter is not installable. Future community
packages require separately verified provenance, signed package mechanisms,
runtime isolation and capability enforcement.

Prioritize finish/verify Classic, then Modern, then test switching/recovery
and a third unrelated presentation, then consider LacOS distribution work.
Preserve immutable user-selected artwork, original/licensed assets, measured
performance, reversible Mint integration and human visual acceptance. Green
CI never means visually rejected work is merge-ready. Welcome code review without limiting participation to a particular group.
Do not publish unsolicited reviewer invitations or recruitment issues.

## Reliability evidence checklist: 99 independent gates

Before claiming a component is production-ready or merging a high-risk
user-facing feature, consult
`docs/RELIABILITY_99_GATE_AUDIT.md`. It enumerates 99 **review questions**,
not 99 completed tests. Only mark a gate as passed with exact commit SHA,
actual environment, reproducible command, logs and screenshots when relevant.
P0 gaps require explicit resolution or a clearly documented blocked state.

"CI-SCOPED" means tested only in the stated source/Ubuntu Actions context;
it is not a whole-product success or proof of Mint, compositor, usability,
security or visual correctness. Keep tests honest (all-skipped is not green),
use negative controls and fail-closed cleanup in every shell lifecycle.

## Autonomous integration and durable checkpoints
Commit and push each coherent verified change to its owned branch; verify the remote SHA. Preserve unfinished work on its isolated branch with explicit test status, never present it as verified. Routine independently reviewed engineering, bounded visual-refinement and integration changes may integrate into the designated integration branch after applicable exact-SHA checks, dependency review and post-integration regression tests. Final release requirements apply to final release integration, not independent development. Named PR holds, branch protections, owner visual approval and high-risk security approval remain binding. Do not merge #151 or #278 into main or override their specific holds. `SUPERSEDED_POINT_IN_TIME`: keep at most eight project-scoped Canopy/LacOS subagents plus Hermes when eligible work exists (Rev3 cap 8+Hermes, A0.1 finish-current-work protection); prioritize wiring existing modules into real runtime behavior over new offline-only helpers. A blocked task is not complete; continue unrelated tasks. Do not create duplicate supervisors or redundant PRs.
