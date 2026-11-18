# Classic development log

## 2026-11-17 — Shared preferences prototype
- Added a reusable layout selector, five profile names, Auto Mode policy and cosmetic Auto/On/Off overrides.
- Added strict schema validation and atomic user-level JSON persistence.
- Reduced-motion accessibility takes precedence over optional visual effects.
- Local prototype validation: `python -m unittest discover -s tests -v` — PASS, 8 tests, Python standard library.
- GitHub CI: NOT RUN at time of writing; real Linux Mint session: NOT RUN; resource benchmark: NOT RUN.
- Limitations: No UI, dock, top bar, compositor, hardware metrics collection or working session yet. This is a shared core prototype, not a desktop.
- Next: select compositor/toolkit through documented ADR; build a selectable session alongside Cinnamon, then Classic top bar and dock.
