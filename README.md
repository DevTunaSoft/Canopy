# Canopy

**The Familiar Feel. The Freedom of Linux.**

Canopy is a planned lightweight Linux desktop shell for Linux Mint, helping macOS and Windows users transition to Linux through familiar, original desktop experiences.

- **Classic (first):** macOS-inspired top bar, original white Tux menu, dock and launcher.
- **Modern (later):** Windows-inspired taskbar, launcher and workflows.
- **One core:** shared configuration, system integration, performance, accessibility and recovery.
- **Safety:** install alongside Cinnamon, retain fallback, never run shell as root.

**Status:** An experimental Classic GTK preview includes a top bar, dock and searchable application launcher. Linux Mint session and hardware acceptance are pending.

Read [requirements](docs/REQUIREMENTS.md), [architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md), [traceability](docs/TRACEABILITY.md), [handoff](docs/HANDOFF.md), and [engineering rules](AGENTS.md).

## Codex and engineering takeover

**Start here: [CODEX_START_HERE.md](CODEX_START_HERE.md)** — verified GitHub state, stacked PR ordering, file inventory, precise implementation limits, local/CI tests, risk register and safe next steps.

Additional authoritative files: [master autonomous mandate](docs/MASTER_AUTONOMOUS_PROMPT.md), [feature status](docs/FEATURE_STATUS.md), [engineering decisions](docs/ENGINEERING_DECISIONS.md), [Classic preview instructions](docs/CLASSIC-PREVIEW.md).

**Development branch note:** The Classic GTK preview currently lives on `feat/classic-gtk-preview`, not on `main`. The takeover documentation lives on `docs/codex-takeover-dossier`. No login-capable Canopy session is built yet.
