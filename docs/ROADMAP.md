# Canopy roadmap

- **Phase 0:** specifications, license choice, architecture decision records, CI, test matrix and resource baseline strategy.
- **Phase 1 / 0.1 Alpha:** selectable Linux Mint session alongside Cinnamon; Classic top bar, Tux menu, dock, launcher, shared settings, five profiles, Auto Mode, overrides, rollback and tests.
- **Phase 2:** everyday desktop integration, accessibility, multi-monitor, sleep/wake, packaging, updates, real hardware QA.
- **Phase 3:** guided macOS/Windows migration experience, familiar shortcuts and app alternatives.
- **Phase 4:** Windows-inspired Modern layout reusing the shared core.
- **Later:** dedicated installer image and additional layouts only after reliable daily-driver readiness.

Every milestone needs acceptance tests, regression coverage, resource evidence, documentation and updated handoff. Status is planning, not implementation.

## Current progress
Shared preferences and cosmetic policy prototype implemented on `feat/classic-preferences-on-foundation`. Eight local unit tests passed. No desktop session or Linux Mint hardware verification yet. Next: compositor/toolkit ADR and Cinnamon-safe session prototype.

## Next UI checkpoint
Experimental GTK3 Classic top-bar/dock preview exists, but not a full session and not visually validated on Mint. Follow with Linux Mint smoke testing, compositor/session ADR, accessibility and final original Tux icon. Keep Modern on the shared core, not a second desktop service stack.
