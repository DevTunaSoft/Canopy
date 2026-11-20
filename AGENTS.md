# Canopy agent engineering contract

Read README.md, docs/ARCHITECTURE.md, docs/QUALITY.md, and docs/PREMIUM_DESIGN_DIRECTION.md completely before making UI changes. Read all existing engineering guidance before making other changes. Preserve existing project instructions; this file supplements rather than replaces them.

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

## Visual design correction (November 20, 2026)

The user explicitly rejected the current PR #69 visual direction as **cheap**
and unlike the agreed macOS-inspired premium target. Treat the existing
flat/vector landscape, generic rounded-square dock icons and simplified Files
preview as test fixtures, not an approved design foundation.

Before further cosmetic QML changes:
- Re-read the **rejection and visual proof gate** in
  docs/PREMIUM_DESIGN_DIRECTION.md. Maintain macOS-familiar layout and
  interactions as closely as legally feasible using ORIGINAL/LICENSED assets.
- Prepare cohesive light-theme reference and original art direction; acquire
  explicit visual approval before expanding the design.
- Never assert that a successful build, smoke test, screenshot, or low CPU/PSS
  means a design has passed aesthetic review. Record status separately:
  `BUILD_PASS`, `VM_PASS`, `VISUAL_REVIEW_PENDING`, `VISUAL_REJECTED`,
  `VISUAL_APPROVED` as evidence supports.
- Source/quality-control for high-DPI wallpaper and icons is mandatory. Do
  not replace premium assets with crude QML Canvas shapes, emoji or
  placeholder-colored squares to save effort or resources.
- Preserve existing tests, performance constraints, accessibility, the
  future Classic/Modern separation, and safe incremental branch workflow.
  PR #69 is **visually rejected**, not merge-ready.

## Visual acceptance
The existing Qt demo is **not** a premium shell skin. Never represent successful CI, nonblank screenshots, a palette swap, or four utility icon tiles as completed high-quality visual design. A representative interactive desktop scene, original art, window chrome, design review and actual Mint acceptance are required. Follow docs/PREMIUM_DESIGN_DIRECTION.md.
Use a coherent design token system: typography, spacing, surfaces, elevation, icon sizes, motion, focus states, and high-DPI scaling. Maintain visual review screenshots for defined resolutions, light/dark modes, and reduced-motion mode. Premium appearance must not depend on constant blur or animated backgrounds.

## Definition of done
Functional behavior, accessibility, no known regressions, documented resource measurements, reproducible build/test steps, and a PR with evidence.
