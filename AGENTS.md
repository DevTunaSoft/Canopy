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
