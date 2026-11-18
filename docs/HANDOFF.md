# Canopy master handoff — initial foundation

**Purpose:** Make Linux feel familiar to people coming from macOS, later Windows, without building a new operating system. Tagline: The Familiar Feel. The Freedom of Linux.

**Decisions:** Linux Mint first, install alongside Cinnamon; Classic first, Modern later; one shared core; original branding and Tux silhouette; five manual profiles plus Auto Mode and user overrides; polkit prompts for administrative actions; safe fallback; no proprietary app icons.

**Engineering:** Clean modular low-memory code, autonomous feature-branch work, draft PRs, green-only commit/push, no unauthorized main merges, independent tests, root-cause regression fixes, full traceability, thorough living documentation and evidence-backed status. Ponytail may supplement but not replace instructions.

**Verified status:** Documentation-only foundation. No desktop session, implementation, hardware test or runtime benchmark has been completed.

**Next:** Choose license, compositor, toolkit and Mint target via ADRs; establish CI; prototype recoverable unprivileged session; implement shared settings and Classic UI; add tests and resource evidence.

**Update protocol:** Every meaningful PR must record decisions, code changes, commands and outcomes, failed tests/root causes, open risks and exact next steps here.

## 2026-11-17 checkpoint: Classic preferences prototype
Branch: `feat/classic-preferences-on-foundation`. Shared `canopy/preferences.py` supports Classic/Modern layout identifier, five profile values, caller-supplied Auto Mode pressure signals, cosmetic Auto/On/Off overrides, reduced-motion safety, validated JSON and atomic user-level persistence. `tests/test_preferences.py` contains eight unit tests; local command `python -m unittest discover -s tests -v` passed. GitHub CI and real Mint tests NOT RUN as of checkpoint. No UI or working session. See `docs/ADR-001-SETTINGS.md` and `docs/CLASSIC-DEV-LOG.md`. Next: compositor/toolkit ADR, recoverable Cinnamon-alongside session, Classic UI.
