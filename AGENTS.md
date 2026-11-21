# Canopy agent engineering contract

## Latest owner's dock and launcher correction (November 20, 2026 — supersedes white Tux)

- Preserve the exact eight approved source PNGs and SHA-256 locks. Render them in
  uniformly rounded, **alpha-clipped** icon cards, with some extra breathing room
  so no source pixels escape the rounded outline and no pictogram is over-zoomed.
- Source master images must never be recolored, substituted, recompressed, or
  overwritten. The runtime `RoundedDockIconProvider` creates padded derivatives
  **in memory once per launch** after verifying all original byte hashes.
- The upper-left penguin launcher must now be a **full-color Tux-like icon**
  (dark body, white belly, amber beak, golden feet), replacing the earlier
  preference for a solid-white silhouette. Retain the reference-based shape.
- Real Qt screenshots with the exact archived artwork and standalone alpine
  background are the visual proof. A concept image or CI's synthetic fixtures
  must not be described as real-design approval. Keep tests and low-RAM/CPU rules.


## Latest canonical user-approved artwork (November 20, 2026)

**READ FIRST: `docs/CLASSIC_CANONICAL_ARTWORK.md`.** The user's direct
upload contains **eight exact app icons**, and the user explicitly selected
these original PNG designs. Order: Browser Option 3, Mail Option 5, Files
Option 2, Calendar Option 3, Photos Option 2, Music Option 3, Terminal Option 4,
Settings Option 8. Their source bytes and SHA-256 digests are locked in
`prototype/classic/assets/approved/manifest.json`. The archived blue-wave
PNG is also SHA-locked for legacy provenance, but it is **not** the current
wallpaper target. The owner's latest direction is a photorealistic alpine lake,
autumn trees and snowy mountains similar to the supplied reference screenshot;
an original or properly cleared standalone image has not yet been packaged.
Do not replace the exact eight approved icons with approximations, old
moodboard interpretations or invented SVGs. The prior six-icon moodboard
order is **SUPERSEDED** for Classic's approved icon collection.

Use `python tools/install_approved_art_zip.py --archive ZIP --destination DIR`
to safely install original SHA-locked PNG bytes from the archived user ZIP.
For current landscape captures, use `--approved-art-dir PATH
--landscape-wallpaper PATH --self-test-approved`; the landscape must be a
cleared original standalone asset, not the reference screenshot or CI fixture.
 If the artwork package is unavailable, mark exact-icon visual
verification **BLOCKED** rather than showing old demo icons and claiming
success. The approved artwork ZIP is preserved in the user's Canopy Library.
Do not silently merge any draft or call the generated concept a Qt screenshot.


Read README.md, docs/ARCHITECTURE.md, docs/QUALITY.md, and docs/PREMIUM_DESIGN_DIRECTION.md completely before making UI changes. Read all existing engineering guidance before making other changes. Preserve existing project instructions; this file supplements rather than replaces them.

## Mission
Build a polished, familiar Linux desktop shell. Classic is macOS-inspired without copying proprietary artwork, assets, or trademarks. Modern is a later Windows-inspired presentation using shared services. Tagline: “The Familiar Feel. The Freedom of Linux.”

## Future product goal: LacOS and switchable experiences

Read `docs/LACOS_VISION.md` for the future Linux Mint-based LacOS distribution goal. Preserve the project sequence: **finish and verify Canopy Classic**, build shared-core Windows-familiar Canopy Modern, make Classic/Modern freely switchable on demand (aim for in-session app/window preservation, with safe announced logout/login fallback when unavoidable), **then** build a separate optimized Mint-derived distribution. This is planned, not released. Do not create duplicate desktop daemons or compromise Mint security, stability, performance budgets, asset provenance, user-approved visual direction, or existing instructions. A live-switch claim requires real tests; do not invent evidence.

## Open-ended Shell Packs — latest owner requirement

Canopy must accept an **unbounded number of future desktop presentation
styles**. Classic and Modern are starting Shell Packs, not the only two.
Read `docs/SHELL_PACK_ARCHITECTURE.md` before changing shell architecture.

- Build and preserve a versioned, documented **Shell Host** contract. New
  packs get their own UI/branding/preferences but consume shared
  apps/windows/notifications/settings/accessibility/session services.
- One active presentation, no duplicate compositor, daemons, background
  indexing, notification services or hidden always-on inactive shell.
- Keep Classic's user-approved live Qt visual direction, exact approved icon
  provenance and quality gates. New adapters must not degrade its visuals.
- Offer a simple SDK/starter, strict schema validation and compatibility
  checking; test that a third independent presentation can integrate
  without editing core business logic when a loader is actually built.
- Treat downloaded pack code as **untrusted**: offline manifest validation
  is never permission enforcement, package verification or safe execution.
  Future community packs require signed/reviewed installation and isolation.
- Target app/window-preserving in-session switching only when demonstrated.
  Clearly warn and safely fall back to logout/login where compositor/session
  requirements make a hot swap unsafe; recover from failed switches.
- Maintain current performance budgets, readability, modular code, CI,
  regression coverage, VM tests, stable APIs and accessibility. Do not
  announce a running marketplace, pack host, third-party loader or switcher:
  these are still planned.

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
images. The original top-left launcher was a **white solid Tux-like silhouette**,
but the owner has now explicitly replaced that requirement with a
**full-color Tux** based on the same traced contour, not a combined tree logo.
The launcher SVG is a source-image derivative, not an external master file.

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

## Visual QA escalation — owner correction (November 21, 2026)

**Reject visually wrong output even when source checks, Qt compilation, geometry
tests, and smoke tests pass.** Review actual screenshots at native size and
at a meaningful close-up. In particular, measure/check both (a) icon image
rectangles within dock controls and (b) the intrinsic artistic balance,
zoom, edge clipping, consistency and optical centering *within the PNGs*.
These are different acceptance gates. The earlier PR #80 only verified
rounded corners while leaving icons 6px too high; this was rejected.

When verified geometry passes but original icon masters remain
compositionally unbalanced, record `VISUAL_REVIEW_PENDING`, explain the
specific issue, and ask the owner before altering their explicitly
selected PNG source artwork. Do not automatically declare success or
silently replace masters. Produce screenshots from the real compiled Qt
application using exact source hashes; static simulations are not
proof of the running build.

## Visual acceptance
The existing Qt demo is **not** a premium shell skin. Never represent successful CI, nonblank screenshots, a palette swap, or four utility icon tiles as completed high-quality visual design. A representative interactive desktop scene, original art, window chrome, design review and actual Mint acceptance are required. Follow docs/PREMIUM_DESIGN_DIRECTION.md.
Use a coherent design token system: typography, spacing, surfaces, elevation, icon sizes, motion, focus states, and high-DPI scaling. Maintain visual review screenshots for defined resolutions, light/dark modes, and reduced-motion mode. Premium appearance must not depend on constant blur or animated backgrounds.

## Definition of done
Functional behavior, accessibility, no known regressions, documented resource measurements, reproducible build/test steps, and a PR with evidence.
