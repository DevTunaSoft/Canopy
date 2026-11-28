# Classic reproducible build evidence — current integration tip 9cf39eb

Workstream 5 (build/release engineering). This document records the exact
executed run at the live integration tip `9cf39ebeaf0bc5f6a25279ec81d12b29cdeda3c2`.
It is **not** a claim of visual approval, Mint acceptance, installer readiness
or a `main` merge. All build output is scratch-only under
`private-evidence/scratch/canopy-classic-release-9cf39eb`.

## Source pin: explicit, caller-supplied, never inferred

The obsolete `SOURCE_SHA = b31c995...` constant was removed from
`tools/build/classic_release_build.py` and `EXPECTED_SOURCE_SHA` was removed
from `tools/qa/classic_build_gate.py`. No 40-hex repository SHA is hardcoded in
either file. The pin is now an explicit argument to both programs:

| Field | Exact value |
|---|---|
| Source commit (HEAD) | `9cf39ebeaf0bc5f6a25279ec81d12b29cdeda3c2` |
| Source tree SHA | `83c7df9557c59b9acdb9ef0f9e69c15ff536a0b1` |
| Integration ref observed locally | `integration/canopy-classic-20261123` (remote tip `9cf39eb`) |
| Build source worktree | `private-evidence/scratch/canopy-pin-base-9cf39eb` (detached at `9cf39eb`, clean) |
| Changed tooling worktree | `private-evidence/scratch/canopy-pin-fix-9cf39eb` (branch `fix/classic-build-source-pin-9cf39eb`) |
| Tracked/staged source changes during build | none (`git diff --quiet` and `git diff --cached --quiet` both 0) |
| Build target | `prototype/classic/CMakeLists.txt` → `canopy-classic-spike.exe` (Release) |

Fail-closed behaviour proved on this bundle:

```
python tools/qa/classic_build_gate.py verify --evidence <out>/evidence --source-sha b31c995a650202b66c08064a7cc3b7b4f0609d2d
CHECK SOURCE_SHA FAIL pinned=b31c995a650202b66c08064a7cc3b7b4f0609d2d actual=9cf39ebeaf0bc5f6a25279ec81d12b29cdeda3c2
SUMMARY checks=12 pass=11 fail=1
FIRST SOURCE_SHA
VERDICT FAIL   (exit 1)
```

The build entry point rejects a HEAD that differs from `--source-sha` before
configuring anything, rejects a malformed/non-40-hex pin, and re-checks HEAD
plus the tracked tree after both builds. The verify CLI makes `--source-sha`
required and normalizes only strict 40-character hex; no pin is taken from the
bundle being verified. A stale or absent pin can therefore never pass silently.

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
  --source private-evidence/scratch/canopy-pin-base-9cf39eb \
  --source-sha 9cf39ebeaf0bc5f6a25279ec81d12b29cdeda3c2 \
  --out private-evidence/scratch/canopy-classic-release-9cf39eb
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
python tools/qa/classic_build_gate.py verify --evidence <out>/evidence --source-sha 9cf39ebeaf0bc5f6a25279ec81d12b29cdeda3c2
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
| SHA-256 | `458291aa2f08c6ea0729e5183e3f8d763cabb2c591f0a56192fa13756521b0c6` |
| Size | `2,119,663` bytes |
| Clean build 1 SHA-256 | `458291aa2f08c6ea0729e5183e3f8d763cabb2c591f0a56192fa13756521b0c6` |
| Clean build 2 SHA-256 | `458291aa2f08c6ea0729e5183e3f8d763cabb2c591f0a56192fa13756521b0c6` |
| Byte-identical rebuild | yes (two fully clean passes, ~221 s and ~190 s compile) |

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

| Resolution | Bundle path | SHA-256 (this run) | Gate-sampled colors |
|---|---|---|---|
| 1920×1080 | `screenshots/classic-1920x1080.png` | `0a08c38b73029327492f943e65ee4cd5284a13ade6435f15ecda14e54a496b11` | 43 |
| 1200×750 | `screenshots/classic-1200x750.png` | `48526f486e03a9f1a304e33e6afe281a4259b34da7cc5132eeca678742a6db91` | 44 |
| 760×500 | `screenshots/classic-760x500.png` | `68465e0e157e96f529d3408ea9f0558a4527dc102565e26c34f97790cb139ce0` | 34 |

Each PNG has its own `selftest-<size>.log`. The binary verifies non-uniformity
and exact dimensions; the independent gate re-parses the PNG bytes (bounded
8-bit RGB/RGBA, no interlace, CRC and scanline filters checked) and requires at
least eight sampled colors.

## Artifact manifest (SHA-256, recomputed by the gate)

```
binary/canopy-classic-spike.exe  458291aa2f08c6ea0729e5183e3f8d763cabb2c591f0a56192fa13756521b0c6
commands.txt                     c1410776ffef7b6e6a3969f71002a0887895a810de2d850ffa37f2e0f611dd2f
evidence.json                    503a9642aa89bd82d058a7a058da8df2db2de82c4e7f8749e3a679bfd1c07eaf
screenshots/classic-1200x750.png 48526f486e03a9f1a304e33e6afe281a4259b34da7cc5132eeca678742a6db91
screenshots/classic-1920x1080.png 0a08c38b73029327492f943e65ee4cd5284a13ade6435f15ecda14e54a496b11
screenshots/classic-760x500.png  68465e0e157e96f529d3408ea9f0558a4527dc102565e26c34f97790cb139ce0
selftest-1200x750.log            c61212948b6e29bdf49ca4244a65cbd76dc48cb3aeb3ebe5442dfb0c678e1941
selftest-1920x1080.log           0b7e902b7295ca0b558fda0088cf95c99ef32bbd122908f584c02973af3524c0
selftest-760x500.log             a268a9fc9cc16ec73bb5bfedb5dc717f7cabc49e6850ee6309a824ed25fd9409
selftest-capability.log          d8de1aaa33c305514ad2ba23b43c9bac26648bd165151bc9e6609aadca556359
selftest-optin-refusal.log       6cd81acb22f654bec1d2f0a78254784b84b62d6d886928937ed55f8f0926e6ff
toolchain.txt                    371095a76d5e25a877b7d797939e22ed213939671458d5c574b4f797bf779587
```

## Gate result at the correct pin

```
CHECK SCHEMA PASS schema_version=1
CHECK SOURCE_SHA PASS pinned=9cf39ebeaf0bc5f6a25279ec81d12b29cdeda3c2 actual=9cf39ebeaf0bc5f6a25279ec81d12b29cdeda3c2
CHECK TOOLCHAIN PASS required fields recorded in toolchain.txt
CHECK COMMANDS PASS cmake/ninja/self-test commands recorded
CHECK REPRO_HASHES PASS build_hashes=2 binary_sha256=458291aa2f08
CHECK MANIFEST_KEYS PASS expected=12 actual=12
CHECK BINARY PASS sha256=458291aa2f08
CHECK FILE_HASHES PASS recomputed 12 manifest entries
CHECK SCREENSHOTS PASS 1920x1080 colors=43; 1200x750 colors=44; 760x500 colors=34
CHECK SELFTEST_LOGS PASS selftest-1920x1080.log:ok; selftest-1200x750.log:ok; selftest-760x500.log:ok
CHECK CAPABILITY_LOG PASS UCRT64 build reports no gio-unix-2.0 launcher
CHECK OPTIN_LOG PASS arbitrary launch refused without opt-in
SUMMARY checks=12 pass=12 fail=0
VERDICT PASS
```

Regression suites at this change:

```
python -m unittest tools.build.tests.test_classic_build_gate -v
Ran 21 tests ... OK (skipped=1)

python -m unittest discover -s tests
Ran 3277 tests ... OK (skipped=45)     # base at 9cf39eb: 3256 OK, skipped=44
```

The 21 tests include stale-pin, correct-pin, malformed/absent-pin cases, a
no-hardcoded-SHA source scan, CLI-required-pin and build-script stale-pin
rejection, plus the gate's 13-case RED/GREEN mutation control
(`python tools/qa/classic_build_gate.py selftest`), pinning exact FIRST codes:
`SOURCE_SHA` (twice), `TOOLCHAIN`, `REPRO_HASHES`, `BINARY`, `MANIFEST_KEYS`,
`FILE_HASHES`, `SELFTEST_LOGS`, `SCREENSHOTS` (twice) and `CAPABILITY_LOG`.
`tests/test_classic_build_gate.py` mirrors these cases into Foundation CI's
`unittest discover -s tests`; the +21-test delta is exactly that mirror.

## Resource / evidence note

- Measured on this Windows UCRT64 host: two clean Release builds (binary SHA
  above), five Qt self-test invocations and three offscreen screenshot captures.
  The binary size, per-pass hashes and all log/manifest hashes are on disk in
  the scratch bundle; gate fixture cases are `SYNTHETIC`.
- `NOT_RUN`: five-minute idle CPU/PSS, real desktop/Mint session, installer
  behaviour and screen-reader/announcement behavior. This change touches only
  Python tooling, docs and tests; no UI, QML or announcement code changed, so
  no screen-reader behaviour was measured or altered.
- No stability, security, accessibility or approved-visual tradeoff was made:
  the gate only tightens how the caller declares the source pin.

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
- A source HEAD or caller pin that differs from `--source-sha` fails before any
  build; a verify run with a stale or missing pin fails at `SOURCE_SHA`.

## Scope ownership

Changed only `tools/build/classic_release_build.py`,
`tools/build/tests/test_classic_build_gate.py`,
`tools/qa/classic_build_gate.py`, `tests/test_classic_build_gate.py` and
`docs/CLASSIC_BUILD_EVIDENCE.md`. Scratch build outputs stay outside the
worktree. No source/QML/asset/dossier/AGENTS path, no other agent's path and no
merge to `main` was performed.
