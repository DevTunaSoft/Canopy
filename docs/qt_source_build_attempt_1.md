# Qt source build attempt 1

**Status: BLOCKED.** No Qt binary was compiled. No compiled binary is
claimed, because no compiler ran and no build log exists.

## Scope and provenance

- Task: `qt-source-build-attempt-1` (attempt real Qt source compilation).
- Branch: `feat/canopy-supervisor-qt-source-build-attempt-1`.
- Commit SHA at check time: `4f77407e9d71f62356ca108d42f8b3cbc596c108`.
- Working tree at check time: clean on the assigned branch.
- Host: Windows (`win32`), PowerShell 5.1. Date: 2026-11-21.
- Authoritative docs read once: `AGENTS.md`, `docs/QUALITY.md`.
- No git commit, push, PR, merge or branch change was made.
- Only workspace file written: this document.

## 1. Prior-campaign toolchain evidence (verified first)

Source: `feat/canopy-supervisor-qt-build-blockers-followup:docs/QT_BUILD_BLOCKERS_FOLLOWUP.md`,
read at a specific ref only (no full history, no PR loading). It records for
this same Windows host:

- `cmake`, `ninja`, `pkg-config`, `qmake`, `xvfb-run` => NOT FOUND.
- `python3` => Microsoft Store execution-alias stub, not a real interpreter.
- `python` => real `Python 3.12.10`.
- `tools/mint_guest_preflight.py --json` => `status: BLOCKED`, nine blockers,
  with `mint_guest_acceptance`, `runtime_functional_test` and
  `visual_acceptance` all `NOT_RUN`.

The toolchain-enablement branch
`feat/canopy-supervisor-qt-toolchain-enablement-attempt-1` contains no
evidence JSON and no document claiming a provisioned Qt toolchain; the only
Qt docs there (`MINT_CLASSIC_QT_SMOKE.md`, `QT_PERFORMANCE_EVIDENCE_GATE.md`)
describe a separately built Qt6 binary from draft PR #100 that is not present
in this worktree and was not fetched. No prior evidence shows a usable Qt
toolchain on this host.

## 2. Fresh toolchain probe

Exact command (PowerShell):

```
$tools = @("qmake","qmake6","cmake","ninja","mingw32-make","nmake","cl","g++","gcc","pkg-config","xvfb-run","python","python3"); foreach ($t in $tools) { $c = Get-Command $t -ErrorAction SilentlyContinue; if ($c) { "{0} => {1}" -f $t, $c.Source } else { "{0} => NOT FOUND" -f $t } }
```

Output (complete):

```
qmake => NOT FOUND
qmake6 => NOT FOUND
cmake => NOT FOUND
ninja => NOT FOUND
mingw32-make => NOT FOUND
nmake => NOT FOUND
cl => NOT FOUND
g++ => NOT FOUND
gcc => NOT FOUND
pkg-config => NOT FOUND
xvfb-run => NOT FOUND
python => C:\Users\X1\AppData\Local\Programs\Python\Python312\python.exe
python3 => C:\Users\X1\AppData\Local\Microsoft\WindowsApps\python3.exe
```

Common install-root existence check:

```
C:\Qt => False
C:\Qt\6.8.0 => False
C:\Program Files\Qt => False
C:\msys64 => False
C:\Program Files\Microsoft Visual Studio => False
C:\Program Files (x86)\Windows Kits => False
C:\Program Files\CMake => False
```

Result: BLOCKED. No Qt build toolchain is present.

## 3. Source inventory via git ls-tree (no full history)

Exact command:

```
git ls-tree -r --name-only origin/feature/classic-qt-prototype
```

Filtered output (Qt/C++ build-relevant paths):

```
prototype/classic/CMakeLists.txt
prototype/classic/DockTile.qml
prototype/classic/Main.qml
prototype/classic/Theme.qml
prototype/classic/main.cpp
tools/measure_qt.py
tools/qt_smoke.py
```

`prototype/classic/CMakeLists.txt` (from the ref) is a real Qt6 target:
`cmake_minimum_required(VERSION 3.21)`, `find_package(Qt6 6.4 REQUIRED
COMPONENTS Quick QuickControls2)`, `qt_add_executable(canopy-classic-spike
main.cpp)` and `qt_add_qml_module(...)`. `main.cpp` includes `QGuiApplication`
and `QQmlApplicationEngine`. Result: buildable Qt sources DO exist on the
feature-ref; PASS for source availability.

## 4. Configure attempt into a temp directory

Sources were extracted from the ref (read-only) into a temp directory so a
real configure could be attempted:

```
git archive --format=zip --output=<temp>\proto.zip origin/feature/classic-qt-prototype prototype/classic
Expand-Archive -LiteralPath <temp>\proto.zip -DestinationPath <temp>\src -Force
```

Extracted files: `CMakeLists.txt`, `DockTile.qml`, `main.cpp`, `Main.qml`,
`README.md`, `Theme.qml`.

Configure attempt, exact command:

```
cmd /c "cmake -S <temp>\src\prototype\classic -B <temp>\build"
```

Output (complete):

```
'cmake' is not recognized as an internal or external command,
operable program or batch file.
```

Exit code: `1`.

A direct PowerShell `cmake -S ... -B ...` attempt produced the same blocker:

```
& : The term 'cmake' is not recognized as the name of a cmdlet, function,
script file, or operable program.
... FullyQualifiedErrorId : CommandNotFoundException
```

Current preflight (real `python`, not the `python3` Store stub):

```
python tools/mint_guest_preflight.py --json
```

Output excerpt (schema 1):

```json
{
  "blockers": [
    "required build/smoke tool not found: cmake",
    "required build/smoke tool not found: pkg-config",
    "required build/smoke tool not found: ninja",
    "required build/smoke tool not found: xvfb-run",
    "Qt6Core pkg-config metadata not available"
  ],
  "commands_present": {
    "cmake": false, "ninja": false, "pkg-config": false, "xvfb-run": false
  },
  "mint_guest_acceptance": "NOT_RUN",
  "probe_only": true,
  "runtime_functional_test": "NOT_RUN",
  "status": "BLOCKED",
  "visual_acceptance": "NOT_RUN"
}
```

## 5. Result and limits

| Check | Result |
| --- | --- |
| Prior-campaign toolchain evidence reviewed | PASS (toolchain absent) |
| Qt sources located via `git ls-tree` on feature ref | PASS |
| Sources materialized in temp directory | PASS |
| Toolchain probe (qmake/cmake/ninja/pkg-config/compilers) | BLOCKED |
| Configure into temp build dir | BLOCKED (exit 1, cmake not found) |
| Compile / link | NOT RUN |
| Compiled binary produced, hashed or measured | NO |
| Build log of a successful compile | NONE EXISTS |
| Mint guest / Qt GUI / screenshots | NOT RUN |
| Code unit tests for changed files | NOT RUN (doc-only change) |

No binary can be claimed: the only logs here are blocker logs, not build
logs. Nothing was committed, pushed or merged.

## 6. Next step

Provision a real Qt6 (6.4+) toolchain with CMake 3.21+, a C++17 compiler and
Qt Quick / QuickControls2 on a disposable Linux host, then configure and
build `prototype/classic` into a temp dir. Record the exact commands, full
compiler output, exit code, binary path and SHA-256 before any build claim.
