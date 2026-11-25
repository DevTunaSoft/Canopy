# Classic top-bar clock label

Scope: `prototype/classic/ClockLabel.qml` plus its offline gate
`tests/test_classic_clock_label_polish.py`. The approved wallpaper, icon set,
dock, top-bar geometry, menu bar and `main.cpp` self-test are untouched. No
artwork was generated and no new timer was introduced.

## Readability and accessible name

- Visible text keeps the checked-in compact form `ddd d MMM · h:mm AP`,
  12 px `Font.Medium`, so top-bar width and clipping behaviour do not change.
- Screen readers receive `Accessible.name: "Local date and time: " +
  spokenDateTime`, where `spokenDateTime` uses `Qt.formatDate(currentTime,
  "dddd, d MMMM")` and `Qt.formatTime(currentTime, "h:mm AP")`. This spells
  out weekday and month ("Sunday, 5 April, 9:41 AM") instead of asking the
  listener to expand "Sun"/"Apr". The role remains `Accessible.StaticText`.
- Verified with the MSYS2 UCRT64 `qml` runtime: `Qt.formatDate` on
  2037-04-05 09:41 returns `Sunday, 5 April` and `Qt.formatTime` returns
  `9:41 AM`. Locale-specific full names are expected and appropriate for a
  screen reader.

## Contrast against approved wallpaper / plate

Approved mode paints the top bar with `#995e89a9` over the SHA-locked
`canopy-wave-preview.png`. The 384 sampled top-strip pixels of that PNG are
`#cbdde7`–`#ecefec`. Using the repository WCAG helper
(`canopy_features.accessibility.contrast_audit`):

| Foreground | Plausible plate/background | Minimum ratio | AA normal (4.5:1) |
| --- | --- | --- | --- |
| `#f7f5eb` (legacy off-white) | approved plate over wave | 2.031 | fails |
| `#1f2326` (new approved-mode ink) | approved plate over wave | 6.514 | passes |
| `#f7f5eb` (unchanged) | default `#ed1f2326` chrome | 11.940 | passes |

Therefore the clock selects dark ink only when `canopyApprovedMode` is true;
the default dark chrome keeps the original off-white. Both literals are
already approved colours in the Classic palette. This is a text-ink binding
inside the owned QML file: no plate, wallpaper, icon, dock or geometry edit.

`SYNTHETIC`: the ratios above are computed from the checked-in PNG bytes and
source literals, not from a live compositor or a screen-reader measurement.

## Minute-aligned wakeup contract

- One `Timer`, `interval: 60000`, `repeat: false`, `running: false`,
  `onTriggered: clock.refreshClock()`; `refreshScheduled` reports its state.
- `refreshClock()` takes `new Date()`, updates `currentTime`, and computes
  `nextMinuteDelay(now) = Math.max(1, 60000 - (seconds*1000 + ms))`. The 1 ms
  floor prevents a double fire at an exact boundary; every valid input lands
  on the next wall-clock minute.
- The timer restarts only while visible, stops when hidden and rearms on
  application activation and component completion. No per-second polling,
  animation, extra process or second timer was added.

`SYNTHETIC`: the Python mirror of the delay is exercised over all 60 seconds
and four millisecond offsets; it does not measure wall-clock drift.

## Verification performed

- Offline gate: `python -m unittest -v tests.test_classic_clock_label_polish`
  plus the pre-existing clock/menu/idle gates — all pass; each has negative
  controls for compact accessible names, unaligned delays, per-second timers
  and low-contrast ink.
- `qmllint ClockLabel.qml`: no errors (the pre-existing unqualified context
  property and `Qt.application.state` notices remain).
- Windows MSYS2 UCRT64 Qt 6 compile: CMake configure and Ninja build succeeded
  with GIO reported as an unavailable optional backend. Binary SHA-256:
  `a563e7cbba0e4b6da8d9eca5d935a4207a05a24a3d57ff09615054e6a2bd4d79`.
- Three compiled-Qt self-test screenshots, each `--approved-art-dir` with the
  exact eight-icon/wave manifest, `--self-test-approved`, and validated by
  `tools/check_screenshot.py`; `SELF_TEST_PASS: local top bar clock updates
  and fits` appeared in every run:

  | Size | SHA-256 |
  | --- | --- |
  | 1920x1080 | `e1259d2679a3b2e6f440d9fa0761277cc24265928297b3504fc7d98e1377a96c` |
  | 1200x750 | `ed06561da9d7ad569f08dd2511fa423f3778923085504ea570b3eca5d97cc0bf` |
  | 760x500 | `7bd8b4600654b30f545d524f57bc721faf4fa24379c95621a212902c2d99a144` |

- Cropped visual inspection found the compact date/time complete and unclipped
  at all three sizes. The 1 s self-test capture can fire while its own launcher
  fixture is open, so those frames include the launcher scrim; they are
  Windows toolchain evidence, not the approved resting composition, not owner
  visual approval and not Linux Mint acceptance.

`NOT_RUN`: live screen-reader announcement, Linux Mint/compositor acceptance
and real-desktop resource sampling were not performed. Screen-reader behaviour
is represented here only by the declared `Accessible.role`/`Accessible.name`
and the offline gate. No visual identity, artwork or geometry change was made;
the binding changes no timer count and no allocation loop, so no measurable
idle-resource regression is expected, but that expectation is unmeasured.
