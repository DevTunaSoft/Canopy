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

## 2026-11-18 — Preview startup and dock placement

- Launcher draft PR #5 passed [unit and GTK jobs](https://github.com/DevTunaSoft/Canopy/actions/runs/44245511113) and [docs](https://github.com/DevTunaSoft/Canopy/actions/runs/44245511062) at `e148290`.
- A new full-preview smoke test exposed a startup failure when a default desktop ID was absent. PyGObject raises `TypeError` when `DesktopAppInfo.new()` returns NULL. The dock now matches its pinned IDs against installed Gio entries, omitting missing entries and retaining the Apps button.
- GTK sizes the dock from its contents. Startup placement centers it above the bottom of the primary monitor's work area, including nonzero origins, and places the top bar at that work area's upper edge. Preview exit removes the clock timer and destroys both windows.
- **PASS** Debian 13 GTK3/Xvfb, 16 tests, including startup with no pinned apps, measured geometry, and window cleanup. Cinnamon panel interaction, changes to monitor layout after startup, Wayland placement and resource measurements remain **NOT RUN**.

## 2026-11-18 — Original Classic menu emblem

- Drew `canopy/assets/classic-penguin.svg` from original paths for the white penguin menu mark. No external artwork imported. The GTK button has a stable accessible name and keeps its text fallback when the image cannot be loaded.
- **PASS** Debian 13 GTK3/Xvfb, 16 tests. The preview smoke test confirms the named menu control loads a 20 px image. An initial smoke run caught a PyGObject error caused by clearing the button label with `None`. The button now starts empty and receives a label only for the fallback.
- Live screen-reader and scaled-display visual acceptance remain **NOT RUN**. Product artwork licensing remains part of the release review.

## 2026-11-18 — Session candidate comparison

- Draft PR #6 passed [unit and GTK jobs](https://github.com/DevTunaSoft/Canopy/actions/runs/44245759206) and [docs](https://github.com/DevTunaSoft/Canopy/actions/runs/44245759288). Draft PR #7 passed [unit and GTK jobs](https://github.com/DevTunaSoft/Canopy/actions/runs/44245920262) and [docs](https://github.com/DevTunaSoft/Canopy/actions/runs/44245920232).
- ADR-003 compares Cinnamon, independent compositor development and Labwc. Debian/Xvfb process measurements are recorded as preliminary evidence. Only a Mint trial can test the target login and recovery behavior.

## 2026-11-18 — Preview settings recovery

- Added a shared XDG settings path and strict version type validation. Classic startup reports invalid or unreadable settings and supports `--safe-defaults` for an in-memory recovery preview. The original settings file remains untouched.
- Covered GTK window and timer cleanup across startup failures. A regression test forces Gio discovery to fail and verifies that the preview windows are disposed.
- Local Debian 13 checks passed with 18 tests under GTK3/Xvfb, Python compilation and the documentation check. The regular Python environment passed 15 tests and skipped 3 graphical tests because PyGObject is unavailable there. Cinnamon and hardware tests remain open.
