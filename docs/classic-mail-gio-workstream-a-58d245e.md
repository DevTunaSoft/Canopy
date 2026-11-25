# Workstream A: Mail dock native GIO bridge evidence (base 58d245e)

Scope: one extra existing Classic dock app (Mail) is connected to the
already-merged native `SystemAppLauncher` GIO service through the same adapter
shape as Files/Browser. No QML, artwork, wallpaper, dock geometry or colour
bytes are changed. No shell, argv builder or second GIO path is introduced.

## Exact base and branch

- Integration tip re-queried with `git ls-remote`: `58d245e8db266e92260825b18434fcf967d4c444`
- Branch: `feat/classic-mail-dock-native-launch-58d245e`
- Owned paths: `prototype/classic/main.cpp`, `.github/workflows/classic-qt.yml`,
  `tests/test_classic_mail_dock_integration.py`, this evidence note.

## RED -> GREEN

- RED targeted command: `python -m unittest tests.test_classic_mail_dock_integration -v`
  on unmodified production: exit 1, 6 tests / 11 failures.
  Log SHA-256 `2982f02789e469c36ef16bbd39fb313a28e734061cdff7926ceb2e1b72563cdc`.
- GREEN targeted command: `python -m unittest tests.test_classic_mail_dock_integration tests.test_classic_browser_dock_integration tests.test_classic_dock_frozen tests.test_classic_qt_source -v`:
  exit 0, 22 tests OK.
  Log SHA-256 `e8b4b25e7cbc49ba0a8344ae9881bd8fb68bc0f45b0c916e8d759d354b034895`.

## Full Python suite (same Windows host, Python 3.14.9)

- Untouched base worktree at `58d245e`: `python -m unittest discover -s tests`,
  exit 0, `Ran 3222 tests`, `OK (skipped=43)`.
  Log SHA-256 `37596621da76503ae3357a96a7e86afd02944058f58f655a662ec5e4f7058bc1`.
- Feature worktree: same command, exit 0, `Ran 3228 tests`, `OK (skipped=43)`.
  Log SHA-256 `4ea393a2077e653eb1675b39f2e13effae589b9e70e5cfbcc3732485ed58b627`.
- Delta: +6 tests, +0 failures, +0 errors, +0 skips; no failure-name set to compare
  because both suites are clean.

## Compiled Qt (local Windows toolchain validation; not Mint acceptance)

- Toolchain: MSYS2 UCRT64 Qt6 Release, Ninja. CMake configure exit 0
  (log SHA-256 `15fd0e4ce6a60a31039da1e17dd335c67b32b908a7f184cfb48fe266da85ef75`),
  build exit 0, 43/43 steps
  (log SHA-256 `408e38e97d7532e20c68eb77a89a9329b7c3930904ed8e4830fa79b7d3f6de87`).
- Binary SHA-256: `5cbbf73b178c8141189ec7568a40c6b6c41fb447308912c49491549b0fefc655`.
- Run environment: `QT_QPA_PLATFORM=offscreen`,
  `QT_QPA_PLATFORM_PLUGIN_PATH=C:/msys64/ucrt64/share/qt6/plugins/platforms`,
  `QT_FORCE_STDERR_LOGGING=1` (Qt 6 Windows stderr logging).
- Capability probe: `CANOPY_GIO_DISABLED` — this UCRT64 build had no Linux
  GIO desktop-app-info headers, so native launch cannot run in this build.
  Log SHA-256 `d8de1aaa33c305514ad2ba23b43c9bac26648bd165151bc9e6609aadca556359`.
- Deny-list self-test: `SYSTEM_APP_LAUNCH_TEST_PASS: unknown or dangerous actions refused, no application executed`.
  Log SHA-256 `6cd81acb22f654bec1d2f0a78254784b84b62d6d886928937ed55f8f0926e6ff`.
- Mail compiled refusal fixture:
  `--enable-system-apps --approved-art-dir prototype/classic/assets/approved --self-test-mail-dock-status`
  exit 0, `MAIL_DOCK_STATUS_FIXTURE_PASS: refusal visible in launcher footer`,
  plus `CANOPY_MAIL_DOCK_NATIVE_LAUNCH_CONNECTED` and
  `CANOPY_MAIL_DOCK_REJECTED: unknown action`.
  Log SHA-256 `2dfaae095627fa76ecd6721372a3894ca7590d087330bb3a67d048dd017423a3`.
- Browser status fixture regression: exit 0,
  `BROWSER_DOCK_STATUS_FIXTURE_PASS`.
  Log SHA-256 `7a54a34d9c1b61d8760aaa8aa1faf70974afdf436c3daf668eea8e7d0d0064bf`.
- Negative control (no `--enable-system-apps`): exit 1,
  `MAIL_DOCK_FIXTURE_FAIL: native launch not enabled`.
  Log SHA-256 `41cffd2d5ef46f839b07490d92018126d466e4fe3283e18242c60069fd68604b`.

## Scoped / not run

- `SYNTHETIC`: the new Python source-contract tests read source text; they are
  not a runtime launch assertion.
- `SYNTHETIC`: the local offscreen Windows status fixture is toolchain
  validation only; it does not prove a Linux GIO launch.
- `NOT_RUN` locally: `--self-test-mail-dock-fixture` with real GIO. Exact cause:
  MSYS2 UCRT64 glib2 2.90.1 ships `gio/gio.h` but not
  `gio/gdesktopappinfo.h`, so the GIO-enabled target cannot compile on this
  host; the fallback build proves refusal only. The added Ubuntu Xvfb CI job
  is the authoritative isolated `thunderbird.desktop` marker check.
- `NOT_RUN`: Linux Mint guest acceptance, real mail client launch, real screen
  reader, idle CPU/PSS for this change. No new rendering loop, timer, polling
  service or background wakeup is added, so no runtime resource measurement
  was performed for this adapter.
- Screen-reader behavior: no new announcement API or accessibility property;
  the existing launcher footer `selectionMessage` Label binding is reused for
  the Mail refusal text. Actual screen-reader output remains `NOT_RUN`.

## CI evidence

The classic-qt workflow now runs the Mail launch fixture (isolated
`thunderbird.desktop` writing `mail-dock-launch-marker`), the Mail status
fixture (no mail app present), and the new source-contract test on the PR
head. CI conclusions are recorded in the PR body after the run reaches a
terminal state; this note does not claim green CI.
