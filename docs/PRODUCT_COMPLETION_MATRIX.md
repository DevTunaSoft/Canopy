# Canopy Classic product completion matrix

**Purpose:** convert accumulated standalone engineering into one verified desktop product. This matrix records maturity, not percent complete. Levels: L0 not implemented; L1 prototype/standalone; L2 functional component independently verified; L3 integrated into the compiled Qt runtime; L4 end-to-end desktop workflow verified; L5 real Linux Mint behavior verified; L6 release acceptance completed.

Source baseline: `integration/canopy-classic-20261123` @ `72b719a`. Evidence is exact-SHA where stated. Synthetic/offline results are not runtime or Mint acceptance.

| Feature | Current implementation | Level | Verified evidence | Blockers / next action | Workstream |
|---|---|---:|---|---|---|
| Classic Qt preview build | C++17/Qt6/QML prototype with approved-art hash checks, three resolution self-tests, dock alignment checks | L2–L3 | Compiled locally in 43 steps; Ubuntu CI compiles and runs Xvfb smoke test; `prototype/classic/README.md`, `docs/MINT_CLASSIC_QT_SMOKE.md` | Not a session; real Mint guest smoke and owner visual acceptance outstanding | A, D |
| Top bar / clock | QML clock with single-shot per-minute timer and accessible label | L3 (preview) | `tests/test_classic_clock.py`; compiled Qt self-test changes and restores QML date | No suspend/resume or full-session verification | A |
| Dock | Eight SHA-locked icons, geometry, running indication, focus/keyboard state modules | L3 (preview) / L2 (backend) | Compiled Qt self-test verifies image midpoints, spacing, bounds; Python dock modules have fail-closed regression tests | No live app state from real WM; protected geometry must not change | A |
| Launcher search and keyboard | QML overlay with case-insensitive filtering; Python ranking/casefold/navigation contracts | L3 (preview) / L2 (backend) | Compiled Qt smoke opens overlay and verifies search; 3000+ Python suite green at integration tip | Real desktop-entry discovery and app launch wiring remain outside preview | A |
| Files integration | Sample-folder Files window, keyboard open/close, local demo data only | L3 (demo) | Compiled Qt smoke verifies hide/restore; README explicitly states no disk browsing | Connect to real file manager or read-only model with user consent; no visual change | A |
| App discovery / launch intent | Desktop-entry parsing, argv validation, policy and launch outcome modules | L2 | Standalone unit and cross-field regression tests at integration tip | Not invoked by running desktop; real launch/focus unverified | A |
| Window management / focus | Capability negotiation, focus intents, workspace inventory, topology snapshots | L2 | Python contracts with regression coverage | No compositor/WM adapter; no compiled-runtime invocation | A |
| Workspace management | Bounded inventory and normalization models | L1–L2 | Unit tests only | No session-level workspace switching | A |
| Settings / configuration persistence | Theme/accessibility contracts and startup checkpoint models | L1–L2 | Unit tests; no durable user settings integration | Define shared state owner and persistence boundary | A |
| Notifications | Event contracts and bounded delivery/overflow modules | L2 | Standalone fail-closed tests | No desktop notification bridge or runtime check | A |
| Session lifecycle | Recovery readiness, rollback, lock/session and lifecycle snapshot modules | L2 | Standalone cross-field tests | No real login/logout/suspend/resume evidence | A, B |
| Display / monitor handling | Screen topology and monitor-change models | L2 | Standalone invariant tests | No compiled Qt signal or real hot-plug verification | A, B |
| Accessibility contracts | Contrast, text scale, reduced motion, shortcut conflicts, metadata/reflow validators | L2; L3 for labels in preview | Pure-Python contract suites; compiled Qt has accessible clock/launcher elements | No keyboard-only end-to-end or screen-reader session evidence; no visual asset changes allowed | A, D |
| Keyboard shortcuts | Conflict detection and shortcut intent models | L2 | Unit tests | No global shell binding verified in runtime | A |
| Linux Mint integration | Guest preflight, dependency probe, Qt plugin discovery, VBox readiness, acceptance summary | L2 | `docs/MINT_GUEST_PREFLIGHT.md`, `docs/MINT_CLASSIC_QT_SMOKE.md`; runner NOT yet executed in a real Mint guest | Real Mint VM acceptance, compositor/session integration, reversible registration | B |
| Install / uninstall / rollback | Dry-run plans, XDG paths, session entry validation, uninstall integrity | L2 | Fail-closed Python contracts | No actual install/uninstall or upgrade/rollback test | B |
| Performance / resource efficiency | Pure-Python allocation fixes, parsers and evidence gates | L1 evidence | `docs/performance-module-audit-20261123.md`: synthetic CPython measurements only | No shell-owned PSS/CPU, GPU, wakeup, startup or five-minute idle measurement | C, D |
| Reliability gates | 99 review questions, integrator/watchdog, exact-SHA PR verification | L2 process | `docs/RELIABILITY_99_GATE_AUDIT.md`; integration watchdog/monitor operational | Most gates are review questions, not completed tests | D |

## Highest-priority next actions

1. Convert compiled Qt preview into a launchable isolated Classic session with real app launch/focus and window state, without changing approved visuals.
2. Run the existing Mint smoke runner in a real Mint guest using verified approved-art inputs; record exact SHA, binary hash, and three screenshots, without claiming visual approval.
3. Build a reproducible combined Classic candidate from the integration branch and execute end-to-end workflows: launcher → app → focus → workspace → close → session recovery.
4. Measure actual shell-owned PSS, CPU, GPU proxy, wakeups and startup on that candidate; profile before optimizing.
5. Validate reversible install/uninstall and rollback in an isolated VM.

## Evidence rules

Record `PASS`, `FAIL`, `BLOCKED`, `NOT RUN`, `SKIPPED`, `SYNTHETIC`, `CI-SCOPED`, `RUNTIME VERIFIED`, or `MINT VERIFIED` exactly. Do not convert a unit suite, mock, screenshot, or green CI check into product acceptance. Preserve PR holds and protected visuals.
