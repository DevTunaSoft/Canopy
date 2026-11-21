# Canopy

**The Familiar Feel. The Freedom of Linux.**

Canopy is a planned lightweight Linux desktop shell with a macOS-inspired Classic experience and a future Windows-inspired Modern experience. Project specification and engineering foundation will be proposed through a draft pull request.

Status: planning; no working desktop shell yet.

## Long-term goal: LacOS

After Canopy is validated, the project aims to enable a separate **LacOS** Linux Mint-based distribution: a more refined, resource-efficient and functional Linux experience for people migrating from macOS **and** Windows. Canopy Classic and the future Canopy Modern will share one efficient core, with **user-controlled switching at any time** as a goal—not a one-time installer choice. Live in-session switching with open apps preserved is a target subject to engineering validation; full third-party desktop environment changes may require logout/login. **No LacOS distribution or completed live switcher exists yet.** See [LacOS vision](docs/LACOS_VISION.md) and [roadmap](docs/ROADMAP.md).

## Add more desktop experiences in the future

Canopy Classic and Modern are the **first two**, not a limit. Our goal is a
shared, efficient host supporting many future **Shell Packs**—new Linux
desktop interfaces that can be selected or switched without reinstalling
Linux, and without running multiple desktop service stacks. This makes it
possible for contributors to create welcoming designs for different users.

The [Shell Pack architecture](docs/SHELL_PACK_ARCHITECTURE.md), offline
manifest checker and [developer starter](examples/shell-pack-starter/README.md)
are **design/building-block work only**. No live shell-pack loader, trusted
community installer, in-session switcher or LacOS distribution exists yet.
The standalone Classic Qt prototype is not migrated to the plugin API.

Local metadata check (no execution):

```sh
python3 tools/check_shell_pack.py examples/shell-pack-starter
python3 -m unittest tests.test_shell_pack -v
```
