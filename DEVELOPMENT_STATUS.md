# Development Status

## Current branches and PRs

- `main`: clean; no desktop shell released.
- `feat/windows-multi-agent-supervisor-20261121`: supervisor implementation.
- `feat/classic-qt-port-buildable-20261121`: Classic Qt prototype and evidence.
- Stacked agent branches: Qt Mint acceptance, desktop launch, preview packaging.
- Draft PRs #135 and #151–#159 are open; none merged.

## Verified results

- `tests/test_canopy_supervisor.py`: 82 tests PASS.
- Full applicable suite: 354 tests PASS, 53 POSIX-only skips on Windows.
- PR #151 CI: `foundation` PASS and `qt-evidence` PASS.
- Real Qt compile: 24 Ninja steps, executable `canopy-classic-spike`.
- Real screenshots: 1920x1080, 1200x750, 760x500; SHA-256 values recorded in
  PR #151.
- Five-minute idle sample: CPU 0.013% of one core; PSS 57,631 to 60,775 KiB.
- GIO launcher self-test: `CANOPY_GIO_ENABLED`, isolated desktop entry launch
  PASS.

## Blocked results

- Linux Mint guest acceptance: NOT RUN.
- Owner visual approval: not granted.
- Alpine wallpaper: source asset unavailable.
- Real installed-application launch and window focus: not tested.
- Five-minute idle measurement on reference Linux Mint hardware: NOT RUN.

## Open engineering issues

- Supervisor campaigns were incorrectly treated as successful when evidence
  reported BLOCKED/NOT RUN; corrected in roadmap campaign status.
- Supervisor retry IDs exceeded task ID length; corrected with `-rN`.
- OpenCode CLI moved from `opencode-ai` to `@opencode/cli`; worker launch fixed.
- Qt SVG runtime plugin was missing; CI installs `libqt6svg6`.
- Files browser and menus are integrated but need owner visual review.
- Mint VM has no usable guest session.
