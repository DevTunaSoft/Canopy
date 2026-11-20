# Canopy agent engineering contract

## Latest canonical user-approved artwork (November 20, 2026)

**READ FIRST: `docs/CLASSIC_CANONICAL_ARTWORK.md`.** The user's direct
upload contains **eight exact app icons**, and the user explicitly selected
these original PNG designs. Order: Browser Option 3, Mail Option 5, Files
Option 2, Calendar Option 3, Photos Option 2, Music Option 3, Terminal Option 4,
Settings Option 8. Their source bytes and SHA-256 digests are locked in
`prototype/classic/assets/approved/manifest.json`. The blue-wave PNG
used in the latest user-liked concept is also SHA-locked there. Do not
replace artwork with approximations, icons invented from the old moodboard,
different wallpaper art or self-drawn SVGs. The prior six-icon moodboard
order is **SUPERSEDED** for Classic's approved icon collection.

Use `--approved-art-dir PATH --self-test-approved` for true Qt approved-asset
runs. If the artwork package is unavailable, mark exact-icon visual
verification **BLOCKED** rather than showing old demo icons and claiming
success. The approved artwork ZIP is preserved in the user's Canopy Library.
Do not silently merge any draft or call the generated concept a Qt screenshot.


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

## Corrected icon source-of-truth (November 20, 2026)

The user **rejected** the claimed PR #72 "approved" icon match: it substituted
author-invented artwork for actual references. Before touching brand assets
read `docs/VISUAL_REFERENCE_PROVENANCE.md` and check the real archived
images. The explicitly requested top-left launcher is the **white solid
Tux-like silhouette** from the recovered image, *not* the invented dark,
ivory-and-gold penguin, nor a combined tree logo. The launcher SVG is a
source-image vector TRACE, not a master supplied by the user.

The recovered moodboard shows six dock app **categories** (Files, Browser,
Settings, Photos, Terminal, Trash). These do not authorize copying Apple's
lookalike icons or claiming the model-drawn versions are the user's files.
Do not add an invented Canopy dock icon or alter the order without new
verifiable instruction. No "approved", "exact copy", or "what you sent"
claims without visual proof and explicit acceptance.

Run the SVG safety checks, regression tests, Qt screenshot tests and Mint VM
acceptance as distinct gates. Keep the visual changes on a separate DRAFT PR;
do not merge to main. Maintain existing engineering/efficiency requirements.

## Current isolated design experiment

The unapproved `feature/classic-blue-current-wallpaper-20261120` branch
introduces original embedded `assets/wallpapers/blue-current.svg` and a
source+runtime validation gate. Read
`docs/CLASSIC_VISUAL_REBUILD.md` before any design-related changes. The
existing dock, folder tiles and Files UI still fail visual acceptance.
**Do not conflate a passing SVG/Qt pipeline with owner approval.**
Retain as an experimental, stacked draft only. Avoid attempting to
merge a design branch while VISUAL_REVIEW_PENDING.

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
