# Canopy

**The Familiar Feel. The Freedom of Linux.**

Canopy is a planned lightweight Linux desktop shell for Linux Mint, helping macOS and Windows users transition to Linux through familiar, original desktop experiences.

- **Classic (first):** macOS-inspired top bar, original white Tux menu, dock and launcher.
- **Modern (later):** Windows-inspired taskbar, launcher and workflows.
- **One core:** shared configuration, system integration, performance, accessibility and recovery.
- **Safety:** install alongside Cinnamon, retain fallback, never run shell as root.

**Status:** An experimental Classic GTK preview includes a top bar, dock and searchable application launcher. Linux Mint session and hardware acceptance are pending.

Read [requirements](docs/REQUIREMENTS.md), [architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md), [traceability](docs/TRACEABILITY.md), [handoff](docs/HANDOFF.md), and [engineering rules](AGENTS.md).

## Windows test-lab entry points (experimental)

**Installer launcher:** `Canopy-OneClick.cmd` runs `Canopy-OneClick.ps1`. It attempts to prepare a Linux Mint installer ISO and start the isolated `Canopy-Test-Mint` VirtualBox VM. It is **not yet a verified one-click installation**: an independently authenticated Mint ISO checksum, available VirtualBox, WSL preparation, and actual guest boot acceptance remain gating conditions. The script never claims a successful Mint desktop boot.

**Read-only preflight:** `Canopy-Start.cmd` runs `Canopy-Setup.ps1` without installation flags. It checks the host and reports readiness; it **does not install or launch Canopy**. The filename is retained for compatibility with existing test-lab instructions.

**Advanced/manual path:** `Canopy-Setup.ps1` and `scripts/Start-CanopyTestLab.ps1` provide parameterized VM and Mint setup operations. The `scripts/Install-CanopyMintOS.ps1` unattended VirtualBox path is a separate experimental implementation; do not run both installer methods against the same VM concurrently. Keep both covered by CI until end-to-end evidence supports consolidation.

**Verification:** GitHub Actions checks PowerShell syntax, unit tests, ISO builder behavior, and bounded safety controls. A green workflow does not prove that Windows restart recovery, Linux Mint installation, or the Canopy desktop actually worked on a physical Windows host.

## Codex and engineering takeover

**Start here: [CODEX_START_HERE.md](CODEX_START_HERE.md)** — verified GitHub state, stacked PR ordering, file inventory, precise implementation limits, local/CI tests, risk register and safe next steps.

Additional authoritative files: [master autonomous mandate](docs/MASTER_AUTONOMOUS_PROMPT.md), [feature status](docs/FEATURE_STATUS.md), [engineering decisions](docs/ENGINEERING_DECISIONS.md), [Classic preview instructions](docs/CLASSIC-PREVIEW.md).

**Development branch note:** The Classic GTK preview currently lives on `feat/classic-gtk-preview`, not on `main`. The takeover documentation lives on `docs/codex-takeover-dossier`. No login-capable Canopy session is built yet.
