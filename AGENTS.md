# Canopy agent engineering contract

Read README.md and docs/ARCHITECTURE.md and docs/QUALITY.md completely before making changes. Preserve existing project instructions; this file supplements rather than replaces them.

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
1. Synchronize with origin/main; inspect existing work, open PRs, tests, and docs before choosing a task.
2. Select one bounded milestone, avoid duplicated concurrent work, and use a feature branch and draft PR.
3. Implement tests alongside code. Run available formatting, linting, unit, integration, and packaging checks; distinguish PASS, FAIL, BLOCKED, NOT RUN.
4. On failure diagnose root cause, fix it, add regression coverage, and rerun affected tests.
5. Update README, architecture, quality budgets, and status docs when behavior changes.
6. Commit and push verified changes to GitHub; never merge failing or unverified work. Continue to the next independent task only when safe.
7. Record measured performance with machine details, methodology, and baseline; do not invent numbers.

## Visual acceptance
Use a coherent design token system: typography, spacing, surfaces, elevation, icon sizes, motion, focus states, and high-DPI scaling. Maintain visual review screenshots for defined resolutions, light/dark modes, and reduced-motion mode. Premium appearance must not depend on constant blur or animated backgrounds.

## Definition of done
Functional behavior, accessibility, no known regressions, documented resource measurements, reproducible build/test steps, and a PR with evidence.

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

## Owner-approved visual design lock — mandatory for every coding agent

The current owner-approved Canopy Classic GUI appearance is **frozen** unless the owner explicitly authorizes a specific visual change. This applies to Hermes, OpenCode, Copilot, supervisors, subagents, CI-driven changes, and future contributors.

- Do **not** create, regenerate, replace, recolor, restyle, resize, reposition, rename, or delete approved icons, wallpaper, artwork, branding, dock assets, or their manifests.
- Do **not** alter approved dock geometry, icon centering, spacing, scale, alignment, top menu bar, window chrome, typography, palette, backgrounds, or overall GUI look. Do not substitute placeholder artwork or generic controls for approved visuals.
- Functional, accessibility, compatibility, security, and performance work may proceed **without changing the approved appearance**. If a necessary fix would affect appearance, stop that change and request explicit owner approval; do not infer permission from a task description or green tests.
- Treat the current approved assets and their manifests as immutable reference inputs. Do not assume screenshots or an agent's interpretation supersede owner-approved designs. Where an exact approved visual baseline is not available, do not invent one or claim visual equivalence.
- Before every PR, review changed paths and rendered-output impact for visual regressions. If any approved visual asset or layout is affected, keep the PR in draft and flag it for owner review; do not merge or silently accept it.
- Only the owner/ChatGPT design workflow supplies new approved artwork. Coding agents integrate supplied assets after explicit approval; they must not generate replacements.
- Existing approved visual assets must not be modified as part of unrelated fixes. Preserve them byte-for-byte whenever possible. No automated formatting, optimization, or asset regeneration on protected assets.

This lock is additive to existing visual-acceptance, quality, and legal requirements. It does not authorize redesign of previously rejected mockups, nor does it establish that an unreviewed current screenshot is owner-approved.
