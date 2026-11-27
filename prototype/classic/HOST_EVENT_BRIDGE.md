# ND-039 — compiled Classic host-event bridge (build-local evidence)

## Scope

`prototype/classic/main.cpp` gains one bounded, event-driven compiled seam,
`ClassicHostEventBridge`, for the four reviewed protocol-v2 host-event tokens.
It routes each token to an already-merged compiled bridge and adds no topic,
payload field, protocol version, transport, timer, poll loop, process, service,
visual geometry, QML, asset or protected-file change.

- `capabilities.report` → `QuickControlsHostStateController::applyHostEvent`
  (quick-controls state and display power detail).
- `session.state.changed` → the same read-only controller; `view("session")`
  stays unknown, so no privileged control is offered.
- `window.state.changed` → `WindowActivationState::applySnapshot`, guarded by
  the frozen required-key set so a malformed token cannot clear live state.
- `app.catalog.changed` → a bounded `catalogRefreshRequested` token that
  main wires to rebinding the existing read-only catalogue bridge. Native
  catalog re-production remains in the already-merged Python host bridge.

The dispatcher records fixed outcome tokens only (`rejected`,
`window-rejected`, `refresh-limit`, `quick-controls-applied`,
`session-observed`, `window-applied`, `catalog-refresh-requested`); no caller
text is echoed into an outcome or a log. Hard ceilings: 64 events per process
lifetime and 16 deterministic history entries. There is no caller-configurable
bound, no retry loop and no background wakeup.

## Verification

- Source contract: `tests/test_nd039_host_event_bridge.py` (topic set equals
  `canopy_core.host_events.TOPICS`, routing targets, fail-closed order, caps,
  no transport/poll/visual constructs, scope isolation).
- Compiled flag: `--self-test-host-event-bridge` exercises all four tokens,
  rejects an unlisted topic, an oversized value and a partial window snapshot,
  then asserts 6 dispatches / 3 accepted / 3 rejected / history 6 of 16 and
  prints `HOST_EVENT_BRIDGE_SELF_TEST_PASS`.
- Foundation: `python tools/check_foundation.py` and the targeted unittest
  modules above. Offscreen compile is `COMPILE_NOT_RUN` unless the dedicated
  Qt toolchain is available and no sibling suite is loading the host.
- No full suite, no VM and no main/protected merge were run in this task.
  Offscreen compile is `COMPILE_NOT_RUN`: at verification time a competing
  `python -m unittest discover -s tests -v` (RI069, PR707 post-merge) and a
  sibling ND-040 CMake/Ninja build were both live on this host, so the suite
  was not quiescent and the serialized Qt build was deliberately not started.

## Resource impact

- Measured (`SYNTHETIC`): Python source-contract test counts and durations on
  the Windows host; static allocation accounting (two bridge pointer members,
  four int counters, one QString and one bounded QStringList of at most 16
  fixed tokens).
- Deliberately not measured (`NOT_RUN`): real shell-owned PSS/CPU, Mint guest
  behavior, compiled Qt frame timings, monitor/DPI signal rate and full-suite
  deltas. The dispatcher adds no timer, thread, cache, service, animation or
  repeat rendering work, so it trades no stability, security, accessibility or
  approved visual quality for a minor gain.
- Screen-reader behavior is `NOT_RUN`: screen-reader announcements register no
  new source and mutate no accessibility label.

## Blocker — display/scaling relayout

Applying a logical-DPI / display-change *plan* in the compiled shell would
resize the window or change QML bindings, i.e. modify frozen visual geometry.
The merged scaling modules (`canopy_features.dock.display_change_response`,
`display_scaling_contract`) are pure Python decision records with an explicit
`NOT_RUN` compiled-wiring status, and no compiled scaling bridge exists at the
integration tip. Compiled delivery of `display/scaling` state therefore stops
at `AWAITING_CHATGPT_VISUAL_APPROVAL`: owner approval is required before any
compiled relayout consumer can be written. This task deliberately does not
fabricate a compiled scaling bridge or edit approved visual source.

Current head: to be recorded at commit in the PR body and evidence log.

## Terminal dock tile — native launch resolution (ND follow-up)

Native functional observation carried into this source change: the frozen
Terminal dock tile stayed preview-only and reported a refusal footer, while a
GIO `konsole.desktop` activation succeeded in the same session at
1920x1080, 1200x750 and 760x500. That observation is runtime evidence scoped
to the tested session; it is NOT visual acceptance and NOT a release gate.

`prototype/classic/main.cpp` now gives Terminal its own exact-label adapter,
`TerminalDockLaunchBridge`, instead of leaving it in the generic remaining-app
bridge. The adapter:

- accepts only the frozen dock label `Terminal` and refuses lookalikes before
  any launcher call;
- uses the one host-owned `SystemAppLauncher` (the validated GIO path) when the
  trusted window-activation snapshot reports `LAUNCH` and that service can
  resolve an installed desktop entry;
- otherwise opens the existing native launcher with the fixed neutral status
  `Choose an installed terminal application` — a **documented fallback**, not
  a refusal footer and never a false success claim;
- keeps truthful refusals only for the explicit `FOCUS` (needs a grant) and
  `IGNORE` (launcher disabled) states.

The closed desktop-entry allowlist in `SystemAppLauncher.cpp` is unchanged:
no new desktop ID, argv, path, URL, shell, `QProcess`, second GIO path,
compositor, QML, icon, wallpaper, dock geometry or colour was added. The
fallback hands selection to the native launcher rather than widening a
security boundary. The compiled fixture keeps both `--self-test-terminal-dock-fixture`
and `--self-test-terminal-dock-status` with the same Pass markers; the status
case now asserts the neutral fallback and the absence of refusal text.

Verification: `tests/test_classic_terminal_dock_native_launch.py` (source
contract plus frozen-dock byte pin), `tests/test_classic_remaining_dock_integration.py`,
`tools/check_foundation.py` and a clean trial merge against the exact source
pin `fef38c311736b7cdded3acedde4bae985237a6e3`. The terminal-specific compiled
GIO fixture is run by CI, not by this source-contract change: compiled runtime
and real Plasma/Mint acceptance remain `NOT_RUN` here.

Resource impact: measured (`SYNTHETIC`) — Python source-contract test counts
and static allocation accounting (three pointer members and two fixed QString
constants on one QObject; no timer, thread, cache, service or polling).
Deliberately not measured (`NOT_RUN`) — real shell-owned PSS/CPU, compiled Qt
frame timings, desktop session behavior and full-suite deltas. Screen-reader
behavior is `NOT_RUN`: no new accessibility label or announcement source is
registered; the existing launcher status text is reused. No stability,
security, accessibility or approved visual quality is traded for a minor gain.
This change is source/functional only: no visual approval is claimed.
