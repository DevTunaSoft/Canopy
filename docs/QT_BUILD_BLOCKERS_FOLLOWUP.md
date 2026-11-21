# Qt and Mint blocker evidence follow-up

**Status:** Host-side, read-only blocker consolidation only.
This document records what was actually checked on this Windows host.
No Qt binary was compiled, no Qt GUI was launched, no Mint guest was booted,
and no screenshot was captured or invented.

## Scope and provenance

- Task: `qt-build-blockers-followup` (consolidate Qt and Mint blocker evidence).
- Branch: `feat/canopy-supervisor-qt-build-blockers-followup`.
- Commit SHA at check time: `6d26dd3a36245fd9f8034459b0843aed416dbe2b`.
- Working tree at check time: clean on the assigned branch.
- Host: Windows (`win32`), PowerShell 5.1 shell.
- Date: 2026-11-21.
- Read this with `docs/QUALITY.md`, `docs/MINT_GUEST_PREFLIGHT.md`,
  `docs/MINT_CLASSIC_QT_SMOKE.md` and `docs/QT_PERFORMANCE_EVIDENCE_GATE.md`.
- Authoritative docs read once: `AGENTS.md`, `docs/QUALITY.md`.

Only read-only commands were used. The sole file written in the workspace is
this document. Evidence JSON was written outside the workspace to the path
assigned by the supervisor. Nothing was committed, pushed or merged.

## Result summary

| Area | Check | Result |
| --- | --- | --- |
| Qt sources | Buildable Qt source/C++ target present in worktree | BLOCKED |
| Qt sources | Source inventory command executed | PASS |
| Build tools | cmake / ninja / pkg-config / qmake present | BLOCKED |
| Build tools | Usable `python` interpreter (`Python 3.12.10`) | PASS |
| Build tools | `python3` usable interpreter | BLOCKED |
| Mint VM | `tools/mint_guest_preflight.py --json` run with real Python | BLOCKED |
| Mint VM | Hypervisor tooling / Mint guest on host | BLOCKED |
| Mint VM | Qt compile + GUI smoke + screenshots | NOT RUN |
| Tests | `tests.test_mint_guest_preflight` | PASS |
| Tests | `tests.test_mint_classic_qt_smoke` | BLOCKED (all skipped) |

Legend: PASS = command ran and condition met. BLOCKED = command ran but a
required precondition is absent. NOT RUN = deliberately not executed here.

## 1. Qt sources

Exact command:

```
git ls-files "*.cpp" "*.cc" "*.h" "*.hpp" "*.qml" "CMakeLists.txt" "*.pro" "*.ui"
```

Output (complete):

```
examples/shell-pack-starter/ui/Main.qml
```

Cross-check exact command:

```
git ls-files | Select-String -Pattern '\.(cpp|cc|h|hpp|qml|pro|ui)$|CMakeLists\.txt'
```

Output (complete):

```
examples/shell-pack-starter/ui/Main.qml
```

Tracked binary check exact command:

```
git ls-files "*.exe" "*.dll" "*.so" "*.a" "*.obj" "*.o"
```

Output: no paths (empty). Marker line `tracked_binaries_end` was appended by
the shell and is not a tracked file.

The single QML file is `examples/shell-pack-starter/ui/Main.qml`. It is a
developer template, not a buildable shell: its own comments say "Developer
template ONLY — not a live Canopy shell or plugin" and it is a bare `Item`
with no Qt build target. `examples/shell-pack-starter/` contains only
`manifest.json`, `README.md` and `ui/Main.qml`. Per `AGENTS.md`, this Qt
starter is not installable.

Finding: this worktree has no C++ sources, no `CMakeLists.txt` and no compiled
Qt binary. Result BLOCKED for compiling Qt from this checkout on this host.
The separately built prototype referenced in draft PR #100 / #109 is not
present here and was not fetched (rule: no full history / PR loading).

## 2. Build tools

Exact command (PowerShell):

```
$tools = @("cmake","ninja","pkg-config","qmake","qmake6","python3","python","git"); foreach ($t in $tools) { $c = Get-Command $t -ErrorAction SilentlyContinue; if ($c) { "{0} => {1}" -f $t, $c.Source } else { "{0} => NOT FOUND" -f $t } }
```

Output (complete):

```
cmake => NOT FOUND
ninja => NOT FOUND
pkg-config => NOT FOUND
qmake => NOT FOUND
qmake6 => NOT FOUND
python3 => C:\Users\X1\AppData\Local\Microsoft\WindowsApps\python3.exe
python => C:\Users\X1\AppData\Local\Programs\Python\Python312\python.exe
git => C:\Program Files\Git\cmd\git.exe
```

Exact command:

```
python3 --version; python --version; python3 -c "import sys; print(sys.executable)"
```

Output (complete):

```
Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.
Python 3.12.10
Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.
```

`python3` is a non-functional Microsoft Store execution-alias stub; it did
not execute any script. `python` is a real `Python 3.12.10` interpreter.

The four tools required by `tools/mint_guest_preflight.py` (`cmake`,
`pkg-config`, `ninja`, `xvfb-run`) plus qmake are all absent. `xvfb-run` was
not re-probed separately because it is a Linux/Xvfb utility; the preflight
JSON below independently reports it as not present. Result BLOCKED for a Qt
build on this host.

## 3. Mint VM support

Exact command (PowerShell):

```
$vm = @("VBoxManage","qemu-system-x86_64","vagrant","wsl","vmrun","docker"); foreach ($t in $vm) { $c = Get-Command $t -ErrorAction SilentlyContinue; if ($c) { "{0} => {1}" -f $t, $c.Source } else { "{0} => NOT FOUND" -f $t } }; "os-release exists => {0}" -f (Test-Path -LiteralPath "/etc/os-release"); "DISPLAY set => {0}" -f [bool]$env:DISPLAY; "WAYLAND_DISPLAY set => {0}" -f [bool]$env:WAYLAND_DISPLAY
```

Output (complete):

```
VBoxManage => NOT FOUND
qemu-system-x86_64 => NOT FOUND
vagrant => NOT FOUND
wsl => C:\WINDOWS\system32\wsl.exe
vmrun => NOT FOUND
docker => NOT FOUND
os-release exists => False
DISPLAY set => False
WAYLAND_DISPLAY set => False
```

Exact command:

```
wsl.exe --list --quiet 2>&1 | Out-String; "wsl_exit=$LASTEXITCODE"
```

Output (complete):

```
wsl_exit=0
```

`wsl.exe` exists but lists no distributions, and no Mint guest is available.

Exact command (the `python3` attempt is recorded for honesty; it produced the
Store-stub error shown in section 2 and did not run the script):

```
python3 tools/mint_guest_preflight.py --json
```

Then, with the real interpreter:

```
python tools/mint_guest_preflight.py --json
```

Output (complete, schema 1):

```json
{
  "blockers": [
    "guest is not verified as Linux Mint",
    "no graphical display for declared session",
    "desktop session identity not provided",
    "session type not provided",
    "required build/smoke tool not found: cmake",
    "required build/smoke tool not found: pkg-config",
    "required build/smoke tool not found: ninja",
    "required build/smoke tool not found: xvfb-run",
    "Qt6Core pkg-config metadata not available"
  ],
  "cinnamon_identified": false,
  "commands_present": {
    "cmake": false,
    "ninja": false,
    "pkg-config": false,
    "xvfb-run": false
  },
  "desktop_session_present": false,
  "graphical_display_present": false,
  "mint_guest_acceptance": "NOT_RUN",
  "mint_identified": false,
  "probe_only": true,
  "qt6_core_version": null,
  "runtime_functional_test": "NOT_RUN",
  "schema_version": 1,
  "session_type": "other-or-unknown",
  "status": "BLOCKED",
  "version_id": "unknown",
  "visual_acceptance": "NOT_RUN"
}
```

This probe is `probe_only: true`. It explicitly sets
`mint_guest_acceptance`, `runtime_functional_test` and `visual_acceptance` to
`NOT_RUN`. Result BLOCKED for Mint VM acceptance on this host.

## 4. Relevant tests actually run

Exact command:

```
python -m unittest tests.test_mint_guest_preflight -v
```

Output excerpt (last lines):

```
test_supported_cinnamon_session_variants ... ok
test_ubuntu_is_not_passed_as_mint ... ok
test_wayland_guest_can_be_ready ... ok
----------------------------------------------------------------------
Ran 16 tests in 0.245s
OK
```

Result PASS: 16 pure/unit tests passed. These use synthetic environment data
and are NOT Mint guest acceptance.

Exact command:

```
python -m unittest tests.test_mint_classic_qt_smoke -v
```

Output excerpt (last lines):

```
test_truncated_png_does_not_pass ... skipped 'POSIX executable-bit and shell-script semantics are unavailable on Windows'
test_unreasonable_and_noninteger_timeouts_are_rejected ... skipped 'POSIX executable-bit and shell-script semantics are unavailable on Windows'
test_wrong_screenshot_resolution_is_not_a_pass ... skipped 'POSIX executable-bit and shell-script semantics are unavailable on Windows'
----------------------------------------------------------------------
Ran 30 tests in 0.001s
OK (skipped=30)
```

Result BLOCKED: all 30 tests were skipped on Windows; the runner reported
`OK (skipped=30)`. Per `AGENTS.md`, all-skipped is not green. No Qt process
ran and no screenshot was produced by this test run.

## 5. Explicitly NOT RUN

- No compilation of Qt sources (no sources, no toolchain on this host).
- No `canopy-classic-spike` binary built, measured or hashed.
- No `tools/mint_classic_qt_smoke` in-guest run.
- No screenshots at 760x500, 1200x750, 1920x1080 or HiDPI.
- No visual, optical-icon, compositor, focus, accessibility or 5-minute
  resource acceptance.
- No Mint guest boot, snapshot, rollback or display-manager change.
- No git commit, push, PR, merge or branch change.

These remain release blockers documented in
`docs/RELIABILITY_99_GATE_AUDIT.md` and `docs/QUALITY.md`.

## 6. Consolidated blocker list

1. Qt build target absent: no C++/CMake Qt source in this worktree; only a
   non-installable QML template.
2. Toolchain absent: cmake, ninja, pkg-config, qmake and xvfb-run not found;
   `python3` is a Store stub.
3. No Mint guest: host is Windows, no `/etc/os-release`, no Cinnamon/X11/
   Wayland session, no VirtualBox/qemu/Vagrant VM, WSL has no distributions.
4. Preflight result BLOCKED with nine explicit blockers; all acceptance
   fields are `NOT_RUN`.
5. In-guest smoke suite is entirely skipped on Windows (30 skips).

Next step for whoever continues: provision a real, disposable Linux Mint
Cinnamon guest with the build toolchain, obtain the verified Qt build from the
approved source SHA and approved artwork bundle, then run the preflight and
smoke runner exactly as documented in `docs/MINT_GUEST_PREFLIGHT.md` and
`docs/MINT_CLASSIC_QT_SMOKE.md`. Record actual logs, hashes and screenshots;
do not carry any status from this document into a release claim.
