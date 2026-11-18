# Classic development log

## 2026-11-17 — Shared preferences prototype
- Added a reusable layout selector, five profile names, Auto Mode policy and cosmetic Auto/On/Off overrides.
- Added strict schema validation and atomic user-level JSON persistence.
- Reduced-motion accessibility takes precedence over optional visual effects.
- Local prototype validation: `python -m unittest discover -s tests -v` — PASS, 8 tests, Python standard library.
- GitHub CI: NOT RUN at time of writing; real Linux Mint session: NOT RUN; resource benchmark: NOT RUN.
- Limitations: No UI, dock, top bar, compositor, hardware metrics collection or working session yet. This is a shared core prototype, not a desktop.
- Next: select compositor/toolkit through documented ADR; build a selectable session alongside Cinnamon, then Classic top bar and dock.

## 2026-11-17 — Non-disruptive first UI preview
- Implemented `canopy.classic_gtk`: GTK3 top bar, Canopy menu, time label, small dock, Gio AppInfo-backed launcher, no shell subprocesses.
- Added `canopy.classic_model` and three unit tests for clock, visible app sorting/deduplication, dock IDs.
- Local command `PYTHONPATH=. python -m unittest discover -s tests -v` on the **new module tests only**: PASS 3/3. `python -m compileall -q canopy tests`: PASS.
- Local Python GI/GTK import: NOT AVAILABLE; live UI and Linux Mint compatibility NOT RUN. Parent preference tests not executed in the same local workspace; GitHub CI is required for combined coverage.
- New docs: ADR-002 and CLASSIC-PREVIEW. No session, compositor, Tux vector art or packaged installer yet.
- Next: verify combined remote CI; review Linux Mint visual behavior; decide session/compositor architecture via ADR; implement original assets and accessibility.

## 2026-11-18 — Searchable Classic launcher

- Started from `24b996f` on the takeover dossier branch. Reviewed the six remote branches, four open draft PRs and 57 completed workflow runs. The takeover head passed Python run 44244355275 and docs run 44244355246.
- Replaced the first-40 applications popup with a scrollable GTK search dialog. `canopy/applications.py` keeps discovery, sorting and name/ID matching available to future layouts. Activation still uses Gio desktop entries. The preview rejects root before GTK initialization.
- Debian 13 GTK3 under Xvfb: **PASS**, 14 tests via `/usr/bin/python3 -m unittest discover -s tests -v` with the virtual display set. The smoke test checks an app beyond the old cap, empty results, focus transfer and row activation. The initial smoke failed because the fixture assumed the dialog content area contained exactly two widgets. It now finds widgets by type. Added a dedicated Xvfb check in the existing Actions workflow.
- Linux Mint/Cinnamon, screen readers, Wayland, multimonitor, real app launch and resource benchmarking remain **NOT RUN**. The launcher builds rows on demand when opened and adds no background service or dependency to the preview.
