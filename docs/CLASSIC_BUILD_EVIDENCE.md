# Classic reproducible build evidence — 2026-11-25

Workstream 5 (build/release engineering). Priority 0 directive: one reproducible
integrated Classic build. This document records the exact executed run; it is
not a claim of visual approval, Mint acceptance, installer readiness or a
`main` merge. All build output is scratch-only under
`C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy-classic-release/`.

## Source pin

| Field | Exact value |
|---|---|
| Source commit (HEAD) | `b31c995a650202b66c08064a7cc3b7b4f0609d2d` |
| Source tree SHA | `e399189824e6c6da7e3dd6f42d2c59ee9004bca7` |
| Integration ref observed locally | `pr-278-ws1`, `integration/canopy-classic-20261123` |
| Worktree | `C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy-ws5` (isolated, branch `build/classic-reproducible-evidence-20261125`) |
| Tracked/staged source changes during build | none (`git diff --quiet` and `git diff --cached --quiet` both 0) |
| Build target | `prototype/classic/CMakeLists.txt` → `canopy-classic-spike.exe` (Release) |

The shared checkout at `C:/Users/X1/Projects/Canopy` was deliberately not
rebuilt: it is at a different tip and contains other agents' work.

## Toolchain (exact `pacman`/version output)

| Tool | Version / path |
|---|---|
| CMake | `cmake version 4.5.1` (`C:/msys64/ucrt64/bin/cmake.exe`) |
| Ninja | `1.13.2` |
| Qt | `6.12.0` |
| Qt install prefix | `C:/msys64/ucrt64` |
| Qt install QML | `C:/msys64/ucrt64/share/qt6/qml` |
| Compiler | `g++.exe (Rev7, Built by MSYS2 project) 16.2.0` |
| MSYS runtime | `msys2-runtime 3.6.10-5` |
| Environment | `MSYSTEM=UCRT64`, `SOURCE_DATE_EPOCH=0`, `TZ=UTC`, `LANG=C`, `QT_QPA_PLATFORM=offscreen`, `QT_QUICK_BACKEND=software`, `QT_QUICK_CONTROLS_STYLE=Basic`, `QT_FORCE_STDERR_LOGGING=1`, `LIBGL_ALWAYS_SOFTWARE=1` |

`QT_FORCE_STDERR_LOGGING=1` is required: without it this Windows GUI-subsystem
binary emits no observable self-test lines on this host.

## Single entry point and exact commands

```sh
python tools/build/classic_release_build.py \
  --source C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy-ws5 \
  --out C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy-classic-release
```

Executed sequence (recorded verbatim in the evidence bundle's `commands.txt`):

```sh
cmake -S <source>/prototype/classic -B <out>/build -G Ninja -DCMAKE_BUILD_TYPE=Release -Wno-author
# normalize generated qmldir mtimes to SOURCE_DATE_EPOCH=0 before rcc
cmake --build <out>/build --parallel 2
# (repeat configure + mtime normalization + build from an empty build dir)
<binary> --self-test-system-apps-capability
<binary> --enable-system-apps --self-test-system-apps
<binary> --approved-art-dir <art> --self-test-approved --self-test-size 1920x1080 --self-test-screenshot <shot-1920x1080>
<binary> --approved-art-dir <art> --self-test-approved --self-test-size 1200x750 --self-test-screenshot <shot-1200x750>
<binary> --approved-art-dir <art> --self-test-approved --self-test-size 760x500 --self-test-screenshot <shot-760x500>
python tools/qa/classic_build_gate.py verify --evidence <out>/evidence --source-sha b31c995a650202b66c08064a7cc3b7b4f0609d2d
```

The script performs two full clean builds (build directory deleted between
passes), copies the second binary into the bundle, captures all self-test
stdout/stderr, writes `evidence.json` + `toolchain.txt` + `commands.txt`, then
runs the gate. It never edits source, never fetches, never merges.

### Why mtime normalization is part of the build

Qt's `rcc` embeds each resource file's modification time. CMake regenerates
`Canopy/Classic/qmldir` at configure time, so two otherwise identical clean
builds produced different binaries until that generated file was pinned with
`os.utime(path, (0, 0))` after configure. With the pin, two full clean builds
produced the same binary bytes. This is recorded in
`reproducibility.mtime_normalization` and in `commands.txt`.

## Binary and reproducibility

| Field | Exact value |
|---|---|
| Binary | `binary/canopy-classic-spike.exe` |
| SHA-256 | `4def58335e50fdade18dd46457f1b1b5c5514b05195ad8d7dbc90efed8d683d8` |
| Size | `2,060,642` bytes |
| Clean build 1 SHA-256 | `4def58335e50fdade18dd46457f1b1b5c5514b05195ad8d7dbc90efed8d683d8` |
| Clean build 2 SHA-256 | `4def58335e50fdade18dd46457f1b1b5c5514b05195ad8d7dbc90efed8d683d8` |
| Byte-identical rebuild | yes (two fully clean passes) |

A build without `SOURCE_DATE_EPOCH=0` or without the `qmldir` mtime pin is NOT
byte-reproducible on this host; those runs were rejected during development.

## Self-test output (excerpt from captured logs)

```
CANOPY_GIO_DISABLED
SYSTEM_APP_LAUNCH_TEST_PASS: unknown or dangerous actions refused, no application executed
CANOPY_APPROVED_ART_VERIFIED: eight exact PNG icons and legacy blue wave
CANOPY_ROUNDED_DOCK_VERIFIED: eight original icons, padded, alpha-clipped
SELF_TEST_PASS: all eight exact approved dock PNGs loaded
SELF_TEST_PASS: dock icons horizontally/vertically centred count 8 with equal 54px art slots and 7px minimum dock insets
SELF_TEST_PASS: desktop chrome geometry QSize(1920, 1080)
SELF_TEST_PASS: nonuniform window screenshot captured QSize(1920, 1080) sampled colors 91
```

The 1200×750 and 760×500 logs carry the same approved-art, centring and
geometry markers with `sampled colors 92` and `71` respectively. All five
self-test invocations returned rc=0; no `SELF_TEST_FAIL` line was emitted.

## Three screenshot resolutions

| Resolution | Bundle path | SHA-256 (this run) | Self-test log |
|---|---|---|---|
| 1920×1080 | `screenshots/classic-1920x1080.png` | `a072fb3b2bff9e2428ae1c0d3a40b5a57077dc81e769752fda3ae00003647f55` | `selftest-1920x1080.log` |
| 1200×750 | `screenshots/classic-1200x750.png` | `f9532ba1d42a71301a332712d90d13a2cddbbf70c8cfc5891cc1a77841e9e7fe` | `selftest-1200x750.log` |
| 760×500 | `screenshots/classic-760x500.png` | `aca3c113c06620d4069f074073d198a41f199bc120b218df2858cba1c4ef8852` | `selftest-760x500.log` |

The binary itself verifies each PNG is non-uniform and has exact dimensions;
the independent gate re-parses the PNG bytes (bounded 8-bit RGB/RGBA, no
interlace, CRC and scanline filters checked) and requires at least eight
sampled colors. Gate observed 43/44/34 sampled colors in the bundle.

## Artifact manifest (SHA-256, recomputed by the gate)

```
binary/canopy-classic-spike.exe  4def58335e50fdade18dd46457f1b1b5c5514b05195ad8d7dbc90efed8d683d8
commands.txt                     bf7ddd1e09cbf4bedfd74ab1dfcf249f9f1fc55af69284aa2532671b814ca1ae
evidence.json                    8b173b6fa683ff4078027e03e9009d1eb4af5bd60526c6b59fbe5c83471c3cc8
screenshots/classic-1200x750.png f9532ba1d42a71301a332712d90d13a2cddbbf70c8cfc5891cc1a77841e9e7fe
screenshots/classic-1920x1080.png a072fb3b2bff9e2428ae1c0d3a40b5a57077dc81e769752fda3ae00003647f55
screenshots/classic-760x500.png  aca3c113c06620d4069f074073d198a41f199bc120b218df2858cba1c4ef8852
selftest-1200x750.log            c61212948b6e29bdf49ca4244a65cbd76dc48cb3aeb3ebe5442dfb0c678e1941
selftest-1920x1080.log           0b7e902b7295ca0b558fda0088cf95c99ef32bbd122908f584c02973af3524c0
selftest-760x500.log             a268a9fc9cc16ec73bb5bfedb5dc717f7cabc49e6850ee6309a824ed25fd9409
selftest-capability.log          d8de1aaa33c305514ad2ba23b43c9bac26648bd165151bc9e6609aadca556359
selftest-optin-refusal.log       6cd81acb22f654bec1d2f0a78254784b84b62d6d886928937ed55f8f0926e6ff
toolchain.txt                    371095a76d5e25a877b7d797939e22ed213939671458d5c574b4f797bf779587
```

## Gate result

```
CHECK SCHEMA PASS schema_version=1
CHECK SOURCE_SHA PASS pinned=b31c995a650202b66c08064a7cc3b7b4f0609d2d actual=b31c995a650202b66c08064a7cc3b7b4f0609d2d
CHECK TOOLCHAIN PASS required fields recorded in toolchain.txt
CHECK COMMANDS PASS cmake/ninja/self-test commands recorded
CHECK REPRO_HASHES PASS build_hashes=2 binary_sha256=4def58335e50
CHECK MANIFEST_KEYS PASS expected=12 actual=12
CHECK BINARY PASS sha256=4def58335e50
CHECK FILE_HASHES PASS recomputed 12 manifest entries
CHECK SCREENSHOTS PASS 1920x1080 colors=43; 1200x750 colors=44; 760x500 colors=34
CHECK SELFTEST_LOGS PASS selftest-1920x1080.log:ok; selftest-1200x750.log:ok; selftest-760x500.log:ok
CHECK CAPABILITY_LOG PASS UCRT64 build reports no gio-unix-2.0 launcher
CHECK OPTIN_LOG PASS arbitrary launch refused without opt-in
SUMMARY checks=12 pass=12 fail=0
VERDICT PASS
```

Regression suite:

```
python -m unittest tools.build.tests.test_classic_build_gate -v
Ran 15 tests ... OK
```

It includes the gate's own 11-case RED/GREEN mutation control
(`python tools/qa/classic_build_gate.py selftest`), pinning exact FIRST codes:
`SOURCE_SHA`, `TOOLCHAIN`, `REPRO_HASHES`, `BINARY`, `MANIFEST_KEYS`,
`FILE_HASHES`, `SELFTEST_LOGS`, `SCREENSHOTS` (twice) and `CAPABILITY_LOG`.

## Known limitations and failure modes

- Windows UCRT64 has no `gio-unix-2.0`; the binary reports
  `CANOPY_GIO_DISABLED` and native app launching compiles as an opt-in
  disabled fallback. The Linux GIO fixture tests in `.github/workflows/classic-qt.yml`
  are NOT run by this entry point.
- `offscreen` + software Quick backend is a render harness, not a Mint/X11
  session, compositor, installer or real desktop integration test.
- Screenshots contain a live clock. Their per-run SHA-256 values are recorded
  and verified against this bundle's manifest, but are deliberately not pinned
  across runs; the gate pins dimensions, structure, visible variation and
  self-test markers instead.
- Visual approval remains exclusively owner/ChatGPT-owned. These captures are
  build-evidence artifacts only, not approved visual sign-off.
- Five-minute idle CPU/PSS, installer behaviour and Mint acceptance are
  separate gates and were not run here.
- Removing `SOURCE_DATE_EPOCH=0` or skipping the `qmldir` mtime pin makes the
  binary byte-unstable; the gate fails with `REPRO_HASHES` when the two clean
  build hashes disagree.
- Omitting `QT_FORCE_STDERR_LOGGING=1` yields empty logs and a red
  `SELFTEST_LOGS`/`CAPABILITY_LOG` gate on this GUI-subsystem binary.
- A source HEAD other than the pinned tip fails before any build is attempted.

## Scope ownership

New files only: `tools/build/classic_release_build.py`,
`tools/build/tests/test_classic_build_gate.py`,
`tools/build/.gitattributes`, `tools/qa/classic_build_gate.py`,
`docs/CLASSIC_BUILD_EVIDENCE.md`. Scratch build outputs stay outside the
worktree. No PR #279, PR #567/#564 integration, GUI artwork path, Mint session
work or dossier file was touched. No merge to `main`.
