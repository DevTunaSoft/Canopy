# Canopy agent engineering contract

Read README.md and docs/ARCHITECTURE.md and docs/QUALITY.md completely before making changes. Preserve existing project instructions; this file supplements rather than replaces them.

## Authority and continuous execution

The owner authorizes Hermes to perform routine nonvisual engineering, testing,
legitimate dependency installation, GitHub operations, independent agent
review, PR promotion and integration into `integration/canopy-classic-20261123`
without repeated permission. Preserve `main` branch protection, specific PR
holds, security requirements and release acceptance gates. Do not merge to
`main` without explicit owner authorization and all release gates.

Hermes must maintain at least four concurrently active engineering subagents
in addition to itself (five agents total) with isolated worktrees, explicit
file ownership, bounded assignments and non-overlapping responsibilities.
When an agent completes or is blocked, immediately assign another eligible
independent task. Verify the five-minute watchdog is operational and restore
the workforce or recover interrupted work when it is not.

Draft PRs are temporary development states, not permanent holding areas.
After exact-SHA checks, dependency/ancestry verification, independent review,
green required checks and a post-merge regression run, promote eligible
nonvisual work to ready and integrate it promptly. Do not leave verified
nonvisual work indefinitely in draft. Do not stop merely because a PR was
created, a test completed, a milestone was reached, one agent was blocked,
visual approval is pending, or a recoverable error occurred.

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

## Visual acceptance
ChatGPT and the owner exclusively own visual design, artwork, icons, wallpaper, dock geometry and alignment, typography, colors and visual approval. Hermes and its subagents must not redesign, replace or generate those assets. Maintain visual review screenshots for defined resolutions, light/dark modes, and reduced-motion mode. Premium appearance must not depend on constant blur or animated backgrounds. Pending visual approval never blocks nonvisual engineering.

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
Commit and push each coherent verified change to its owned branch; verify the remote SHA. Preserve unfinished work on its isolated branch with explicit test status, never present it as verified. Routine independently reviewed nonvisual changes may integrate into the designated integration branch after applicable exact-SHA checks, dependency review and post-integration regression tests. Final release requirements apply to final release integration, not independent development. Named PR holds, branch protections, owner visual approval and high-risk security approval remain binding. Do not merge #151 or #278 into main or override their specific holds. Keep at least two nonoverlapping workstreams active when eligible work exists; prioritize wiring existing modules into real runtime behavior over new offline-only helpers. A blocked task is not complete; continue unrelated tasks. Do not create duplicate supervisors or redundant PRs.
