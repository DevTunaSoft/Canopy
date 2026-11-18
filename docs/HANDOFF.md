# Canopy master handoff — initial foundation

**Purpose:** Make Linux feel familiar to people coming from macOS, later Windows, without building a new operating system. Tagline: The Familiar Feel. The Freedom of Linux.

**Decisions:** Linux Mint first, install alongside Cinnamon; Classic first, Modern later; one shared core; original branding and Tux silhouette; five manual profiles plus Auto Mode and user overrides; polkit prompts for administrative actions; safe fallback; no proprietary app icons.

**Engineering:** Clean modular low-memory code, autonomous feature-branch work, draft PRs, green-only commit/push, no unauthorized main merges, independent tests, root-cause regression fixes, full traceability, thorough living documentation and evidence-backed status. Ponytail may supplement but not replace instructions.

**Verified status:** Documentation-only foundation. No desktop session, implementation, hardware test or runtime benchmark has been completed.

**Next:** Choose license, compositor, toolkit and Mint target via ADRs; establish CI; prototype recoverable unprivileged session; implement shared settings and Classic UI; add tests and resource evidence.

**Update protocol:** Every meaningful PR must record decisions, code changes, commands and outcomes, failed tests/root causes, open risks and exact next steps here.

## 2026-11-17 checkpoint: Classic preferences prototype
Branch: `feat/classic-preferences-on-foundation`. Shared `canopy/preferences.py` supports Classic/Modern layout identifier, five profile values, caller-supplied Auto Mode pressure signals, cosmetic Auto/On/Off overrides, reduced-motion safety, validated JSON and atomic user-level persistence. `tests/test_preferences.py` contains eight unit tests; local command `python -m unittest discover -s tests -v` passed. GitHub CI and real Mint tests NOT RUN as of checkpoint. No UI or working session. See `docs/ADR-001-SETTINGS.md` and `docs/CLASSIC-DEV-LOG.md`. Next: compositor/toolkit ADR, recoverable Cinnamon-alongside session, Classic UI.

## 2026-11-17 — GTK Classic UI prototype checkpoint
- Branch `feat/classic-gtk-preview`, based on `feat/classic-preferences-on-foundation`, itself based on `docs/initial-project-foundation` (stacked draft PR dependency; avoid duplicate merges).
- `canopy/classic_gtk.py` adds optional GTK3 preview windows; `canopy/classic_model.py` isolates pure, tested display logic; `tests/test_classic_model.py` provides 3 unit tests.
- Local model test results: 3 PASS; Python compileall PASS. GTK runtime unavailable in this execution environment, so GUI, Cinnamon and hardware tests NOT RUN. The parent preference tests were not rerun locally against the combined tree; use GitHub CI.
- Limitations: no real desktop session; text placeholder instead of final white Tux; no actual reserved top-bar space; no global menu; no verified multi-monitor positioning; no compositor. See `docs/ADR-002-CLASSIC-PREVIEW.md` and `docs/CLASSIC-PREVIEW.md`.
- Next priority: CI verification, real Mint prototype smoke test, compositor and packaging ADR, shared accessibility/visual assets; keep Cinnamon fallback. Never merge main without explicit approval.

## 2026-11-17 — Codex takeover audit

Canonical full audit: `CODEX_START_HERE.md`. Master 16-rule mandate: `docs/MASTER_AUTONOMOUS_PROMPT.md`. Current feature status: `docs/FEATURE_STATUS.md`. Chronological product decisions: `docs/ENGINEERING_DECISIONS.md`. PRs #1/#2/#3 are open draft and unmerged, with stacked dependencies (PR #2 includes PR #1 against main; PR #3 targets PR #2). GitHub Actions for audited head SHAs: PR #1 docs SUCCESS, PR #2 unit/docs SUCCESS, PR #3 unit/docs SUCCESS. Linux Mint UI/hardware, accessibility and resource tests remain NOT RUN. Ponytail not installed/verified. Takeover docs isolated on branch `docs/codex-takeover-dossier`, derived from PR #3 branch. Begin Codex work only after fetching live Git and inspecting PR state.

## 2026-11-18 — Classic application search

`feat/classic-app-search` is based on the dossier head `24b996f`. Classic now searches installed visible desktop entries by name and ID, including entries beyond the former 40-app cap. Discovery and search live in the shared application module. Debian 13 GTK3/Xvfb passed all 14 tests. See the development log and preview guide for scope and test evidence. Continue with Cinnamon smoke testing and responsive dock placement, followed by the session architecture ADR. Preserve the stacked PRs.

## 2026-11-18 — Dock startup and placement

`feat/classic-dock-placement` builds on draft PR #5. GTK/Xvfb tests now cover preview startup without any default apps and compact dock coordinates. The preview uses the primary work area at startup and cleans up both windows and the clock timer on exit. Next, verify work-area behavior on Cinnamon/X11 and examine Wayland placement before deciding on a longer-term integration strategy.

## 2026-11-18 — Classic menu emblem

`feat/classic-menu-emblem` adds the original white penguin SVG, an accessible menu name and text fallback. GTK3/Xvfb verifies the asset loads in the preview. Screen-reader and target Mint appearance checks remain open alongside the session architecture evaluation.

## 2026-11-18 — Session architecture evaluation

ADR-003 records the Cinnamon-first evaluation path, a separate Labwc-backed candidate, and the cost of an independent compositor. It includes a Debian/Xvfb process sample and explicit decision gates. The next acceptance step requires a disposable Linux Mint Cinnamon target. No production session choice has been made.

## 2026-11-18 — Preview settings recovery

`feat/classic-safe-startup` follows the session evaluation branch. The preview now reports bad settings and can start with temporary built-in defaults through `--safe-defaults`. It leaves the stored file unchanged. GTK startup failures dispose created windows and the clock timer. Debian GTK3/Xvfb passed 18 tests. Mint session acceptance remains open.

## 2026-11-18 — Settings directory synchronization

`fix/settings-directory-sync` follows draft PR #9. The shared settings writer synchronizes its containing directory after atomic replacement. A targeted test confirms file and directory `fsync` calls. New parent directory durability, backup, migration and simultaneous writer policy remain open.

## 2026-11-18 — Launcher keyboard completion

`feat/classic-launcher-keyboard` follows draft PR #11. Search supports Enter to launch the first match, Escape to close, and Down to move into results. Debian GTK3/Xvfb passed 20 tests. Cinnamon keyboard and screen-reader acceptance remains open.

## 2026-11-18 — Dock window background

`fix/classic-dock-window-background` follows draft PR #12. The dock window uses an opaque matching background without a compositor and an RGBA visual when compositing is available. Debian/Xvfb screenshots confirmed removal of the white corners. Cinnamon and composited appearance remain open.

## 2026-11-18 — Configurable Classic dock

`feat/classic-pinned-dock` is based on draft PR #13. Schema version 2 accepts version 1 settings, and the preview's Edit dock dialog saves a validated pin list through a shared locked update. The dock scrolls horizontally within the work area and keeps Apps accessible. Debian GTK3/Xvfb tests cover the editor and 320px display. Cinnamon testing, backup and explicit pin reordering remain open. Draft PR #2 now targets the foundation branch, reducing its duplicated diff.

## 2026-11-18 — Unattended test-lab runner checkpoint

Branch `feat/mint-testlab-runner` based on `feat/classic-pinned-dock` (PR #15), preserving all preceding Classic prototype changes. Adds `scripts/mint_testlab.py`, `tests/test_mint_testlab.py`, `docs/MINT-TEST-LAB.md`, ignores generated test results. Fixed allowlisted subprocess arguments, 120-second default timeout per check (max 900), bounded logs, JSON results with PASS/FAIL/BLOCKED. No root, package install, host VM control, arbitrary command execution or self-hosted runner configuration. A Mint VM has NOT been connected, real Cinnamon tests remain NOT RUN. Review CI results for the new head SHA before asserting green. Next: safe standalone Mint VM with approved-commit private workflow and screenshot/GUI tests.

## 2026-11-18 — Isolated visual evidence automation
Branch `feat/mint-testlab-visual-evidence` builds on PR #16 without duplicating Mint runner logic. New `scripts/capture_classic.py` captures precisely the two Canopy GTK preview windows under an isolated Xvfb display, with short-lived CI artifacts; `tests/test_capture_classic.py` verifies capture boundary, allowed test-display guard and invalid states. CI job includes an opt-in test-only screenshot capture, not a remote-control channel. Graphical Linux Mint Cinnamon, full session test, real VM provisioning, snapshot/reset and performance benchmarks remain NOT RUN. Consult `docs/MINT-TEST-LAB.md`, CI workflow and PR for actual evidence. Never merge main without authorization.
