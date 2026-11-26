# PE-019 startup phase profile — exact candidate at 90dd463

**Classification: `SYNTHETIC` / `WINDOWS_HOST_UCRT64_OFFSCREEN`.** These are
bounded repeated offscreen launches of a compiled Windows binary. They are not
Linux Mint, not Xvfb, not a real desktop, not GPU evidence, not release
acceptance and not a speedup claim. No visual asset, QML geometry, icon or
wallpaper file was changed. No merge was performed.

## Exact pins and serialization

- Source pin: `90dd463dc96d70bae00cfe4b2391784a86fb0b12`.
- Baseline binary: PE-002 candidate
  `db107f2dc0e4f3932eb478ab76fb06757aa558da328d5553405db07c2877c6a9`.
- Candidate binary: `ca2253df8642999922b5bacb114ddf565f14e50078310b67a560cb37143f11b9`
  (two earlier experimental candidates are retained in the scratch evidence
  index as superseded, not as final claims).
- Toolchain: MSYS2 UCRT64, Qt 6.12.0, `QT_QPA_PLATFORM=offscreen`,
  Windows 11 x86_64 software raster path.
- Before this worktree's build, the RI-003 clean-build process was observed
  active, so no build was started. RI-003 finished with `build_rc=0`
  at `2026-11-26T17:46:26Z`; this worktree's isolated build then finished with
  `build_rc=0` at `2026-11-26T17:51:47Z`, with two bounded incremental rebuilds
  after that. This task ran no full suite; an unrelated agent's targeted suite
  was active during the later launches, so timing is scoped context only.

## Measured baseline phases

One warm-up plus five measured launches per mode, alternating mode order.
Timings are monotonic milliseconds from process spawn to each `qInfo` marker
line on stderr; a phase is the difference between two markers.

| Mode | Window-ready median (ms) | Range (ms) |
|---|---:|---:|
| Qt/core init only (`--self-test-system-apps-capability`) | n/a (early exit, 123 ms total) | 93–239 |
| Core + activation snapshot (`--self-test-launcher-catalog-model`) | n/a (early exit, 99 ms total) | 87–200 |
| Full QML scene, no approved art (`--self-test-quick-controls`) | 516 | 412–545 |
| Full QML scene + approved art (approved self-test) | 751 | 560–857 |

Approved-mode phase medians: art SHA verification 137 ms (116–202), icon
provider construction 94 ms (81–177), main QML load 436 ms (353–482),
QuickControls overlay 14 ms, Settings overlay 19 ms. The approved path adds
235 ms over the same scene without approved art, accounted for by the 137 ms
verification and 94 ms icon phases. The demonstrated startup bottleneck is
duplicate work in that path: the gate reads and hashes eight PNGs, then the
icon provider reopens and decodes those same eight files before the scene is
allowed to open.

All wall-clock numbers in this section are `SYNTHETIC` host samples on a noisy
multi-agent machine. They identify where work happens; they are not a
speedup estimate.

## Minimal fix

`verifyExactArtwork()` now retains the eight exact, already SHA-verified PNG
payloads in a bounded `QHash`, and `RoundedDockIconProvider` decodes those
bytes directly. The eight file opens/reads previously performed a second time
by the icon provider are eliminated; the payload map is cleared immediately
after the fixed icon cache is decoded. The wallpaper is verified but never
retained. No other production behavior changed.

Deterministic change: 8 duplicate file opens/reads removed on every approved
startup; 1,627,322 bytes of verified icon payload are retained transiently
until provider construction instead of being reread from disk, then released.
The accepted digest set, manifest schema, path/symlink guards and fail-closed
comparison are unchanged.

A deterministic source-contract gate
(`tests/test_pe019_verified_art_bytes_reuse_contract.py`) asserts the byte
handoff, bounded retention, retained security guards and a mutation that
restores duplicate file reading.

## Verification actually run

- `python -m unittest discover -s tests -p 'test_pe019_verified_art_bytes_reuse_contract.py'`: 2 tests, OK (mutation rejected).
- `python -m unittest discover -s tests -p 'test_approved_art*.py'`: 18 tests, OK.
- Compiled approved-art self-test on the final candidate: rc=0, 21 `SELF_TEST_PASS` lines, `CANOPY_CLASSIC_WINDOW_READY` and a nonuniform 1200x750 frame.
- Corrupted-art negative control (one byte flipped in a scratch copy, never in
  the approved tree): rc=3, `APPROVED_ART_FAIL: SHA-256 mismatch`, no screenshot
  written. The gate still fails closed.
- Alternating A/B on the exact two binaries: 10 pairs, 10/10 paired frames
  byte-identical, 6/10 pairs favouring the candidate on time-to-window-ready,
  median base-minus-candidate delta **+49.89 ms** on this host. This is scoped
  `SYNTHETIC` context, not a general speedup claim; the eliminated file reads
  are the deterministic evidence.
- Separate five-launch candidate profile: approved window-ready median 629 ms,
  art phase 114 ms, icon phase 103 ms; cross-pass numbers are not compared as
  a speedup.

## Explicitly not measured (`NOT_RUN`)

Linux Mint guest and real desktop sessions, Xvfb, GPU/compositor cost, true
scheduler wakeups, five-minute shell-owned PSS, full `unittest discover -s tests`
(fixture serialized under the 2026-11-26 directive), accessibility behavior
including screen-reader output, and owner visual acceptance. No target in
`README.md` or `docs/QUALITY.md` is claimed as attained.
