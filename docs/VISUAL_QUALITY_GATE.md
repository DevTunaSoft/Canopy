# Canopy Visual Quality Gate

Every UI PR must complete this checklist. This is a **release gate**, not an inspiration mood board.

## Non-negotiable visual standards
- [ ] The UI looks cohesive, premium, restrained, and intentional rather than like a generic theme or a superficial macOS clone.
- [ ] Typography has consistent weight, line-height, legible size, and appropriate hierarchy; no clipped, fuzzy, or misaligned labels.
- [ ] Spacing, alignment, padding, radii and component sizes follow shared tokens; no arbitrary one-off values without an explained exception.
- [ ] Original icons have consistent stroke/fill weight, scale and baseline; no unlicensed Apple imagery or unfinished placeholders.
- [ ] Both light and dark modes provide deliberate colors, surface hierarchy, visible focus/hover/selected/disabled states, and adequate contrast.
- [ ] Shadows, translucency and transitions add depth without distracting noise, muddy glass, illegible text, animation stutter or expensive constant repaints.
- [ ] File manager, dock, menu bar, launcher, settings, dialogs, notifications, and window decorations look like one product when affected.
- [ ] UI is coherent at 1366×768 and 1920×1080, 100% and 150% scaling, and with long labels and crowded windows.
- [ ] Keyboard navigation, focus visibility, screen-reader semantics, reduced motion and low-effects mode are functional and attractive.
- [ ] Appearance remains stable on weak integrated graphics, under load and after resume; no broken transparency fallback.

## Evidence for review
Attach or link **real screenshots from a running Linux desktop** showing before and after when available, plus exact environment: distro, desktop/compositor version, resolution, scale, GPU/driver and theme. Include a light and dark state, launcher and dock, and representative application/window states as relevant.

A browser mockup or generated rendering is permitted to **propose** a direction but cannot verify actual Linux rendering, integration, or performance. Do not confuse the two.

For visual work, include a short written self-review: what feels refined, what is still visibly rough, known mismatches with the design system and how they are tracked. Address clear visual defects before declaring complete.

## Performance and engineering gate
- [ ] No extra resident process or timer was added without a justification and resource measurements.
- [ ] Relevant CPU/RAM/GPU, compositor/wakeup and frame-time data are captured where measurable; follow `docs/PERFORMANCE.md`.
- [ ] Low-effects fallback preserves usability and quality; no idle continuously running animation.
- [ ] Existing behavior, security and accessibility regressions were checked and failures root-caused.
- [ ] No duplicate implementations of functionality available in the selected native Linux stack.

## Merge policy
Record each gate as **PASS**, **FAIL**, **NOT RUN**, or **BLOCKED** with evidence or reason. No blanket PASS. Keep the PR draft while mandatory checks remain NOT RUN/BLOCKED or FAIL, unless the PR explicitly contains only planning/design documents with no shipping UI and is reviewed as such.

Premium visual quality is **equally important** to clean code, security and low resource usage; do not sacrifice one to mask weaknesses in another.
