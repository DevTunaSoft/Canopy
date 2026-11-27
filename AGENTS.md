# Canopy agent engineering contract

## Controlling owner directive (2026-11-27)

Read [docs/MASTER_OWNER_DIRECTIVE.md](docs/MASTER_OWNER_DIRECTIVE.md) first; it supersedes incompatible historical implementation, workforce, distro and integration policies. Maximum eight subagents plus Hermes, lower as needed; finish active assignments before reassignment. Fedora Kinoite is the leading evidence-gated production candidate; preserve official upstream update continuity. All first-party features and Shell Packs are FOSS and free. No routine upstream security update requires owner approval. All existing release, security, named holds and visual safeguards remain binding.

## Governing architecture decision — 2026-11-27 (Plasma 6 track)

The owner has authorized native KDE Plasma 6/KWin and gated autonomous main integration. Read [docs/PLASMA6_PIVOT.md](docs/PLASMA6_PIVOT.md) first: it governs conflicting implementation, distro and merge instructions. Finish all currently assigned legacy tasks before reassigning their agents; commit, review and integrate eligible work, document genuine external blockers, and assign no new Cinnamon-specific tasks. Freed workers may start migration. Archive final legacy SHA and selectively port verified deltas. Use integration/canopy-plasma6-20261127 until native Plasma Classic passes its coherent baseline gates; then Hermes may integrate the baseline into protected main and use main as the development trunk under the ADR's independent review, required-check and regression policy. Stable releases and protected identity changes remain owner-gated. Kubuntu 26.04 LTS is the reference development guest; evaluate Fedora Kinoite first against other immutable alternatives. Do not force-push, bypass protections, duplicate desktop services, change protected artwork or increase the current owner-authorized host-safe workforce cap. Preserve named holds #279/#151/#278.

Read README.md and docs/ARCHITECTURE.md and docs/QUALITY.md completely before making changes. Preserve existing project instructions; this file supplements rather than replaces them.

## LacOS immutable core and application options (2026-11-27)

Read [docs/LACOS_IMMUTABLE_ARCHITECTURE.md](docs/LACOS_IMMUTABLE_ARCHITECTURE.md) and updated [docs/LACOS_VISION.md](docs/LACOS_VISION.md). The production OS must use a read-only core with verified atomic updates/rollback and separate APT, Pacman, DNF/RPM, Flatpak and rootless Podman application paths. The exact backend/base remains evidence-gated. Include KDE neon in upstream compatibility research; use every relevant Zorin edition and layout as research across the desktop experience library without copying proprietary assets or adding a second desktop. Do not interrupt current assignments or delay native Classic with speculative distro work.

## Governing product-completion priority

The governing objective is one coherent, functional, secure, stable, resource-efficient and premium Canopy Classic desktop product. Workstreams are: 1 product integration/functional engineering; 2 premium GUI/artwork engineering; 3 Plasma session/deployment (Mint remains legacy reference); 4 independent QA/performance/release evidence. Prioritize security/stability/data integrity, explicit owner decisions and approved visual identity, actual product functionality, clean architecture, continuous autonomous execution, and evidence-backed acceptance. Do not optimize for commit, PR, module or test counts. Use `docs/PRODUCT_COMPLETION_MATRIX.md` and `docs/GUI_ENGINEERING_DOSSIER.md` to select dependency-aware work and record verified maturity. Do not continue generating increasingly granular standalone validators while core desktop integration remains incomplete. The 2026-11-25 master product-completion/GUI-takeover directive supersedes earlier lower-priority queues and the prior ChatGPT-exclusive visual ownership rule, but does not weaken security, quality, accessibility, resource, release-gate or final-owner-acceptance requirements.

## Authority and continuous execution

The owner authorizes Hermes to perform routine engineering, GUI refinement, testing, legitimate dependency installation, GitHub operations, independent review, PR promotion and integration into the appropriate integration branch and, after the baseline transition gates pass, protected main without repeated permission. Preserve branch protections, named holds, security and release gates. Development integration is not release approval; see the governing ADR.

Hermes should maintain productive engineering subagents within the current owner-authorized host-safe cap, aiming for at least four when capacity and eligible work permit, with isolated worktrees, explicit
file ownership, bounded assignments and non-overlapping responsibilities.
When an agent completes or is blocked, immediately assign another eligible
independent task. Verify the five-minute watchdog is operational and restore
the workforce or recover interrupted work when it is not.

Draft PRs are temporary development states, not permanent holding areas. After exact-SHA checks, dependency/ancestry verification, independent review and green required checks, promote eligible changes to ready and integrate them promptly; run mandatory post-merge regression after integration. Verified nonvisual and bounded non-substantive visual-refinement work may integrate into the designated integration branch; substantial identity changes and final visual acceptance remain owner-gated. Do not leave verified work indefinitely in draft. Do not stop merely because a PR was created, a test completed, a milestone was reached, one agent was blocked, final visual acceptance is pending, or a recoverable error occurred.

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
1. Fetch origin/main and the designated integration branch; use the appropriate current integration tip during migration and protected main after the baseline transition; inspect existing work, open PRs, tests, and docs before choosing a task.
2. Select one bounded milestone, avoid duplicated concurrent work, and use an isolated feature branch; reuse an existing scoped PR where appropriate. Draft status never prevents commits or pushes.
3. Implement tests alongside code. Run available formatting, linting, unit, integration, and packaging checks; distinguish PASS, FAIL, BLOCKED, NOT RUN.
4. On failure diagnose root cause, fix it, add regression coverage, and rerun affected tests.
5. Update README, architecture, quality budgets, and status docs when behavior changes.
6. Commit and push verified changes to GitHub; never merge failing or unverified work. Continue to the next eligible independent task without waiting for unrelated release gates.
7. Record measured performance with machine details, methodology, and baseline; do not invent numbers.

## Visual ownership and acceptance

Hermes now owns GUI development, visual design engineering, artwork processing, icon correction, Qt/QML presentation, usability, accessibility and visual QA. The previous ChatGPT-exclusive visual ownership rule is superseded by the owner's 2026-11-25 directive. Preserve the approved Canopy design identity: original icon artwork, approved alpine lake wallpaper, Tux launcher identity, centered dock, top menu bar, Classic layout, branding and macOS-familiar interaction language. Hermes may professionally refine optical alignment, proportions, spacing, typography, hierarchy, contrast, transparency, shadows, surfaces, controls, focus/hover/selected states, high-DPI behavior and unfinished interface components without requesting approval for each minor refinement. Substantial identity changes, artwork replacement or fundamental layout changes require owner approval. Final owner visual acceptance remains required. Do not copy proprietary artwork or substitute unapproved wallpapers/icons. Visual QA must inspect actual compiled Qt screenshots at 1920x1080, 1200x750 and 760x500, plus relevant crops and transparency tests; unit tests alone are not visual acceptance. Pending final acceptance never blocks functional engineering.

## Definition of done
Functional behavior, accessibility, no known regressions, documented resource measurements, reproducible build/test steps, independent review of the exact head SHA, integration into the designated branch with post-merge regression evidence, and a PR with evidence.

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
performance, reversible deployment on the selected supported base and human visual acceptance. Green
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

## Autonomous integration and durable checkpoints
Commit and push each coherent verified change to its owned branch; verify the remote SHA. Preserve unfinished work on its isolated branch with explicit test status, never present it as verified. Routine independently reviewed engineering, bounded visual-refinement and integration changes may integrate into the designated integration branch after applicable exact-SHA checks and dependency review; run regression tests after integration. Final release requirements apply to final release integration, not independent development. Named PR holds, branch protections, owner visual approval and high-risk security approval remain binding. Do not merge #151 or #278 into main or override their specific holds. Keep productive isolated engineering subagents plus Hermes within the current owner-authorized host-safe cap when eligible work exists; prioritize wiring existing modules into real runtime behavior over new offline-only helpers. A blocked task is not complete; continue unrelated tasks. Do not create duplicate supervisors or redundant PRs.
