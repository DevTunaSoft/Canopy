# Quality gates and performance measurement

**All budgets are initial targets, not verified results.** Revise only with reproducible benchmark evidence.

## Targets
- No continuously busy shell loop when idle; favor signal-driven behavior.
- No mandatory always-on blur, live wallpaper, or constant animation.
- Keep incremental shell idle memory small; initial engineering target <= 200 MiB proportional set size for shell-owned processes on the reference machine, excluding compositor and existing system services. Report exclusions clearly.
- Target <= 1% average shell-owned CPU over a five-minute idle measurement on the reference machine, with measurement conditions stated.
- Aim for smooth 60 Hz interactions on reference hardware; measure frame time distribution and dropped frames rather than declaring smoothness by inspection.
- Test cold/warm launch and memory growth after repeated app opening, theme switching, and monitor changes.

## Required matrix
- Linux Mint release and desktop/session compatibility, Wayland and X11 where applicable.
- Low-end integrated graphics and a representative modern system.
- 1080p and HiDPI, single and multi-monitor, light and dark.
- Keyboard-only navigation, screen reader where supported, high contrast, reduced motion.
- Session restart, service failure, lock/unlock, suspend/resume, unplugged display, and unexpected exit.

## Validation evidence
Record commit SHA, hardware, distro/kernel, graphics driver, compositor, commands, duration, before/after metrics, screenshots, and PASS/FAIL/BLOCKED/NOT RUN. Never report a target as a measurement.

## PR acceptance
Unit and integration tests green, no unexplained performance regression, original asset licensing checked, docs current, and user-visible visuals reviewed. Keep a PR draft only until exact-SHA evidence and independent review exist; then promote eligible nonvisual work within the current integration cycle.

## Draft PR lifecycle and integration authority (issue #132)
- A draft PR is a temporary working state, not a permanent holding area. Once its exact head SHA has passed every applicable check and its dependencies/conflicts are verified, promote it to ready-for-review.
- Green CI alone is never authorization to merge. Before any integration, verify: exact SHA tested equals SHA merged; all required checks passed; no unresolved dependencies or conflicts; regression/integration/security/performance checks completed; no protected visual change without owner approval; correct target branch and sequence; all requirements applicable to the target and scope satisfied. Final release requirements apply to final release integration, not routine independently verified nonvisual integration.
- Independently verified nonvisual changes may be integrated incrementally through the integration branch with regression tests after each step. Preserve history; never force-push shared branches or bypass protections.
- Classic Qt final desktop integration remains release-blocked until actual Linux Mint acceptance and owner visual approval are recorded. Keep those PRs in draft regardless of CI status.
- Do not stop independent engineering work because another task is awaiting approval.

## Additional Shell Pack release checks (planned)

Each new desktop experience needs version/capability compatibility,
independent user visual approval, original or licensed assets, keyboard
and screen-reader evidence, real Qt or applicable UI-engine screenshots
and measured resource overhead versus the existing Classic reference.

Once switching exists, require repeated A→B→A transitions, app/window state
preservation, failed-switch rollback, session recovery, memory cleanup
and proof that inactive packs do not run independent desktop services.
Metadata validation is not runtime, sandbox or security verification.
See [Shell Pack architecture](SHELL_PACK_ARCHITECTURE.md).

## Multi-angle reliability review (initial 99 gates)

Use the [99-angle reliability matrix](RELIABILITY_99_GATE_AUDIT.md) for
cross-functional acceptance. It identifies real Linux Mint/compositor work,
power-failure recovery, QML trust boundaries, app lifecycle management,
optical visual signoff, accessibility, 5-minute resources, and packaging
as separate test gates. The matrix is intentionally not a percent-complete
score: most P0 user-facing requirements are still unverified or unbuilt.
Don't turn a single green workflow into a release claim.
