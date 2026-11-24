# Canopy — Master Handoff

This document is the entry point for any developer continuing Canopy. It
supplements, and does not replace, `AGENTS.md`, `README.md`,
`docs/ARCHITECTURE.md`, `docs/QUALITY.md`, and the draft PRs listed below.

## Repository

- Repository: `DevTunaSoft/Canopy`
- Default branch: `main`
- Primary implementation branch: `feat/windows-multi-agent-supervisor-20261121`
- Classic Qt implementation branch: `feat/classic-qt-port-buildable-20261121`
- All work is preserved as draft pull requests; nothing has been merged to `main`.

## Current development status

Canopy has two substantial, verified implementation tracks in draft PRs:

1. **Multi-agent supervisor** — PR #135.
   - `canopy_supervisor/` package, CLI, state store, Git/GitHub operations,
     policy, worker launcher, roadmap and tests.
   - 82 supervisor tests pass; full applicable suite passes on Windows after
     isolation of POSIX-only tests.
   - Autonomous scheduling, recovery, evidence gates and draft-PR publishing are
     implemented and exercised.

2. **Classic Qt desktop** — PR #151.
   - Real Qt 6/QML prototype with approved eight-icon dock, exact SHA-locked PNG
     masters, C++ rounded dock icon provider, Files browser, shell menus,
     launcher GIO bridge, responsive layouts, keyboard/accessibility checks.
   - GitHub Actions compile and runtime evidence passes, including real
     three-resolution screenshots and a five-minute idle CPU/PSS sample.
   - PR remains draft pending owner visual approval and Linux Mint acceptance.

## Completed work

- Shared Shell Host/event contracts and Shell Pack metadata tools.
- Classic Qt build/runtime evidence and source-level regression tests.
- Supervisor state, locking, leases, recovery, evidence validation, publishing.
- 100-task engineering backlog and bounded retry/backoff.
- Safe user-level preview packaging and Mint guest runtime runner (blocked on
  guest prerequisites).
- CI hardening: no skipped-only checks treated as green; required checks.

## Unfinished work

- Owner visual approval of compiled Qt screenshots.
- Linux Mint guest runtime acceptance (VM currently powered off, no Guest
  Additions, no SSH key, no compiled binary in guest).
- Approved alpine/autumn wallpaper asset (historical blue wave only exists).
- Integration of stacked Qt PRs onto current `main`.
- Functional depth beyond prototype: real file system integration, window
  manager integration, app launching in a real session.

## Known blockers

- `Canopy-Test-Mint` VM UUID `fbf69438-6729-47d4-897f-2ff1473b02a3` is
  powered off; no Guest Additions or SSH credentials are available.
- Eight approved PNG masters are now committed in PR #151, but the alpine
  wallpaper asset is missing.
- Owner visual approval has not been granted.

## Next engineering actions

1. Review PR #135 and PR #151.
2. Provide the alpine wallpaper asset and owner visual signoff.
3. Prepare the Mint VM with Guest Additions and an SSH key.
4. Rebase verified Classic Qt work onto `main` after review.
5. Run Linux Mint acceptance and five-minute resource measurements in a guest.

## Safety

No secrets were committed. Supervisor state, logs, and worktrees are local and
must not be committed. PRs remain draft; no automatic merge is authorized.
