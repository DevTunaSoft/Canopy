# CANOPY — CODEX TAKEOVER / MASTER ENGINEERING HANDOFF
Last audited: 2026-11-17. Repository: https://github.com/DevTunaSoft/Canopy

> **Mandatory first read.** This is a self-contained engineering handoff, not a claim that Canopy is a finished desktop. Preserve all existing README, AGENTS.md, specifications, roadmap, ADRs, logs, traceability, and prior decisions. Do not paraphrase them instead of reading them. This document adds detail; it does not supersede them.

The 2026-11-17 audit below records the original takeover state. Read the 2026-11-18 checkpoint in section 10 before selecting a branch.

## 0. Exact Git state: READ BEFORE MODIFYING ANY FILE

As audited on 2026-11-17:

| PR | Branch | Base | Contents | Status |
| --- | --- | --- | --- | --- |
| #1 https://github.com/DevTunaSoft/Canopy/pull/1 | `docs/initial-project-foundation` | `main` | Initial engineering documents | OPEN DRAFT |
| #2 https://github.com/DevTunaSoft/Canopy/pull/2 | `feat/classic-preferences-on-foundation` | `main` | Foundation + shared preferences and tests | OPEN DRAFT |
| #3 https://github.com/DevTunaSoft/Canopy/pull/3 | `feat/classic-gtk-preview` | `feat/classic-preferences-on-foundation` | Experimental GTK Classic top bar/dock | OPEN DRAFT |
| takeover docs | `docs/codex-takeover-dossier` | based on `feat/classic-gtk-preview` | This document, status and handoff corrections | Documentation work |

**WARNING:** `main` currently contains only the initial short README. The working prototype code is on the descendant branches above. Do NOT start from an empty `main` and rewrite or duplicate work. Inspect actual current remote state, since it may change. The branch `feat/classic-shared-preferences` exists but was created as an unused scaffold; inspect before using/removing it. Never delete without approval.

**Safe Codex entry point:**
```bash
git clone https://github.com/DevTunaSoft/Canopy.git
cd Canopy
git fetch --all --prune
git status --short
git branch -a
git switch -c feat/codex-next origin/docs/codex-takeover-dossier
python3 -m unittest discover -s tests -v
python3 -m compileall -q canopy tests
```
If local working state exists, do not overwrite or abandon it; inspect first. If the docs takeover branch is unavailable, use the latest verified descendant of `feat/classic-gtk-preview`, after inspecting PRs and commits. Replace the sample branch name with a unique descriptive feature branch if it already exists. No destructive Git commands. Work only on feature branches and draft PRs. Never force-push or merge main without authorization.

**Original stacked PR concern, resolved 2026-11-18:** PR #2 targeted `main` and included PR #1's work. PR #2 now targets the foundation branch, so the review diff contains only its preferences increment. PR #3 continues to target PR #2's branch. Continue to inspect live PR bases before integration. The takeover branch is another descendant, not an independent implementation. Do not create duplicate PRs for the same changes. Coordinate with parallel agents.

## 1. What Canopy actually is

**Product:** Canopy desktop shell for Linux, first on Linux Mint. **NOT** a separate operating system, Linux distribution or kernel. Preserve Linux Mint and use its mature services. Official tagline: **The Familiar Feel. The Freedom of Linux.** Marketing tagline belongs on README, website, onboarding/branding; do not permanently clutter the desktop.

**Why:** People moving from macOS or Windows should feel familiar immediately yet retain Linux openness, stability, control, licensing and privacy. Visual polish must not compromise security, hardware compatibility, performance or maintainability.

**Canopy Classic:** macOS-inspired top bar; original white Tux-inspired silhouette in upper-left menu location; floating configurable dock; application launcher/search; keyboard shortcuts; polished window workflows; original Canopy icons; themes, accessibility and optional animations. Classic is FIRST.

**Canopy Modern:** Windows-inspired taskbar, app launcher, notification/system tray and familiar workflows. Deferred until Classic is stable. Classic and Modern are interchangeable interface presentations atop ONE shared core; shared system integrations, app model, preferences, security, performance, accessibility and session services. No duplicated desktop implementations. Users should be able to change experience without reinstalling Linux or losing preferences.

**Brand identity:** Canopy name; C/canopy leaf emblem with a Tux-inspired penguin option; initial premium green/dark aesthetic and original iconography, not proprietary Apple/Microsoft logos. Original white silhouette penguin menu mark is desired but **not yet committed as a verified production-ready asset**. User's newer company identity BulldogSoft is planned; current GitHub owner remains DevTunaSoft. Avoid hardcoding either owner in runtime paths; allow eventual repository transfer.

## 2. Preserve every non-negotiable engineering rule

Read `AGENTS.md` and the original user master autonomous development prompt before coding. Key requirements:
- Minimal, clean, modular, secure, memory-efficient code. Reduce idle RAM/CPU, disk I/O, dependency footprint and needless background tasks. Reuse proven Linux services instead of cloning them.
- Autonomous progress: INSPECT -> PLAN -> CODE -> TEST -> FIX -> REGRESSION -> DOCUMENT -> CHECKPOINT -> COMMIT -> PUSH -> VERIFY CI/PR -> NEXT TASK. No routine confirmation loops. Stop for genuine blocker, cost, irreversible action, or permissions.
- Investigate Git, PRs, issues, documents, files and checkpoints before edits; avoid duplicate effort and conflicting concurrent writes. Use isolated feature branches/worktrees with explicit ownership where multiple agents actually run.
- Work on draft PRs; push verified green code, check GitHub Actions, record exact commands and outcomes. Never bypass rules, force-push, destroy work, or merge main without approval.
- Record root cause of any failure and create regression tests; treat flaky/inconclusive tests as NOT VERIFIED.
- Chronological, cumulative documentation: why and what changed, actual verified state, defects, risks, tests, decisions, code pointers and exact next steps. Keep user guide, roadmap, requirements, traceability, ADRs, feature status and handoff aligned.
- No chargeable resources, deployments, irreversible actions or secrets exposure without authorization.
- Ponytail: follow the official `https://github.com/DietrichGebert/ponytail` docs and `SKILL.md` after checking provenance and compatibility. Install in project-scope supported skill location only if safe; do not replace existing AGENTS.md, hooks, skills or settings. Verify in a fresh Codex session. **Ponytail is not currently installed or verified in this repo.** Never claim otherwise.

## 3. Canonical functional specification

### 3.1 Desktop core and integration
Reuse Linux Mint user-space, network, Bluetooth, audio, notifications, package management, file associations, portals, removable drives, power and authentication. Evaluate freedesktop APIs, systemd user services, DBus, polkit, PipeWire, NetworkManager, AppInfo, APT/Flatpak/PackageKit and XDG standards. Make appropriate Wayland/X11/XWayland/compositor decisions in separate ADRs backed by measurements and interoperability tests. Do not promise macOS global menus for Linux apps that do not expose them.

Daily desktop completeness includes application lifecycle, launch, search, settings, notification handling, clipboard, screenshots, lock screen, logout/restart/shutdown, session reliability and suspend/resume. Provide useful failure states, keyboard-only operation, screen reader and reduced-motion compatibility, localization groundwork, fractional scaling/HiDPI, multi-monitor/refresh/gesture support.

### 3.2 Performance
Five manual profiles: **Ultra Lite, Efficient, Balanced, Enhanced, Ultimate**. Intelligent **Auto Mode** can adapt optional effects to real hardware, memory/workload pressure and battery power. Each relevant feature has **Auto/On/Off** overrides. User ON/OFF choices beat automatic optimization when safe and compatible; accessibility, system safety and security always win. Do not disable essential desktop/network functions to 'save resources'. Benchmark cold/warm startup, idle memory, CPU, responsiveness, disk I/O and resume across profiles, Classic and future Modern. Establish realistic numeric budgets only from actual measurements.

### 3.3 Safety, root and recovery
The Canopy shell MUST run unprivileged. Use established polkit-authorized, narrowly scoped system operations when legitimate administration requires a password prompt, just as Linux Mint does. Never store admin passwords or run desktop UI as root. Keep Cinnamon usable as a separate login/fallback session; avoid replacing or breaking it. Provide safe installation/uninstallation, versioned user settings and backups/migrations, corruption recovery, rollback and crash containment. Default privacy and no forced telemetry/cloud account.

### 3.4 Migration and updates
First-run helper for macOS/Windows/Linux habits, keyboard shortcuts, app alternatives and finding personal files; later optional assisted import. Secure updates and release packaging; provenance/license/trademark review; hardware and regression matrices. No dedicated installer ISO until core works safely. Avoid cloning proprietary icons.

## 4. Accurate file inventory and implementation status (audit)

The following existed on `feat/classic-gtk-preview` as of the audit:
- `README.md` — short product introduction; not full user manual.
- `AGENTS.md` — 13 initial rules.
- `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/TRACEABILITY.md`, `docs/HANDOFF.md` — baseline plans, not exhaustive implementation.
- `docs/ADR-001-SETTINGS.md` — preliminary settings architecture.
- `docs/ADR-002-CLASSIC-PREVIEW.md`, `docs/CLASSIC-PREVIEW.md`, `docs/CLASSIC-DEV-LOG.md` — GTK preview design and operation.
- `canopy/preferences.py` — Python dataclasses/enums for layouts, profiles, Auto/On/Off cosmetic toggles, validated JSON and atomic settings save.
- `canopy/classic_model.py` — default dock app IDs, visible-app filter/sort and short clock text.
- `canopy/classic_gtk.py` — GTK3 preview GUI with menu, clock, buttons/dock, Gio application launching. Requires Linux graphical session, GTK3 and PyGObject; NOT a login session or compositor.
- `tests/test_preferences.py` — 8 unittest test methods covering defaults, five manual profile values, overrides, reduced motion, serialization, invalid inputs and corrupt-file behavior.
- `tests/test_classic_model.py` — 3 unittest test methods: clock, app filtering and dock deduplication.
- `.github/workflows/python-tests.yml` and `.github/workflows/docs.yml` — Python unittest and documentation-presence CI checks. The workflows run on branch pushes and PRs.

**Important nuance:** Passing Python unit tests confirms deterministic model behavior, NOT that desktop UI launches on Mint, handles real windows, integrates with Cinnamon, or meets resource targets. Most significant GUI/system requirements remain planned. `README.md` status may understate current prototype; update as PRs land.

### 4.1 Prototype behavior
Preferences default to Classic, Balanced, Auto Mode enabled, all three cosmetic flags in AUTO. The `effective_features()` function accepts **caller-supplied** `battery_saver`, `memory_pressure`, `reduced_motion` flags; **there is no real hardware sensor, hardware auto-detection or resource governor**. Thresholds currently affect only animations, transparency and dock magnification. Settings use JSON schema version 1, with safe temporary replacement and mode 0600 for the written file. Config is read via XDG_CONFIG_HOME or ~/.config/canopy/settings.json for preview. Corrupt JSON raises rather than being silently overwritten.

The GTK prototype shows a top bar labelled 'Canopy ▾' (not yet the original Tux), 'Classic', 'Preview', and clock; a dock with available launchers `nemo.desktop`, `firefox.desktop`, `org.gnome.Terminal.desktop` plus Apps menu. It relies on Gio AppInfo, not constructed shell commands. It is designed for a Cinnamon session, not a separate desktop login. It does not reserve screen area or replace Cinnamon panels. The launch list is currently capped at 40 sorted entries; search is not implemented. Styling/colors and positioning are preliminary, and the dock does not yet support magnification or customizable pinned icons.

### 4.2 Verified remote CI evidence
GitHub commit head / latest associated workflow runs inspected 2026-11-17:
- PR #1 head `ecf227400b1d6a3b3995f64d34814ecdd3761340`: Documentation checks run **44241921860**, completed SUCCESS.
- PR #2 head `6bad39f4eb1fa7c8f408d9390014458db06db6f5`: Python unit tests run **44242300082**, documentation checks **44242300075**, both completed SUCCESS.
- PR #3 head `7db803158ccabd95602b35323852f88c15bcfb60`: Python unit tests run **44242957886**, documentation checks **44242957966**, both completed SUCCESS. Fetching #3 job details confirmed `Run tests` and `Verify baseline` steps each concluded SUCCESS.
- All three PRs were OPEN DRAFT and unmerged when checked. These CI results are specific to those SHAs, **not automatically evidence for newer commits**.
- Linux Mint graphical smoke test: **NOT RUN**. PyGObject GTK behavior: **NOT RUN** in a Linux display here. X11/Wayland, NVIDIA/AMD/Intel, HiDPI, multiple monitors, sleep/wake, accessibility interactions, memory and CPU benchmarks: **NOT RUN**.
- Build artifact, installer, working session, complete menu icon, ready-to-ship shell: **NOT IMPLEMENTED**.

### 4.3 Review risks that need engineering inspection
These are review targets, not verified defects:
1. `canopy/classic_gtk.py`: GTK positioning and window hints may behave differently on Cinnamon/X11 vs Wayland; monitor-origin handling and hardcoded 400px dock need actual tests.
2. GTK preview's `set_keep_above`/DOCK hint can overlap existing Cinnamon UI; avoid installing or enabling autostart before tests.
3. App discovery list truncated at 40 and has no query/search, keyboard navigation review, accessible labels or dynamic monitoring.
4. Hardcoded desktop-file IDs may not exist on different Mint releases; avoid blank dock; support icon discovery and settings.
5. Current profile policy uses arbitrary prototype thresholds, no measured load/power inputs and no actual GTK binding to feature settings.
6. JSON settings: inspect symlink/path safety, directory mode if pre-existing, file permissions, interrupted-write behavior, corruption recovery, schema migration and concurrent writes before production usage.
7. Add GUI smoke tests under Xvfb or other suitable automation after selecting toolkit; human Cinnamon smoke test still required.
8. Check desktop-session requirements before committing to GTK3 as final architecture. A floating GTK preview is not proof of a replacement desktop shell.
9. CI's docs check tests only presence/phrase, not cross-document accuracy; add doc consistency checks and lint/test coverage as needed.
10. License file and third-party artwork provenance remain to be decided before public release; do not assume assets are libre.

## 5. Recommended engineering sequence

**Immediately (Codex takeover):** Read `AGENTS.md`, this entire file, existing docs, full Git log, current open PRs/CI; inspect code, run unit tests and syntax checks. Generate objective PASS/FAIL/BLOCKED/NOT RUN evidence. Do not implement parallel duplicate settings engines. Resolve any unsafe incomplete work through tests and root causes.

**First visible user-facing improvement:** Strengthen the GTK3 preview in a focused branch without claiming a full desktop. Add an original, copyright-safe white silhouette Tux menu icon as an SVG created from original shapes (not copied from Apple's logo or other proprietary images); make the dock adapt to contents/monitors; improve app launcher search and keyboard usability; bind cosmetic settings to visible behavior. Add tests for pure model logic, safe GUI smoke testing, and docs. Do not invent assets if source authoring is impractical—document as BLOCKED.

**Architectural decision:** Write a substantive comparison ADR for (A) Cinnamon applet/extension approach, (B) own desktop-shell/compositor architecture, and (C) alternative reusable compositor/session foundation. Evaluate lightweight resource profile, Linux Mint versions, session fallback, Wayland/X11/XWayland, global menus, file manager, accessibility, installation, desktop completeness and maintenance burden. Recommend a prototype-backed direction; record tradeoffs and unsupported features. Avoid conflating "macOS-inspired appearance" with a working desktop shell.

**Then:** Installable test package and reproducible developer setup; safe preview and backup path; user-level session prototype with Cinnamon fallback; full top bar/dock/launcher and keyboard integration; shared settings UI and real performance telemetry; independent QA; later Modern via presentation abstraction. Do not prematurely declare 0.1 alpha complete.

## 6. Local and CI verification matrix

| Check | Command or method | Baseline |
|---|---|---|
| Python unit tests | `python3 -m unittest discover -s tests -v` | GitHub CI passed on PR #3 SHA |
| Python syntax | `python3 -m compileall -q canopy tests` | Prior local compile claim; rerun on fresh checkout |
| GTK availability | `python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk"` | NOT RUN on Mint |
| GTK preview | `python3 -m canopy.classic_gtk` inside Cinnamon | NOT RUN |
| Safe exit | Canopy menu → Quit preview; ensure Cinnamon unaffected | NOT RUN |
| Launcher behavior | Buttons open desktop apps; missing IDs gracefully omitted | NOT RUN |
| Hardware / scaling | Different monitors, HiDPI, X11 and Wayland | NOT RUN |
| Accessibility | Keyboard, screen reader, reduced motion | NOT RUN |
| Runtime performance | baseline memory, CPU, startup and resource changes | NOT RUN |
| Login session | selectable session with Cinnamon fallback and rollback | NOT IMPLEMENTED |

Do not interpret remote CI as a Mint visual acceptance test. Record exact distro versions, display backend, hardware, commands, runtime traces and before/after measurements once available. Include both normal and negative/error paths.

## 7. Git rules / agent coordination

Before writing, query current upstream PR state. Use a unique feature branch from current reviewed head; keep PRs reviewable and focused. Avoid conflicting edits to shared docs or core files among agents. If multiple agents can work simultaneously, allocate independent owned files and integrate deliberately. For failures, capture reproduction, root cause, fix, regression test and verification. Push only locally checked code and verify CI/remote SHA; draft PR until ready. Do not automatically merge main or reorganize PR stack without checking change scope and approvals. Do not force push, delete unknown branches, install packages on user's machine, enable session autostart, or spend money without approval.

Ponytail integration requires reading official `README.md`, `INSTALL.md`, and `skills/ponytail/SKILL.md` as available and verifying exact Codex-compatible project installation in a clean session; audit added instructions/hooks and resolve conflicts. Preserve existing master rules; avoid copying unreviewed scripts.

## 8. Definition of done / required concise status report

A task is only DONE with code, applicable tests, regression, documentation, tracked commit, remote branch, CI status and limitations. At each checkpoint output:
- Branch, commits, draft PR URL, concise feature summary.
- Exact PASS / FAIL / BLOCKED / NOT RUN evidence (commands / workflow links).
- Resource impact, security and accessibility impact (or explicitly NOT RUN).
- Files changed, docs updated, next non-overlapping task and remaining risks.

Avoid repeat explanations or re-reading static documents every micro-step; first read thoroughly, then use the handoff/checkpoints to conserve tokens. Do not conceal missing verification.

## 9. Exact continuation instruction for Codex

**Read every project document fully, beginning with AGENTS.md and CODEX_START_HERE.md. Inspect all current branches, PRs and CI before work. Continue from the latest safe descendant of the existing prototype; preserve and extend code rather than rebuilding it. Focus first on the macOS-inspired Canopy Classic preview while protecting one reusable core for future Canopy Modern. Implement focused code, run tests, fix root causes, record performance/security/accessibility impact, update all cumulative docs, commit/push verified changes to feature branches, and create draft PRs. Do not merge main or make irreversible, chargeable or privileged changes without authorization. Never claim a usable desktop shell until verified on Linux Mint. Continue autonomously until genuinely blocked or session ends.**

## 10. Verified continuation checkpoint, 2026-11-18

PR #2 was retargeted to `docs/initial-project-foundation` after confirming that branch is an ancestor of its head. Its diff now has nine files and 208 added lines. PR #1 through #8 remain open drafts. PR #9 adds a temporary settings recovery launch, PR #11 synchronizes the settings directory, PR #12 completes launcher keyboard actions, and PR #13 fixes an opaque dock background artifact. These PRs form a descendant chain ending at `fix/classic-dock-window-background` commit `e68ea5d`. All six checks on PR #13 passed when inspected. PR #10 is a separate draft based on PR #8 for the project-scoped Ponytail skill. Its checks passed, but fresh Codex skill discovery is unverified. Inspect current heads and checks before using either branch. [PR #2](https://github.com/DevTunaSoft/Canopy/pull/2) · [PR #9](https://github.com/DevTunaSoft/Canopy/pull/9) · [PR #10](https://github.com/DevTunaSoft/Canopy/pull/10) · [PR #11](https://github.com/DevTunaSoft/Canopy/pull/11) · [PR #12](https://github.com/DevTunaSoft/Canopy/pull/12) · [PR #13](https://github.com/DevTunaSoft/Canopy/pull/13)

Debian 13 GTK3/Xvfb passed the 20-test Classic preview suite on PR #13's code. Screenshots exposed white corners on the dock window without a compositor, and a second capture confirmed they were removed. Neither screenshot tests Cinnamon or a composited display. An environment check found no Mint image, Cinnamon session, usable VM, or container service here. Target Mint, accessibility, graphics hardware, and a selectable login session remain unverified. See the chronological development log and ADR-003 for exact scope and preliminary resource measurements.
