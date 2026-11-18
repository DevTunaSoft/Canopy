# Canopy — Repository Engineering Instructions

These instructions apply to all contributors and automated coding agents. They **add to, not replace**, existing requirements, user specifications, and repository documentation. Resolve conflicts by preserving the stricter security, correctness, accessibility, performance, and quality requirements; document any conflict rather than silently dropping a requirement.

## Product goal
Build **Canopy**, a premium-quality, macOS-inspired Linux desktop experience ("Classic") that is welcoming to people moving from macOS to Linux. The long-term "Modern" Windows-inspired interface must share core functionality and services. Tagline: **The Familiar Feel. The Freedom of Linux.**

**Visual polish is a shipping requirement, not optional decoration.** Every user-facing change must look and feel coherent with the rest of Canopy. Avoid cheap-looking imitation, inconsistent themes, generic placeholder icons, awkward spacing, excessive effects, and visual regressions.

## Design rules — mandatory
1. Read `docs/DESIGN_SYSTEM.md` and `docs/VISUAL_QUALITY_GATE.md` before changing UI. Apply centralized design tokens, typography, spacing, corner treatments, surface hierarchy, iconography and motion; do not invent slightly different styles in individual components.
2. Aim for refined, deliberate, premium aesthetic quality: crisp type, balanced alignment, carefully controlled shadows and translucency, strong contrast and readable states. Design light and dark experiences together.
3. Original, properly licensed Canopy branding, icons, and artwork only. No Apple-proprietary icons, copied assets, or misleading product branding. Treat temporary symbols as placeholders clearly identified in documentation; replace before release.
4. Visual quality and low resource use are **simultaneous** acceptance gates. Favor native GPU-composited transform/opacity transitions, static gradients, and limited blur. No idle animation/polling, duplicate desktop services, or resource-heavy effects solely for appearance.
5. Keep behavior polished too: keyboard navigation, predictable interactions, scalable text, high-DPI display support, accessible focus and contrast, reduced-motion support and low-effects fallback must remain usable.
6. Create screenshots from a **running Linux session** for implementation claims. Label concept renders, browser previews and AI-generated imagery accurately; never present them as a verified build.

## Engineering and delivery rules — mandatory
- First inspect the repository, roadmap, existing architecture, code, and prior work. Reuse functionality; prevent duplicated work and conflicting changes.
- Produce clean, modular, secure, low-memory, maintainable code with small well-defined interfaces; favor event-driven behavior. Do not reinvent the compositor, file manager, or OS services without documented evidence.
- Develop on feature branches; keep changes scoped, document decisions and update relevant roadmap/feature status/manual files where present.
- Add and execute appropriate tests (including visual and accessibility regressions), verify behavior on supported Linux configurations, diagnose root causes for failures, and rerun affected regression suites.
- Quantify memory, CPU, wakeups and GPU behavior when making performance claims; consult `docs/PERFORMANCE.md`. Targets are **not** verified results.
- Do not report PASS without logs or reproducible evidence. Commit changes to the feature branch, open/update a draft PR, and merge only after required reviews and checks actually pass. Never manufacture completion or test results.
- Work autonomously where supported, document true blockers concisely, and preserve development notes that allow another engineer to resume without guesswork.

## Definition of done for visible UI
A change is not ready to merge until the visual quality gate, functional behavior, accessibility, and relevant resource/regression checks pass with evidence. When hardware integration is unavailable, mark gates NOT RUN and keep the PR draft.

References: `docs/DESIGN_SYSTEM.md`, `docs/VISUAL_QUALITY_GATE.md`, `docs/ARCHITECTURE.md`, `docs/PERFORMANCE.md`.
