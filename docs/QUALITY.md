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
- Native Plasma 6 reference guest and selected supported base, Wayland and X11 where applicable; Linux Mint remains the legacy comparison baseline.
- Low-end integrated graphics and a representative modern system.
- 1080p and HiDPI, single and multi-monitor, light and dark.
- Keyboard-only navigation, screen reader where supported, high contrast, reduced motion.
- Session restart, service failure, lock/unlock, suspend/resume, unplugged display, and unexpected exit.

## Validation evidence
Record commit SHA, hardware, distro/kernel, graphics driver, compositor, commands, duration, before/after metrics, screenshots, and PASS/FAIL/BLOCKED/NOT RUN. Never report a target as a measurement.

## PR acceptance
Unit and integration tests green, no unexplained performance regression, original asset licensing checked, docs current, and user-visible visuals reviewed. Keep a PR draft only until exact-SHA evidence and independent review exist; then promote eligible routine engineering work and authorized bounded GUI refinements within the current integration cycle.

## Draft PR lifecycle and integration authority (issue #132)
- A draft PR is a temporary working state, not a permanent holding area. Once its exact head SHA has passed every applicable check and its dependencies/conflicts are verified, promote it to ready-for-review.
- Green CI alone is never authorization to merge. Before any integration, verify: exact SHA tested equals SHA merged; all required checks passed; no unresolved dependencies or conflicts; regression/integration/security/performance checks completed; no protected visual change without owner approval; correct target branch and sequence; all requirements applicable to the target and scope satisfied. Final release requirements apply to public releases, not routine independently verified development integration. Follow the owner-approved trunk transition gates in [PLASMA6_PIVOT.md](PLASMA6_PIVOT.md).
- Independently verified engineering changes and authorized bounded GUI refinements may be integrated incrementally through the respective integration branch during migration and protected main after the Plasma baseline gates pass, with regression tests after each step. Preserve history; never force-push shared branches or bypass protections.
- Post-merge regression is mandatory **after** the merge; it is not a pre-merge gate. Keep pre-merge verification intact and do not create a circular rule requiring a post-merge result before an eligible merge.
- Honor the latest owner-authorized host-safe workforce ceiling (not a quota); do not increase it based on historical limits. Use isolated worktrees, explicit ownership and independent review; serialize expensive VM/build jobs as needed.
- Named owner holds on #279, #151 and #278 remain binding; general integration authorization does not waive them.
- Legacy standalone Qt release holds remain binding. Native Plasma baseline transition requires actual guest acceptance and applicable owner visual approval under the ADR. Main is a development trunk after transition; public releases require separate explicit owner authorization and all release gates.
- Do not stop independent engineering work because another task is awaiting approval.

## LacOS immutable release gates (planned)
Apply [LACOS_IMMUTABLE_ARCHITECTURE.md](LACOS_IMMUTABLE_ARCHITECTURE.md). Verify mount flags and core integrity before/after APT, Pacman, Flatpak and rootless Podman installation/update/remove, including malicious or malformed inputs and interrupted operations. Demonstrate signed atomic deployment, known-good boot rollback, persistence and compatibility of user/configuration state, power-loss/disk-full/failed-boot recovery, supported upstream security rebuilds, provenance and patch latency, and independent application/container updates. Test on actual hardware and isolated guests; do not confuse Distrobox integration with a sandbox or snapshots with backups. Benchmark full-system and per-app RAM, CPU, GPU, wakeups, startup, storage and image/container overhead; include inactive Shell Pack and stopped-container checks. Do not require production LacOS gates for ordinary Canopy development. Preserve existing resource budgets and owner approval requirements.

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
