# Next Tasks

## Immediate

1. Review PR #135 and PR #151. They are draft; do not merge without approval.
2. Provide the approved alpine/autumn wallpaper asset.
3. Configure the `Canopy-Test-Mint` VM with Guest Additions and an SSH key.
4. Rebase verified Qt work onto `main` after review.
5. Run Linux Mint guest acceptance and five-minute idle resource measurements.

## Implementation backlog

The supervisor includes 100 bounded engineering tasks in
`tools/canopy_backlog_100.py`, covering launcher, dock, app launching, windows,
Mint compatibility, installer, reliability, security, performance and
accessibility. These tasks are implementation work, not documentation-only
follow-ups.

## Blocked tasks

- Mint guest acceptance: VM powered off, no Guest Additions, no SSH key.
- Owner visual approval: not granted.
- Alpine wallpaper integration: source asset unavailable.
- Real installed-application launch and window focus: not tested in Mint.

## Do not do

- Do not generate replacement artwork.
- Do not modify approved dock geometry.
- Do not merge without green tests and visual approval.
- Do not create duplicate supervisors or documentation-only PRs.
- Do not treat green CI as release approval.
