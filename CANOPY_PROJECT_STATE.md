# Canopy — current project state and coordination ledger

> Status snapshot: 2026-11-21. This document is a coordination record, **not** evidence of active agents, green CI, Mint acceptance, or owner visual approval. Update with exact SHAs and links after each verified milestone.

## Source of truth and authority
- Existing `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/QUALITY.md`, and the reliability/visual reference documents remain authoritative. This file supplements them; it does not replace or weaken them.
- Owner approves visual changes and product direction. The coordinating engineer reviews architecture, integration, test evidence, and branch scope. Copilot may provide **secondary code review only**, not autonomous implementation/merge authority.
- Agents are not assumed to be running because issues exist. Each active task must record the assigned executor, actual start time, branch, commit, and latest run evidence.

## Current release target
Deliver one integrated, actual compiled **Canopy Classic Qt** candidate, with the owner's original eight icons and frozen dock, owner-directed alpine-lake/autumn-tree/snowy-mountain/sunset wallpaper direction, launcher, clock, Files preview interactions, and native Linux app launch where enabled. No invented screenshot, mockup, release claim, or unlicensed artwork.

Primary release blocker: [#132](https://github.com/DevTunaSoft/Canopy/issues/132).

## Evidence-based status
| Area | State | Evidence / next gate |
| --- | --- | --- |
| Desktop shell on main | NOT RELEASED | README currently states no working desktop shell; inspect SHA before revising |
| Compiled Qt prototype | DRAFT / NOT INTEGRATED | [#100](https://github.com/DevTunaSoft/Canopy/pull/100); exact head and CI must be rechecked |
| Dock and original icon assets | VISUAL ACCEPTANCE BLOCKED | Do not alter approved masters or dock geometry; review [#109](https://github.com/DevTunaSoft/Canopy/pull/109), [#121](https://github.com/DevTunaSoft/Canopy/pull/121), [#123](https://github.com/DevTunaSoft/Canopy/pull/123) |
| Wallpaper | DIRECTION SET / DISTRIBUTABLE ASSET UNVERIFIED | Owner's alpine scene, not older wave; inspect [#76](https://github.com/DevTunaSoft/Canopy/pull/76) |
| Launcher and native apps | DRAFT | Review [#120](https://github.com/DevTunaSoft/Canopy/pull/120), [#124](https://github.com/DevTunaSoft/Canopy/pull/124), [#102](https://github.com/DevTunaSoft/Canopy/pull/102) |
| Live clock | DRAFT | [#119](https://github.com/DevTunaSoft/Canopy/pull/119) |
| Actual screenshot comparison | DRAFT | [#118](https://github.com/DevTunaSoft/Canopy/pull/118); actual screenshot artifacts and SHA required |
| Linux Mint guest acceptance | NOT PROVEN | [#87](https://github.com/DevTunaSoft/Canopy/issues/87); only real in-guest runs count |
| Performance acceptance | NOT PROVEN | [#88](https://github.com/DevTunaSoft/Canopy/issues/88); 5-minute CPU/PSS target evidence required |
| Shell Host event architecture | ASSIGNED / EXECUTION UNVERIFIED | [#86](https://github.com/DevTunaSoft/Canopy/issues/86) |
| Copilot review | NOT VERIFIED | Only use after a reviewable diff exists; never infer execution |

## Ownership and integration rules
1. **Coordinator:** maintain this ledger, reconcile draft PR dependencies, record current main SHA, prioritize #132 and guard scope. No automatic claims about background execution.
2. **Qt engineer:** launcher/clock/interaction work only on assigned branch; never alter frozen dock geometry or original icon masters.
3. **Visual QA:** independently review *compiled* Qt PNG captures at 760x500, 1200x750 and 1920x1080, with SHA, artwork provenance, optical center and human signoff.
4. **Mint QA:** execute guest-only acceptance when a real Mint session is available; do not call synthetic checks acceptance.
5. **Reliability/performance:** independently verify security, regressions and measured resource targets; no fabricated figures.
6. **Copilot:** optional secondary read-only PR review. Coordinator resolves findings; no Copilot merge authority.

## Immediate execution order
1. Record current main SHA and exact open-PR head SHAs, dependency graph, CI conclusions, superseded/rejected branches. Avoid merging rejected visual directions (#69, #72, #81) or unreviewed stacked ancestry.
2. Integrate only validated, relevant changes on a clean branch from main; run complete Qt compile and runtime smoke tests.
3. Capture actual build screenshots and compare to owner-approved references without changing frozen assets. Explicitly mark unresolved visual issues.
4. Run Mint guest acceptance and measured performance evidence when the required environments exist.
5. Request owner visual approval; merge to main only after all required green checks, exact-SHA evidence, and acceptance.

## Session handoff template
- Date / executor / active branch / HEAD SHA:
- Scope and paths owned:
- Changes committed (SHA and PR):
- Tests (command, platform, PASS/FAIL/BLOCKED/NOT RUN, artifact links):
- Visual state (approved / pending / rejected):
- Mint state and performance evidence:
- Current blocker and exact next action:
- Copilot review (requested / completed / not run):
- Merge decision and reason:

**Never use 'green' without identifying which exact checks passed at which commit.**
