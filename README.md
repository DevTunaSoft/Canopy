# Canopy

**The Familiar Feel. The Freedom of Linux.**

Canopy is a lightweight, premium Linux desktop shell under active development. Its mission is to make the transition to Linux feel natural for people accustomed to macOS or Windows, without sacrificing the freedom, flexibility, security and efficiency of Linux.

Canopy starts on Linux Mint as a separately usable desktop shell. It is not itself a new operating system. Our longer-term ambition is **LacOS**, a distinct Linux Mint-based distribution built around the Canopy experience.

## One foundation. More than one desktop experience.

| Experience | Vision | Development status |
| --- | --- | --- |
| **Canopy Classic** | A macOS-familiar menu bar, dock, launcher and desktop workflow, with original visual design. | Active development; compiled Qt preview and integration work exist. |
| **Canopy Modern** | A Windows-familiar taskbar, application menu, system tray, window workflows and shortcuts. | Planned after Classic. |
| **Canopy Shell Packs** | A framework for additional original desktop presentations, using a shared host rather than separate desktop service stacks. | Metadata validation, local developer tooling and an in-memory lifecycle prototype exist; runtime loading and switching are future work. |
| **LacOS** | A future Linux Mint-derived distribution offering Canopy experiences with integrated installation, updates and recovery. | Long-term vision; no released operating system. |

## What we are building toward

- **Familiar, refined design:** intuitive navigation, coherent original artwork, accessible controls and a polished desktop.
- **Lightweight by design:** event-driven components, lazy initialization, bounded memory and caches, and no unnecessary background services or mandatory visual effects.
- **One shared core:** app launching, window and workspace integration, settings, notifications and session services shared across presentations where technically practical.
- **Choice without duplication:** five planned performance profiles plus Auto Mode and per-feature overrides; a future extensible Shell Pack system for choosing additional desktop experiences.
- **Trust and reliability:** secure defaults, least privilege, reversible installation, reproducible builds, accessibility and measured performance on real Linux hardware.

These are design goals, not claims of completed functionality or measured performance.

## LacOS: the next chapter

LacOS is envisioned as a separate Linux Mint-based distribution that combines familiar desktop experiences with the established Linux package ecosystem, hardware compatibility, security updates and recovery foundations. Its aim is to deliver a leaner, more refined and more adaptable experience, validated against stock Mint on the same hardware and workloads.

The long-term goal is to let users choose Classic, Modern or additional compatible Shell Packs, and switch between them without reinstalling or rebooting when the underlying session supports it. Preserving running applications and user work, recovering safely from failed switches, and unloading inactive presentations are essential design requirements. Where a compositor or session change is required, a clearly explained logout/login transition is the safe fallback.

LacOS distribution development follows successful Canopy shell, session, performance and switching acceptance. Neither LacOS nor seamless live Shell Pack switching is available today.

## Development roadmap

1. Complete and validate Canopy Classic on Linux Mint.
2. Build Canopy Modern using the shared core.
3. Implement and validate secure Shell Pack loading, switching and rollback, including an additional independent presentation.
4. Develop LacOS distribution packaging, installation, upgrades and recovery.
5. Release only after real-world functional, security, accessibility, visual and resource acceptance.

## Current project status

**Active development — pre-alpha.** A compiled Canopy Classic Qt preview and shared-core building blocks exist. Ongoing engineering is integrated on the [development branch](https://github.com/DevTunaSoft/Canopy/tree/integration/canopy-classic-20261123). Real Linux Mint session acceptance, final visual approval, native functionality, release packaging and real-desktop resource benchmarks remain outstanding. There is no production-ready Canopy or LacOS download at this stage.

- [Current development and evidence matrix](https://github.com/DevTunaSoft/Canopy/blob/integration/canopy-classic-20261123/docs/PRODUCT_COMPLETION_MATRIX.md)
- [Architecture](docs/ARCHITECTURE.md)
- [LacOS vision](docs/LACOS_VISION.md)
- [Shell Pack architecture](docs/SHELL_PACK_ARCHITECTURE.md)
- [Quality and performance requirements](docs/QUALITY.md)
- [Classic release integration blocker](https://github.com/DevTunaSoft/Canopy/issues/132)

## Developer resources

The following tools are early engineering building blocks. They do not constitute a released desktop, installer, trusted plugin runtime or completed Linux Mint session.

A safe metadata validator and non-executable starter are present. No Shell
Host runtime loader, community package installer, live-switch implementation
or Linux Mint session acceptance is claimed:

```sh
python3 tools/check_shell_pack.py examples/shell-pack-starter
python3 -m unittest tests.test_shell_pack -v
```

### Try the metadata-only Shell Pack registry

The new `canopy_core` discovery API and CLI find and validate up to 64
local Shell Pack directories without loading or executing their QML code:

```sh
python3 -m canopy_core examples --json
python3 -m unittest tests.test_shell_pack_registry -v
```

**Important:** metadata discovery does not install, approve or launch packs.
The actual Shell Host/runtime, permissions and session switching remain future
engineering milestones.

### Shared presentation lifecycle prototype

`canopy_core.shell_host.ShellHost` also has a tested **in-memory,
host-registered** adapter lifecycle: prepare → deactivate old → activate
new → dispose old, with rollback and visible recovery failures. It is a
non-Qt simulation of the host-side transition logic, not an end-user
shell switcher or permission to run community QML.

```sh
python3 -m unittest tests.test_shell_host -v
```

### Create a new local Shell Pack starter

Developers can now generate a third (or later) original presentation without
touching Canopy's shared-core code or existing Classic artwork:

```sh
mkdir -p /tmp/canopy-packs
python3 -m canopy_core.scaffold /tmp/canopy-packs \
  --id com.example.focus --name "Focus Desktop" \
  --capability app-launcher
python3 -m canopy_core /tmp/canopy-packs --json
python3 -m unittest tests.test_shell_scaffold -v
```

This only creates a locally validated `manifest.json`, QML placeholder and
README. It refuses unsafe or existing directories, invalid IDs and
capabilities, and invalid catalogs. **It does not install or run** a desktop
presentation; runtime loading and same-session switching are still future work.

### Classic dock artwork optical QA

The standalone [icon optical audit](docs/ICON_OPTICAL_REVIEW.md) helps
reviewers quantify why centered image rectangles can still contain
off-center artwork. It reads **externally supplied, SHA-verified** original
PNG masters and generates a non-mutating heuristic report. No source
icons are included, uploaded, transformed or approved by this tool.

### Try Classic without replacing your desktop

A limited, user-level [Classic preview menu registration](docs/CLASSIC_USER_MENU_PREVIEW.md)
lets you add or remove the **compiled Qt preview** as an application inside
your existing Linux desktop. It uses no root access, login manager changes,
compositor changes, network service or background daemon. It verifies
ownership before removing its exact desktop entry; modified user files
are preserved.

The registration script does **not** install a real desktop session, bundle
a Qt binary, or prove Linux Mint GUI acceptance. Run its tests with
python3 -m unittest tests.test_classic_preview_menu -v.

### Real Linux Mint Qt smoke evidence (when guest is available)

After the [read-only Mint preflight](docs/MINT_GUEST_PREFLIGHT.md), the
[guest-only Qt smoke runner](docs/MINT_CLASSIC_QT_SMOKE.md) can execute
the compiled Qt Classic prototype at three sizes and save screenshot
SHA-256 evidence without modifying Cinnamon or installing packages.
The integration branch records scoped Mint/Xvfb smoke evidence, but full native desktop/session acceptance remains unestablished. Synthetic harnesses and scoped smoke tests are not a substitute for end-to-end Mint acceptance.
