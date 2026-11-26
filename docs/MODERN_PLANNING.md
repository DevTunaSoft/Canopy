# Canopy Modern — planning charter

**Status: planning only; no implementation or visual approval claimed.**

Branch: `planning/canopy-modern`.
Initial baseline: Classic integration commit `16569c46876013e6e47c29452a2ab36fa82f1cc8`.
This charter supplements the existing engineering contract, not replaces it.

## Mission

Deliver a premium Windows-familiar Linux desktop presentation with original or properly licensed assets, low resource consumption, accessible workflows and user choice. Modern is the second Canopy Shell Pack, not an independent desktop engine or a separate distribution. LacOS remains the later distribution project.

## Scope to design

- Configurable centered or left-aligned taskbar, running application state, tray, clock, keyboard navigation and auto-hide.
- Application menu with pins, favorites, categories, search and accessible navigation.
- Window previews, snapping and workspace workflows using shared host capabilities.
- Quick settings, notifications, file workflows and personalization through shared services.
- Light/dark/high-contrast appearance, original icons, wallpaper selection, scaling, reduced motion and accessible focus states.
- Five performance profiles plus Auto Mode and per-feature overrides, subject to shared-core readiness.

These are planning targets, not implemented features. Visual identity, detailed layout and artwork remain subject to owner approval.

## Architecture and resource principles

Reuse the shared host's application discovery/launch, window/session ownership, notifications, settings, system controls, accessibility and recovery. Do not fork Classic services, run a second compositor, duplicate resident processes or introduce needless polling. Keep inactive packs unloaded when safe. Preserve existing quality, security and evidence gates. Prefer event-driven updates, bounded caches, lazy loading and measured optimization. Audit the actual Classic runtime interfaces before deciding what can be reused or extracted; no speculative rewrites.

## Planning deliverables

1. Product requirements and interaction specifications, including explicit non-goals.
2. Original premium GUI concepts, taskbar/menu mockups and visual token specifications for owner review.
3. Shared-core dependency inventory with exact source references and gaps.
4. Versioned Shell Pack compatibility and integration plan, including rollback and state preservation.
5. Dependency-ordered implementation backlog, resource budgets and verification matrix.
6. Master engineering dossier and Hermes handoff, with clear acceptance criteria and open decisions.

## Transition and isolation

Classic completion remains the governing priority. Do not divert active Classic agents, touch Classic-owned paths, change the default experience, merge to main, or start Modern runtime implementation under this planning charter. Planning may proceed independently. Keep planning changes scoped to this branch; coordinate any shared-core changes through the established integration workflow.

Before starting Modern implementation, refresh from the then-current verified Classic integration baseline (preserve planning commits; no shared-history rewrite), audit reusable contracts, confirm Classic's required functional/Mint acceptance and obtain explicit authorization to start implementation. Do not assume this branch's initial snapshot is the final Classic baseline.

Future work must verify actual compiled screenshots, native Linux Mint interactions, keyboard/accessibility, install and rollback, session-safe switching where supported, and real desktop RAM/CPU/GPU measurements. Green CI alone is not release or visual acceptance.

## Governing references

- [Engineering contract](../AGENTS.md)
- [Architecture](ARCHITECTURE.md)
- [Shell Pack architecture](SHELL_PACK_ARCHITECTURE.md)
- [LacOS vision](LACOS_VISION.md)
- [Quality gates](QUALITY.md)
- [Classic product completion matrix](PRODUCT_COMPLETION_MATRIX.md)
