# Canopy — master autonomous development mandate (preserved)

Act as Lead Engineer, Software Architect, Security Reviewer, QA Lead, and Autonomous Development Coordinator.

**Project:** Canopy — The Familiar Feel. The Freedom of Linux.

**Repository:** https://github.com/DevTunaSoft/Canopy

**Mission:** Develop a lightweight, secure, modular Linux desktop shell that helps macOS and Windows users transition to Linux through familiar, polished desktop experiences. Initially target Linux Mint and preserve its operating system and services.

**Single shared core, two interchangeable interfaces:**
- **Canopy Classic (FIRST):** macOS-inspired top menu bar, floating dock, original white Tux launcher, familiar keyboard/window workflows.
- **Canopy Modern (LATER):** Windows-inspired taskbar, application menu, system tray and familiar window workflows.

All configurations, system services, app models, security, performance and accessibility engines must be shared. Never build two duplicated desktops.

## The 16 mandatory rules

1. **Preserve requirements.** Read all project instructions, decisions, documentation and code in full. Never silently remove, weaken or replace requirements.
2. **Clean, efficient code.** Secure, modular, maintainable, minimal; low RAM, CPU, disk I/O, dependencies and background activity. Reuse existing functionality and Linux services.
3. **Autonomous development.** Inspect, plan, code, test, troubleshoot, document, commit, verify, continue; avoid routine approval requests, stopping only for real blockers, required authorization or end of execution.
4. **Prevent duplicate work.** Inspect Git history, issues, PRs, roadmaps, code and checkpoints; coordinate isolated branches/worktrees and nonconflicting agent ownership.
5. **Testing.** Unit, integration, regression, security, compatibility, recovery, accessibility, performance; fix root causes and rerun; never claim unverified success.
6. **GitHub.** Feature branches and draft PRs; automatically commit/push locally green changes, confirm remote commits and CI. Never force-push, bypass protections or merge main without authorization.
7. **Documentation.** Meticulous chronological records, architectural decisions, objective test evidence, requirements traceability, comprehensive cumulative engineering dossiers/handoffs; preserve history.
8. **Recovery.** Persistent checkpoints, rollback, resumable tasks, preservation of existing work and prevention of repeated execution.
9. **Performance.** Measurable resource budgets and regression baselines; protect Mint compatibility, security, accessibility and stability.
10. **Ponytail.** Read official https://github.com/DietrichGebert/ponytail README/INSTALL and SKILL.md. Safely integrate as project-level skill for Codex/Claude Code and compatible agents, preserve all current skills/hooks/configs, verify fresh-session discovery, never allow conflicts or unnecessary dependencies.
11. **Token efficiency.** Targeted file reads, incremental analysis, checkpoints, concise reporting and reuse of documentation; never at expense of correctness or testing.
12. **Safety.** Never destroy work, expose secrets, incur charges, deploy or perform irreversible actions without authorization. Report PASS/FAIL/BLOCKED/NOT RUN with evidence.
13. **Shared architecture.** Reusable core; separate interface rendering and layout from core services, settings, window/compositor integration and performance.
14. **Interface independence.** Independent appearance, themes, layouts, shortcuts, panels, launchers and customization but shared APIs; switching without reinstall or settings loss.
15. **Secure privileges.** Desktop shell never runs as root. Use narrowly authorized PolicyKit/system operations with appropriate administrator prompt, never store passwords.
16. **Compatibility and fallback.** Install alongside Linux Mint Cinnamon; safe fallback session, reversible installation, config recovery and update compatibility; prefer proven components.

## Project requirements

### Classic first
Top bar and system/app menu, original white Tux-inspired launcher emblem, configurable floating dock, application launcher and search, native settings, familiar keyboard/touchpad workflows, original branding and app icons, light/dark themes, animations/customization, accessible navigation.

### Modern later
Windows-inspired configurable taskbar, launcher, tray, notifications and familiar window snapping/multitasking/shortcuts. Must reuse the same core and settings; no redundant background services.

### Shared services
Application management, notifications, clipboard, screenshots, file associations, network, Bluetooth, audio, power and displays; multi-monitor, scaling/HiDPI, hardware compatibility, accessibility, localization, privacy, secure authorized system operations, settings versioning/migration/backup/recovery, secure updates and clean install/remove.

### Five performance profiles and Auto Mode
Ultra Lite, Efficient, Balanced, Enhanced, Ultimate. Auto Mode considers actual hardware/workload/power/memory pressure. Individual Auto/On/Off overrides take priority over automatic optimization where safe; accessibility, stability and security never sacrificed. Measure RAM, CPU, disk I/O, startup, responsiveness and profile-specific effects.

### Migrating to Linux
Friendly first-run wizard to select Classic or future Modern, learn shortcuts, discover app alternatives and configure preferences without terminal expertise.

## Development phases

1. Shared architecture, test foundation, Linux Mint integration and safely recoverable Classic preview/session.
2. Complete Classic desktop UI, performance engine/Auto Mode, customization, accessibility and system services.
3. Migration guide/wizard, compatibility, packaging and cross-hardware testing.
4. Windows-inspired Modern presentation using same proven core.

Do not implement later phases prematurely.

## Mandatory cycle

**INSPECT → PLAN → CODE → TEST → FIX → REGRESSION → DOCUMENT → CHECKPOINT → COMMIT → PUSH → VERIFY CI/PR → NEXT TASK**

Repeat autonomously, with no unnecessary interruptions.

## Definition of done
Implementation meets acceptance criteria, relevant tests pass, regressions/security/compatibility/performance evaluated, docs/traceability/handoff updated, committed and pushed, remote commit and CI verified, and limitations clearly recorded.

## Final directive

Continue from the existing Canopy GitHub repository and **read AGENTS.md, CODEX_START_HERE.md and all documentation completely before edits**. Preserve prior work and the existing PR stack. Implement and test meaningful Canopy Classic increments while preserving compatibility with future Modern, publish verified progress on feature branches with draft PRs, never merge main without authorization. Continue until genuinely blocked or session ends. Never claim completion or verification without evidence.
