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
CI never means visually rejected work is merge-ready. Coordinate with the
owner's existing reviewers; do not recruit reviewers unrequested.
