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

## 2026-11-17 Codex takeover checkpoint

See `CODEX_START_HERE.md` for dependency-safe branch guidance. Do not repeat completed preferences/preview tasks. First verify GTK startup on real Mint, address any confirmed defects and add GUI smoke coverage; implement original Tux menu artwork, responsive launcher/search and polish; prepare compositor/session ADR with alternatives and measured evidence. Modern remains future presentation on shared core. Current CI success does not prove a working desktop session.

## 2026-11-18 launcher checkpoint

The Classic preview now supports shared application search, keyboard selection and a headless GTK launcher smoke test. Next priorities are verified Cinnamon behavior, responsive dock placement, original menu artwork and the session architecture ADR.

The Classic dock now sizes to its contents and uses the primary monitor's work area at startup. Verify the result with a Cinnamon panel in place and cover monitor changes before considering login-session integration.

The Classic preview supports a temporary settings recovery launch. Follow with a versioned backup and migration design after target Mint testing establishes the settings location and session lifecycle.

The Classic preview now stores user-selected dock pins in shared version 2 settings and bounds the dock on a narrow display. Next acceptance work includes Cinnamon behavior, explicit pin ordering, safe settings backup and a production session decision.

## 2026-11-18 — Mint test-lab controller increment

Added a non-destructive, unprivileged Python runner for approved Linux Mint VM checkouts, with unit, syntax and Xvfb GTK checks, timeouts and machine-readable JSON evidence. It does not provision a VM, perform live Cinnamon testing or install a self-hosted runner. See `docs/MINT-TEST-LAB.md`. VM setup, screen capture, real Mint integration and snapshot restoration remain pending.
