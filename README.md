# Canopy

**The Familiar Feel. The Freedom of Linux.**

Canopy is an early-stage Linux desktop shell project. Its first experience, **Classic**, aims to make moving from macOS to Linux comfortable through a familiar but original, polished interface. A future **Modern** Windows-inspired experience will share Canopy's underlying services rather than duplicate core functionality.

**Product goal:** Deliver exceptional commercial-grade visual quality **and** low CPU, RAM and GPU usage. Neither visual polish nor performance is optional.

> **Project status:** Planning and browser-based visual prototype. No working Canopy Linux desktop shell, distributable installer, or validated performance results yet. The browser prototype is a design reference, **not** a Linux desktop screenshot.

## Guidance for AI coding agents and contributors

**Read [AGENTS.md](AGENTS.md) in full before changing this project.** This is the authoritative, tool-independent set of engineering instructions. Apply it alongside existing user requirements and project documentation; do not replace or weaken standards.

| Document | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | **Single source of truth:** clean and modular code, low resource use, premium visuals, accessibility, security, testing, regression checks, and GitHub workflow |
| [Design System](docs/DESIGN_SYSTEM.md) | Visual vocabulary, layouts, spacing, icons, color, motion and interaction standards |
| [Visual Quality Gate](docs/VISUAL_QUALITY_GATE.md) | Mandatory visual/accessibility/performance review checklist for user-facing changes |
| [Architecture](docs/ARCHITECTURE.md) | Shared Classic/Modern design, proposed Linux integrations, implementation stages |
| [Performance](docs/PERFORMANCE.md) | Proposed resource budgets, real-hardware test matrix and proof requirements |
| [CLAUDE.md](CLAUDE.md) | Claude Code entry point; references the shared rules |
| [Copilot instructions](.github/copilot-instructions.md) | GitHub Copilot entry point; references the shared rules |

**Expected workflow for any AI assistant:** inspect current code/docs before editing; avoid duplicating functionality or instructions; work in focused branches; implement and test changes; review visual and resource impacts; troubleshoot failures at their root cause; record evidence and limitations; commit changes to the development branch and propose reviewed PRs. Merge only after required checks really pass. Do not invent runtime test results or claim a prototype is a finished desktop.

Agents that do not automatically load these files must be told explicitly to read `AGENTS.md` and the linked documents before working. Guidance files alone do not guarantee compliance; review and checks remain necessary.

## Design prototype

See [Classic browser design reference](prototype/classic/index.html). It is a visual exploration with limited demonstration interactions, **not** a replacement desktop environment or Linux shell.

## Immediate milestones

1. Review the design system and prototype against the visual quality gate.
2. Evaluate a sustainable native Linux desktop stack using measured resource and integration evidence.
3. Implement a real Classic session and capture authentic Linux screenshots.
4. Verify accessibility, performance and stability on lower-end hardware.
5. Package a reproducible installer only after the runtime desktop is validated.

Canopy uses original branding and art; it is not affiliated with Apple or Microsoft.
