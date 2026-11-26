# Canopy Classic Mint session architecture (decision plan, guest NOT_RUN)

Issue #107 (`P0 architecture gate: real Mint session/compositor and reversible
shell integration`) was re-queried while writing this document and is **OPEN**.
This is a proposed architecture and test plan, not an accepted release decision
and not evidence of native Mint execution. Native session acceptance is
**NOT_RUN** until a real guest run is recorded.

## Chosen integration strategy (proposal for review)

**Phase 1 — user-level application entry only.** Canopy Classic is installed
as a per-user desktop entry (`org.canopy.ClassicPreview.desktop`) in
`$XDG_DATA_HOME/applications`. It never replaces Cinnamon, the display manager,
the compositor, the window manager or any system file. The default Mint
session remains the owner of window management, focus, notifications, power,
accessibility, settings and input. Canopy is one unprivileged application
window/dock in that session, not an alternative login session.

This option is deliberately narrower than the other two choices in #107
(full separate session with an existing WM, or a new compositor integration).
It satisfies the reversible-installation requirement without claiming desktop
shell ownership. Promotion to a session-level shell requires a separate
architecture decision, independent review and guest evidence; it is not
authorized by this document.

### One active compositor

Only the session's existing compositor runs. The Qt preview uses the normal
X11/Wayland connection provided by that session and does not start, replace or
nest a compositor. On Wayland, unsupported shell protocols must produce a
fail-closed diagnostic rather than a silent fallback that pretends full
integration. On X11, the existing Cinnamon/Mutter ownership remains intact.
Session type is a consistency hint only; `READY_FOR_TESTS` from
`tools/mint_guest_preflight.py` is a prerequisite, not a pass.

### Service and ownership boundaries

| Responsibility | Owner in Phase 1 | Canopy behavior |
|---|---|---|
| Window stacking, focus, workspaces | Cinnamon/Mutter | Query/request only; no override |
| Application discovery and launch | GIO/desktop entries | Opt-in native launch via real desktop entries |
| Notifications, power, brightness | Desktop daemons | Do not duplicate; disclose unsupported items |
| Accessibility/settings | Desktop session + Qt | Respect session settings; no global writes |
| Shell Pack/QML trust | Not loaded in Phase 1 | A local QML path or manifest is not a sandbox |
| Session switching | Out of scope | No compositor handoff or focus-transfer claim |

## Install, uninstall and recovery boundary

The exact-state planner in `canopy_features/mint/install_recovery_plan.py` and
the real entry installer in `tools/register_classic_preview.py` are the only
Phase 1 installation surface. See `CLASSIC_INSTALL_RECOVERY.md` for the exact
paths, byte bounds, dry-run commands and rollback contract.

Fail-closed rules:

- root, system-owned paths, symlinked components and `..` traversal are
  refused before any action;
- a modified/unmanaged entry is never deleted automatically;
- session-entry probes (autostart/xsessions names matching the managed ID)
  make a state unsafe;
- no plan may claim a session, compositor, display-manager or system-path
  change; such a plan fails structural verification.

## In-session visual mode switching and crash rollback

Not implemented in Phase 1. A future design must define one active compositor,
focus transfer, retained application windows, subscription cleanup, failed
switch rollback and a safe logout/reboot route before any session-level
promotion. Until then, switching modes is **NOT_IMPLEMENTED** and native
session behavior is **NOT_RUN**.

## Guest execution plan (to be run by an independent agent)

1. Take a recoverable snapshot of a disposable Linux Mint 22.3 Cinnamon VM.
2. Record guest release, session type, exact source SHA and compiled binary
   SHA-256; run the read-only preflight.
3. Run `register_classic_preview.py install --dry-run`, save the bounded JSON
   plan, then perform the real user-level install and verify exact bytes.
4. Launch the preview inside the real session; check window creation, native
   app launch/focus, keyboard navigation and graceful exit; log failures.
5. Run `uninstall`, verify the two owned paths are absent and confirm the
   original Cinnamon session, wallpaper, dock and display geometry are intact.
6. Repeat after logout/re-entry and reboot; record a snapshot-based recovery.
7. Measure real five-minute shell-owned PSS/CPU and startup/frame pacing in
   the guest. Host-orchestrated or Xvfb evidence is scoped, not acceptance.

A green offline test suite does not satisfy any of these steps.

## Evidence status and resource note

- Native Mint session launch: **NOT_RUN**.
- Compositor/window-manager integration: **NOT_RUN**.
- Real app launch, focus handoff, workspace switching, logout/re-entry:
  **NOT_RUN**.
- Guest PSS/RSS, CPU, GPU, wakeups, frame pacing and screen-reader behavior:
  **NOT_RUN**.
- Offline planner tests: `SYNTHETIC` bounded pure-Python checks only.

This document changes no code, visual asset, session configuration or VM
state. It does not trade stability, security, accessibility or approved visual
quality for a resource gain. Owner visual acceptance and independent review
remain separate gates.
