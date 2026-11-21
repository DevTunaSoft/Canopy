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
Unit and integration tests green, no unexplained performance regression, original asset licensing checked, docs current, and user-visible visuals reviewed. Keep PR draft until evidence exists.

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
