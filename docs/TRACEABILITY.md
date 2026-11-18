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
