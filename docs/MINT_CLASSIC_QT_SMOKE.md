# Linux Mint Classic Qt smoke evidence runner

**Status:** An executable, bounded, read-only **in-guest** smoke runner.
It has not yet been run in a real Linux Mint guest. Unit tests use an inert
Python script that imitates Qt command-line output; they do NOT constitute
Mint acceptance or prove a functional compositor/session.

Use the separately built Qt6 Classic binary from draft PR #100, or an
explicitly accepted successor. The optional source-framing variant currently
lives in draft PR #109. The original approved icon masters, alpine wallpaper
and optional Terminal-v3 candidate must come from the user's verified asset
bundle; they are not embedded or republished in this public repository.

## Run inside an existing Mint Cinnamon guest

First, boot Linux Mint normally and keep its default desktop/session intact.
Run the read-only preflight:

    python3 tools/mint_guest_preflight.py --json

If the preflight reports READY_FOR_TESTS and Qt6 has been compiled, create
an empty parent directory for evidence. Run as a regular user with the
real build's **lowercase 40-character source commit**:

    python3 -m tools.mint_classic_qt_smoke \
      --binary /absolute/path/to/canopy-classic-spike \
      --approved-art-dir "/absolute/path/to/approved-art" \
      --landscape-wallpaper "/absolute/path/to/alpine-wallpaper.png" \
      --terminal-refinement "/absolute/path/to/Terminal-v3.png" \
      --source-sha 0123456789abcdef0123456789abcdef01234567 \
      --output-dir "/absolute/path/to/new-evidence-folder"

Replace every example path and SHA with actual verified values. The optional
--icon-framing-review flag must only be used with a compiled build that
supports it; the runner verifies a distinct Qt self-test marker.

The runner enforces a real Mint graphical preflight, validates source path
safety, executes three Qt self-test capture processes with bounded timeouts,
and verifies their expected completion markers and PNG dimensions:

- 1920 x 1080
- 1200 x 750
- 760 x 500

The output folder must **not already exist**; no existing screenshots,
reports, desktops, configs or app windows are removed. It contains three
actual screenshot PNGs (when tests pass) and report.json with source-SHA
declaration, measured binary SHA-256, individual exit/marker counts, each
screenshot SHA-256, and PASS/FAIL per size. It deliberately omits raw Qt
stdout/stderr, user file paths and environment variables.

The declared source SHA must be supplied by the engineer; the runner does
not cryptographically prove that the executable was built from that commit.
The binary SHA-256 is measured independently, allowing later matching
against trusted GitHub artifacts.

## What PASS means and does NOT mean

PASS means the compiled Qt application's built-in checks and three valid
resolution screenshots worked **under the identified Mint guest session**.
It does not certify visual quality, optical icon alignment, Nemo/Firefox
launch/focus, window management, accessibility, crash resilience, 5-minute
RAM/CPU performance, reboot/rollback, or a full alternative desktop session.
Those are separate entries in docs/RELIABILITY_99_GATE_AUDIT.md.

The runner never starts a new login session, installs apt packages, changes
display-manager state, moves windows, executes arbitrary user shell strings,
or uploads evidence to external services. Treat output screenshots as
potentially private if your desktop contains personal information.

## Regression tests (on any developer machine)

    python3 -m unittest tests.test_mint_classic_qt_smoke -v

Unit tests check 3-size orchestration, incorrect PNGs/dimensions, missing
Qt markers, nonzero process exit, timed-out processes, nonexistent assets,
symlinks, duplicate-output refusal, privacy-preserving JSON, and rejection
of environments claiming to be Ubuntu rather than Mint.
