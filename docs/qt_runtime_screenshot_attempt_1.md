# Qt runtime screenshot attempt 1 — evidence

## Result

**NOT RUN.** No genuine compiled Qt binary exists in this environment. No
screenshot was captured, no exit code from a Qt self-test exists, and no PNG
paths or SHA-256 hashes are reported. No synthetic PNG was created or presented
as a real screenshot.

| Field | Value |
| --- | --- |
| task_id | qt-runtime-screenshot-attempt-1 |
| branch | feat/canopy-supervisor-qt-runtime-screenshot-attempt-1 |
| commit_sha (base) | 4f77407e9d71f62356ca108d42f8b3cbc596c108 |
| status | NOT RUN |
| draft | true |

## Why this is NOT RUN

The task permits launching a binary only **if a compiled Qt binary was proven
in the previous campaign**. It was not. Prior supervisor evidence records the
opposite, and this worker's own absence checks confirm no binary is present
now:

- `docs/SUPERVISOR_VERIFICATION.md` wave-1 evidence lists **no compiled Qt
  binary, no Qt toolchain, no Mint VM, no compiled-Qt screenshot, and no owner
  visual signoff**, all marked BLOCKED/NOT RUN.
- The qt-build-blockers follow-up records that **no Qt binary was compiled, no
  Qt GUI launched, no Mint guest booted, and no screenshot captured** on this
  Windows 11 / PowerShell 5.1 host.
- The visual-qa worker found **zero Qt screenshot artifacts**
  (`**/qt-*.png` and `**/*screenshot*.png` returned 0 matches).
- The clean repository binary audit found **no tracked binary artifacts**
  (`*.exe`, `*.dll`, `*.so`, `*.a`, `*.obj`, `*.o`).

A separate concurrent task, `qt-source-build-attempt-1`, has only **staged
source** so far (`CMakeLists.txt`, `main.cpp`, `Main.qml`, `DockTile.qml`,
`Theme.qml`, `README.md`); it has produced no compiled binary. That task is out
of scope here and its in-progress work is not treated as proven evidence.

## Exact absence check (commands and output)

All commands ran from the worktree root under PowerShell 5.1 on Windows 11.

1. Tracked binary artifacts:

   ```
   git ls-files | Select-String -Pattern '\.(exe|dll|so|a|obj|o|pyd)$'
   ```
   Output: `(none)` — exit 0, zero matches.

2. Binary artifacts anywhere in the worktree:

   ```
   glob **/*.{exe,dll,so,a,obj,o,pyd}
   ```
   Output: `No files found`.

3. Qt build toolchain on PATH:

   ```
   Get-Command qmake, qmake6, cmake, mingw32-make, g++, cl
   ```
   Output: `qmake => MISSING`, `qmake6 => MISSING`, `cmake => MISSING`,
   `mingw32-make => MISSING`, `g++ => MISSING`, `cl => MISSING`.
   (`wsl.exe` is present but no Qt toolchain or compiled binary was located.)

4. GUI source in worktree and the main Canopy checkout:

   ```
   glob **/*.{cpp,h,hpp,cc,qml,pro,cmake}
   ```
   Output: only `examples/shell-pack-starter/ui/Main.qml`, a developer
   template explicitly marked "Developer template ONLY — not a live Canopy
   shell". No C++ entry point, no `.pro`, no compiled artifact.

5. Concurrent source-build workspace:

   ```
   Get-ChildItem C:\Users\X1\AppData\Local\Temp\opencode\qt-source-build-attempt-1 -Recurse -File -Include *.exe,*.dll,*.so,*.a,*.obj,*.o
   ```
   Output: `(none)` — only source files and `proto.zip` present.

## Self-test flags that would have been used

From `tools/mint_classic_qt_smoke.py:405-411`, each Qt run would use:

```
<binary> --approved-art-dir <dir> --landscape-wallpaper <path> \
  --self-test-approved --self-test-size <WxH> \
  --self-test-screenshot <path>
```

with sizes `1920x1080`, `1200x750`, `760x500` (`SIZES` at line 24). Required
markers are at lines 27-31; an optional `--icon-framing-review` flag adds the
framing marker at line 32/414. A successful pass requires exit code 0, exact
marker counts, a CRC-valid nonuniform PNG at the exact requested size, and a
measured SHA-256. `run_mint_smoke` also requires a real Linux Mint preflight
(`READY_FOR_TESTS`, `mint_identified`), which is likewise not available on
this host.

No such command was executed because no binary and no Mint guest exist.

## Tests

| Command | Result | Output excerpt |
| --- | --- | --- |
| `python -m unittest tests.test_mint_classic_qt_smoke -v` | PASS (0 run, 30 skipped) | `Ran 30 tests in 0.001s` / `OK (skipped=30)`; each skip reason: `POSIX executable-bit and shell-script semantics are unavailable on Windows` |

The smoke unit tests pass but are skipped on Windows; they validate the
evidence logic, not a real Qt launch. All-skipped is not a green runtime
claim. No runtime screenshot test was run — result NOT RUN.

## Scope and protected paths

Only this document was added. No approved icon, dock, wallpaper, Qt GUI file,
or protected path was modified. No files were committed, pushed, or merged;
the supervisor publishes. All screenshots that would have been written under
an output directory were never created; no placeholder or synthetic PNG was
generated.

## Conclusion

Genuine compiled-Qt runtime evidence is **NOT RUN** because no compiled binary
was proven in a prior campaign and none exists now. The blocking prerequisites
are a compiled Qt binary plus a real Linux Mint guest; both are absent. This
work is draft and must not be reported as a passing visual or runtime gate.
