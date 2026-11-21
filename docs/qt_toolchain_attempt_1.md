# Qt toolchain enablement attempt 1

Task: `qt-toolchain-enablement-attempt-1`
Branch: `feat/canopy-supervisor-qt-toolchain-enablement-attempt-1`
Source SHA: `4f77407e9d71f62356ca108d42f8b3cbc596c108`
Status: **BLOCKED** — no buildable Qt prototype source and no viable Linux build environment. No packages installed.

## Read-only probes

All probes ran read-only. No environment change made.

### 1. Build tool availability

Command:

```
Get-Command cmake,ninja,qmake,g++,cl -ErrorAction SilentlyContinue
```

Output (per-tool re-run for unambiguous evidence):

```
cmake => NOT_FOUND
ninja => NOT_FOUND
qmake => NOT_FOUND
g++ => NOT_FOUND
cl => NOT_FOUND
```

Exit: all tools absent from `PATH`.

### 2. WSL

Command:

```
wsl.exe --list --quiet
```

Output:

```
LINES=0 EXIT=0
```

No distributions registered. `wsl.exe --status` reported:

```
Default Version: 2
WSL1 is not supported with your current machine configuration.
Please enable the "Windows Subsystem for Linux" optional component to use WSL1.
```

Exit: `0`, but zero installed distros — no Linux build environment.

### 3. winget

Command:

```
winget search Qt
```

Exit: `0`. winget is available and returned Qt-related packages, including
`TheQtCompanyLtd.QtCreator` (21.0.0-rc1), `Qt.QtDesigner` (5.11.1),
`miurahr.aqtinstall` (3.3.0), and several `InstallBuilder for Qt` editions.
These are IDE/installer/auxiliary packages, not a coherent compiler + Qt SDK
toolchain for the Linux Mint target this project builds for.

## Qt prototype source inspection

Buildable-source search (CMakeLists.txt, \*.pro, \*.pri, \*.qml, \*.qrc, \*.ui,
\*.cpp, \*.hpp, \*.cc, \*.cxx, \*.h), excluding `.git`:

```
COUNT=1
examples/shell-pack-starter/ui/Main.qml
```

Findings:

- The only Qt source is `examples/shell-pack-starter/ui/Main.qml`, a placeholder
  `Item` with `implicitWidth: 1280`, `implicitHeight: 720` and no functionality.
  Its own comment says: "Developer template ONLY — not a live Canopy shell or
  plugin." `docs/SHELL_PACK_ARCHITECTURE.md:134` states a validated starter
  pack "does not make it installable."
- No `CMakeLists.txt`, no `.pro`/`.pri`, no C++ source, no build system of any
  kind exists. There is nothing to compile.
- `tools/mint_classic_qt_smoke.py` and `tests/test_mint_classic_qt_smoke.py` are
  Python test harnesses that consume an already-compiled Qt binary; they build
  nothing.
- `docs/SHELL_PACK_ARCHITECTURE.md:135` notes Classic is a standalone Qt demo
  that "has not been migrated" to the host API.

## Decision

No packages were installed. The install condition was not met:

- **No buildable Qt prototype source is present.** A single non-installable QML
  placeholder is not a build target; no build system exists.
- **No safe installer path to the intended target.** The host is Windows with
  no WSL distro, while the project's Qt evidence workflow requires a real Linux
  Mint guest. winget's Qt packages do not produce that target and installing a
  large SDK with no source to build would be an unjustified environment change.

Per task rules, BLOCKED is reported with exact probe output above.

## Verification

Command:

```
python -m unittest tests.test_mint_classic_qt_smoke -v
```

Output excerpt:

```
Ran 30 tests in 0.005s
OK (skipped=30)
TEST_EXIT=0
```

All 30 tests skipped on Windows (`POSIX executable-bit and shell-script
semantics are unavailable on Windows`). Per `AGENTS.md`, all-skipped is not
green: result recorded as NOT RUN for meaningful validation. Python 3.12.10.
No build was attempted and no screenshot was produced; none is claimed.

## Files changed

- `docs/qt_toolchain_attempt_1.md` (this document) — only in-repo change.

No artwork, dock, wallpaper, Qt GUI file, CI workflow, or protected path was
touched. No commit, push, PR, merge, or branch change made.
