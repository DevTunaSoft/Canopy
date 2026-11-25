# Classic clock accessibility without visual change

Base: `integration/canopy-classic-20261123` tip
`9a37427212fab0e30966de03c6c43f897348f746`. Branch:
`a11y/clock-accessible-name-9a37427`. Draft PR only; no `main` merge.

## Scope decision

`polish/classic-clock-label-ec4ccc6` (PR #612) proposed two things in
`prototype/classic/ClockLabel.qml`: an unabbreviated screen-reader name and a
change of the approved-mode ink from `#f7f5eb` to `#1f2326`. The ink change
alters rendered pixels and is NOT_APPROVED under the owner's visual lock, so it
is excluded in full. The accessibility change alone is possible with zero
rendered change and is the entire QML delta:

- `spokenDateTime` spells out the local weekday and month (`dddd, d MMMM`) plus
  `h:mm AP` for `Accessible.name`.
- `Accessible.role` remains `Accessible.StaticText`.
- `text` (the compact visible `ddd d MMM · h:mm AP`), `color: "#f7f5eb"`,
  `font.pixelSize: 12`, `font.weight: Font.Medium`, the single minute-aligned
  non-repeating timer, visibility rearm and application-resume rearm are byte
  identical to the base. No `canopyApprovedMode` branch exists in the clock.

No artwork, wallpaper, dock, icon, `main.cpp`, geometry or timer-count file was
touched. There is no new animation, polling loop, process, asset or background
service.

## Offline gates

```
python -m unittest -v tests.test_classic_clock_accessibility_no_visual_change \
                     tests.test_check_visual_region_identity
Ran 14 tests in 0.967s ... OK
```

RED on the exact base worktree (same test file copied in, then removed):
`Ran 8 tests ... FAILED (failures=2)`; primary failure
`AssertionError: unabbreviated spoken date/time missing`.

The clock gate pins each visible/wakeup input literal, the single color binding
and the unabbreviated spoken name, and includes negative controls for a compact
accessible name, dark ink, a changed visible date format and a per-second timer.
The region-identity checker is stdlib-only and its tests cover identical
captures, a one-pixel RGB delta, an alpha-only delta, out-of-bounds regions, a
dimension mismatch and a corrupt PNG CRC. `qmllint ClockLabel.qml` exits 0 with
only the pre-existing `Qt.application.state` warning.

## Compiled Qt evidence (Windows MSYS2 UCRT64, offscreen/software)

Toolchain: CMake 4.5.1, Ninja 1.13.2, g++ 16.2.0. Environment:
`QT_QPA_PLATFORM=offscreen`, `QT_QUICK_BACKEND=software`,
`QT_QUICK_CONTROLS_STYLE=Basic`, `QT_FORCE_STDERR_LOGGING=1`,
`LIBGL_ALWAYS_SOFTWARE=1`, `TZ=UTC`, `LANG=C`. Both sides were compiled from
real isolated worktrees pinned to the exact base SHA, with fresh build
directories. GIO is unavailable on this host (`gio-unix-2.0 dev package
absent`), so native app launching compiles as a disabled fallback; the Linux
GIO fixture stays a CI gate.

| Binary | SHA-256 |
|---|---|
| Base `canopy-classic-spike.exe` | `dddd2e1353f188f2b5bb9dffda1b885d28c748acb914db14f28fc7e679d462f9` |
| Feature `canopy-classic-spike.exe` | `1865ed9a00e6f7940ae809fe8477a4c6ceca0e3e81378889e359383e009d1ddd` |

Both binaries were exercised with `--approved-art-dir
prototype/classic/assets/approved --self-test-approved --self-test-size <size>
--self-test-screenshot <png>`. All six runs returned rc=0, all six logs contain
`CANOPY_APPROVED_ART_VERIFIED` and `SELF_TEST_PASS: local top bar clock updates
and fits`, and no `SELF_TEST_FAIL` line appeared. Each PNG passed
`tools/check_screenshot.py` at its declared dimensions.

### Three screenshots: byte-exact visual identity

The definitive base/feature pairs were captured back-to-back inside the same
UTC minute (2026-11-25 22:33:01Z–22:33:30Z). A first capture round that crossed
a minute boundary produced 92 differing pixels, all confined to the rightmost
320 px of the top bar (the live clock text) and zero elsewhere; the same-minute
pairs below are byte-identical over the whole frame, which is the stricter
result. `tools/check_visual_region_identity.py` decoded each 8-bit RGB PNG and
compared every pixel byte-for-byte: full-frame verdict `PASS`,
`differing_pixels=0` at all three sizes.

| Size | Base and feature PNG SHA-256 (identical) | Region JSON SHA-256 |
|---|---|---|
| 1920x1080 | `e005f7a6381fb75bf5c3a15a0cbb17b2249ec1839cbc66cc9a695b25adc4ba1e` | `e51cd9bf9ad81715765de6d3bf6e3c8f103acd2a0b528b97de4239956f1faf5c` |
| 1200x750 | `2fe9fea22ccd64de42664b9aa7c7fedea48a06ae4f1a2bb03f71c7684ac23992` | `82403d58c24a42614a1bd6afbb646da894f80863f2ce77f37062e779b174aa5a` |
| 760x500 | `b9781183aeee71094bdfb47712ca575d636318e1222a6f1a9a66d581d01dd584` | `0908ef4df468769db26e85e7586055d873e213c39873eaa9b0dfcbe5d64c2504` |

Logs, both capture timelines and all twelve PNGs are covered by the on-disk
manifest `C:/Users/X1/AppData/Local/Temp/clock-evidence-9a37427/SHA256SUMS.txt`.
Offscreen toolchain captures are evidence of identical rendering, not owner
visual approval or Linux Mint acceptance.

## Full suite (same host, exact pinned worktrees)

```
base   9a37427: Ran 3555 tests in 1099.616s ... OK (skipped=48)
feature head:    Ran 3569 tests in 1100.259s ... OK (skipped=48)
```

The +14 tests are exactly the two new gates. Zero FAIL/ERROR names in both;
normalized FAIL/ERROR-name set SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` for each.
Raw logs: base
`f5ef19aa74c68e15f4cdce74ff0abf115ea763efbdf446522490702535ea81d8`, feature
`e0bf9d2ea60c62f510f26f5a5a63747526867d78c41547c2bb035261d110afd7`.

After capture, the live integration tip advanced to `164e0e1d` (PR #622,
shell-menu typography/states only). `git diff --name-only
9a37427..164e0e1d` contains no owned path, so no rebase or re-verification was
needed; the draft PR targets the integration branch.

## Resource / evidence note

- Measured: compiled Qt self-test runs, twelve screenshot captures, byte-exact
  full-frame comparisons and two full offline suites on this Windows UCRT64
  host. These are toolchain and `SYNTHETIC`-style byte checks, not a runtime
  performance benchmark; suite wall-clock numbers are durations, not
  optimization evidence.
- `NOT_RUN`: real-desktop idle CPU/PSS sampling, Linux Mint/compositor
  acceptance, installer behaviour and live screen-reader announcement.
  Screen-reader behavior is represented only by `Accessible.role` and
  `Accessible.name` plus the offline gate; no live AT announcement is claimed.
- No stability, security, accessibility or approved-visual tradeoff was made
  for a performance gain. The change adds one read-only string property and
  rebinds one accessible name; the timer, visible text and approved ink are
  unchanged.
