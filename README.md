# Canopy

**The Familiar Feel. The Freedom of Linux.**

Canopy is a lightweight Linux desktop shell engineering candidate with a
macOS-inspired Classic experience and a future Windows-inspired Modern
experience. Shared-core, Qt prototype and nonvisual module work exists;
this is **not** a production release.

Status: extensive nonvisual modules are integrated and tested on the
integration branch, and a compilable Classic Qt prototype exists in the draft
stack (see #151). No release candidate has passed owner visual acceptance and
Linux Mint guest acceptance; see release blocker #132. Modern is planned.

## Resource targets and evidence labels (read before citing a number)

- **Targets, not verified results:** under 100 MiB incremental idle PSS for
  Canopy Classic where technically achievable, under 0.1% average idle CPU of
  one core, and low GPU/compositor cost and wakeups. Measure shell-owned
  consumption on a real desktop before claiming attainment; no target may be
  reported as a measured result.
- **SYNTHETIC**: the Windows 11 `offscreen` Qt host samples in
  [the ce408f4 runtime evidence](docs/perf-windows-runtime-evidence-ce408f4.md)
  (working set, CPU activity proxy, startup timings). They are not Mint, not
  real-desktop and not release evidence.
- **CI-SCOPED**: Ubuntu Actions/Xvfb captures compiled by
  [the Classic Qt workflow](.github/workflows/classic-qt.yml). A green run is
  source/Ubuntu-runtime evidence only; it is not visual or Mint acceptance.
- **NOT_RUN**: real five-minute shell-owned PSS on a real desktop, GPU/compositor
  cost, true scheduler wakeups, screen-reader behavior and automatic CI-on-guest
  acceptance. No proxy, static gate or host-orchestrated report may be relabeled
  as one of these.
- **R066 is BLOCKED** until those real measurements exist; release readiness
  stays false. See [the Mint evidence gate](docs/MINT_ACCEPTANCE_REPORT_GATE.md).
  These labels are editing/evidence rules, not a weakening of any acceptance
  gate.

## Continuous engineering contract

Hermes leads up to **15 concurrent engineering subagents plus Hermes as lead
orchestrator (16 total)**, each in an isolated worktree with explicit file ownership. The
2026-11-26 master autonomous engineering directive supersedes only earlier workforce ceilings,
including the 10-agent ceiling in the external directive cited in
[workforce policy](docs/AGENTS_WORKFORCE.md); all other requirements and acceptance gates there remain in force. This is an
authorized ceiling, not a quota, and supersedes the earlier 12/10/9/7/4-agent configurations. Routine independently
verified engineering follows DEVELOP → TEST → INDEPENDENT REVIEW → READY →
INTEGRATE → VERIFY on `integration/canopy-classic-20261123`. Draft PRs are
temporary; post-merge regression runs **after** a merge, never as a
pre-merge gate. The approved Classic visual identity is frozen; bounded GUI
refinement may proceed without waiting on acceptance, but final visual
acceptance and any merge to `main` are owner-gated. Named holds on #279, #151
and #278 are preserved. See [workforce policy](docs/AGENTS_WORKFORCE.md),
[AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md) and
[quality gates](docs/QUALITY.md).

## LacOS and expandable Canopy Shell Packs — future goals

Canopy Classic is our first macOS-familiar experience; Canopy Modern will be
a Windows-familiar option. The design must support **additional Shell Packs**
without rebuilding the operating system, duplicating the compositor or
starting separate desktop background-service stacks.

The long-term [LacOS vision](docs/LACOS_VISION.md) is a separately validated
Linux Mint-based distribution, **not an available OS release**. See the
[versioned Shell Pack architecture](docs/SHELL_PACK_ARCHITECTURE.md) and
[developer starter](examples/shell-pack-starter/README.md).

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
It is **not yet proven on a real Mint guest**. Its local synthetic test
harness is not a substitute for in-guest functional acceptance.
