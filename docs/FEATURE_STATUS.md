# Canopy feature status (as verified 2026-11-17)

Statuses: PLANNED = specified, no implementation; PROTOTYPE = code exists but target integration not verified; VERIFIED-CI = code with passing relevant CI (not graphical acceptance); NOT RUN = verification missing.

| Feature | Status | Evidence / boundary |
|---|---|---|
| Project foundation docs | VERIFIED-CI | PR #1 head ecf2274; documentation workflow success |
| Shared Classic/Modern preference identifier | VERIFIED-CI prototype | `canopy/preferences.py`, PR #2/#3 CI |
| Five profile identifiers | VERIFIED-CI prototype | No actual system performance enforcement |
| Auto Mode policy | VERIFIED-CI prototype | Caller-supplied flags only; no hardware monitoring |
| Three cosmetic Auto/On/Off overrides | VERIFIED-CI prototype | Not yet connected to GTK visuals |
| Reduced motion policy | VERIFIED-CI prototype | No system accessibility integration yet |
| Settings JSON validation / atomic replacement | VERIFIED-CI prototype | No migration/backup or full corruption recovery |
| GTK Classic top bar and local clock | PROTOTYPE | PR #3, GUI not tested on Mint |
| GTK dock / Gio launch buttons | PROTOTYPE | Fixed desktop IDs, no drag/reorder or visual verification |
| GTK applications menu | PROTOTYPE | First 40, no search or accessibility review |
| White original Tux menu icon | PLANNED | Text placeholder remains |
| Dock customization/animations | PLANNED | Nothing wired to profile policy |
| Windows-inspired Modern UI | PLANNED | Shared layout enum only |
| Global menu / true window-management | PLANNED | Compositor/session architecture undecided |
| Linux Mint selectable Canopy session | PLANNED | Preview is just a GTK process |
| Cinnamon fallback installer and rollback | PLANNED | Never alter existing session |
| Graphics/compositor ADR | PLANNED | GTK preview ADR is NOT a compositor choice |
| Accessibility + multimonitor + HiDPI tests | NOT RUN | Test on Mint hardware |
| Resource benchmarks | NOT RUN | Set budgets from actual measurements |
| First-run migration wizard | PLANNED | macOS/Windows guidance deferred |
| Secure updates/packages/release image | PLANNED | No installer package |
| Ponytail project installation | NOT RUN | No repo-local skill installed or discovery verified |

## Audit status

PR #1, #2 and #3 open draft, **unmerged** when checked. Head workflow runs were successful: #1 docs 44241921860, #2 Python 44242300082/docs 44242300075, #3 Python 44242957886/docs 44242957966. Passing CI covers current Python tests and documentation-presence checks only. No Linux Mint UI or hardware verification.

See `CODEX_START_HERE.md` for exact branch dependencies, inventory, risks, commands and takeover protocol.
