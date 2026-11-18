# Requirements traceability

All items below are PLANNED, not verified. Add code locations, tests, CI links and evidence as implementation progresses.

| ID | Requirement | Target | Status |
|---|---|---|---|
| R01 | Mint session with Cinnamon fallback | 0.1 | PLANNED |
| R02 | Classic top bar, original Tux menu, dock and launcher | 0.1 | PLANNED |
| R03 | Shared configuration and layout APIs | 0.1 | PLANNED |
| R04 | Five manual performance profiles | 0.1 | PLANNED |
| R05 | Auto Mode and safe feature overrides | 0.1 | PLANNED |
| R06 | Secure privilege authorization | 0.1 | PLANNED |
| R07 | Safe installation, removal and crash recovery | 0.1 | PLANNED |
| R08 | Automated tests and resource benchmarks | 0.1 | PLANNED |
| R09 | Accessibility and system integration | 0.2 | PLANNED |
| R10 | Migration assistant | 0.3 | PLANNED |
| R11 | Windows-inspired Modern layout | Later | PLANNED |

## Prototype evidence (2026-11-17)
R03: Shared settings and layout selector IMPLEMENTED (prototype), local 8 unit tests PASS; Mint integration NOT RUN. R04/R05: five profile identifiers, Auto Mode cosmetic policy and overrides IMPLEMENTED (prototype); actual hardware monitoring and benchmarks NOT RUN. See `canopy/preferences.py`, `tests/test_preferences.py`, `docs/ADR-001-SETTINGS.md` and `docs/CLASSIC-DEV-LOG.md`.

## Classic preview evidence
R02: Partially IMPLEMENTED — experimental GTK3 top bar, menu, dock, app list in `canopy/classic_gtk.py`; original Tux icon, complete desktop session and real hardware testing remain PLANNED. Pure app model tests: 3 PASS locally; graphical GTK/CI: NOT RUN at commit time. R01: NOT IMPLEMENTED as a selectable login session (prototype runs inside Cinnamon). See ADR-002.

## Searchable launcher evidence (2026-11-18)

R02/R09: `canopy/applications.py` and `canopy/classic_gtk.py` supply filterable app discovery, named controls and keyboard selection. `tests/test_classic_gtk.py` verifies focus and activation with GTK3 under Xvfb. R06: preview startup rejects effective UID 0. R08: the Python workflow now includes a GTK/Xvfb job. Screen-reader, Cinnamon and hardware acceptance remain open.

## Dock startup evidence (2026-11-18)

R02/R07/R08: `test_preview_places_compact_dock_without_default_apps` launches the actual preview using GTK3 and verifies geometry and cleanup with an empty app catalog. The model test checks offsets and undersized work areas. Cinnamon, dynamic monitor changes and Wayland placement still require verification.

## Classic menu emblem evidence (2026-11-18)

R02/R09: The Classic menu displays `canopy/assets/classic-penguin.svg`, an original drawing. The GTK smoke test verifies the image and accessible name. Screen-reader and scaled-display checks on Mint remain open.

## Preview recovery evidence (2026-11-18)

R03/R07/R08: `canopy/preferences.py` resolves the XDG path and rejects invalid version types. `canopy/classic_gtk.py` exposes a temporary recovery launch and disposes windows after startup failures. `tests/test_preferences.py` and `tests/test_classic_gtk.py` cover the path, preserved corrupt bytes and a forced Gio failure. Settings migration, backup and Cinnamon recovery remain open.

## Settings save durability evidence (2026-11-18)

R03/R07/R08: `save()` synchronizes the temporary file and its parent directory after replacement. `test_save_syncs_file_and_containing_directory` verifies both descriptor types. Parent directory creation durability and concurrency remain open.

## Launcher keyboard evidence (2026-11-18)

R02/R09: `test_search_enter_and_escape` checks Enter with and without a result and Escape from the search field under GTK3/Xvfb. Cinnamon keyboard and screen-reader checks remain open.

## Classic dock configuration evidence (2026-11-18)

R02/R03/R07/R08/R09: `canopy/preferences.py` accepts version 1 settings and stores validated version 2 Classic pins with locked updates that preserve concurrent non-pin edits. `canopy/classic_gtk.py` provides an Edit dock dialog and bounded pinned-app scroller with an Apps entry. Tests cover migration, conflict rejection, corrupt settings, menu persistence and a 320px Xvfb monitor. Linux Mint and real multi-process behavior remain open.

## Test-lab automation checkpoint (2026-11-18)

R08 partial prototype: `scripts/mint_testlab.py` executes fixed commands and records PASS/FAIL/BLOCKED JSON; `tests/test_mint_testlab.py` provides unit regression tests. This is not a functioning remote Mint environment. Mint graphical acceptance, screenshot capture, VM provisioning and hardware benchmarks remain NOT RUN.
