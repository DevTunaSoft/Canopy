# Canopy

**The Familiar Feel. The Freedom of Linux.**

Canopy is a planned lightweight Linux desktop shell with a macOS-inspired Classic experience and a future Windows-inspired Modern experience. Project specification and engineering foundation will be proposed through a draft pull request.

Status: planning; no working desktop shell yet.

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
