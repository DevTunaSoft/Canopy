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
`window-rejected`, `quick-controls-applied`,
`quick-controls-applied-deferred`, `session-observed`,
`session-observed-deferred`, `window-applied`, `window-applied-deferred`,
`catalog-refresh-requested`, `catalog-refresh-pending`,
`catalog-refresh-coalesced`); no caller text is echoed into an outcome or a
log. The former 64-event process-lifetime freeze is removed. Overload is now a
lazy token bucket: 16 tokens, one refill per second from a monotonic clock
sampled only inside `dispatch()`, so valid events continue indefinitely when
spaced. Authoritative state commits happen before the bucket check and are
never reported as failures: an empty bucket yields an explicit `*-deferred`
token while the committed state stays fresh.

A fresh `app.catalog.changed` fingerprint is emitted **before** its token is
charged. When the bucket is empty, a single boolean `m_refreshPending` latch
carries the authoritative refresh to the next real `dispatch()` that observes
a token; the latch flush emits exactly once and clears. Duplicates within the
four-fingerprint window coalesce and spend no token. The latch is one bit, not
a queue: there is no retry path, timer thread, poll loop, background wakeup,
new topic, payload field or new transport. Outcome history stays a fixed
16-entry ring. There is no caller-configurable bound.

## Follow-up scope (PR724 audit)

This branch is a standalone, non-stacked change at
`fef38c311736b7cdded3acedde4bae985237a6e3`. It carries the reviewed bounded
limiter from PR #724 together with the three audited fixes: pending-refresh
latch, deferred authoritative catalog refresh with correct token ordering,
and truthful outcome semantics for already-committed state. It does not merge
PR #724 or any other branch, and it leaves the downstream Python catalog
consumer's separate 64-event ceiling for its own follow-up.

## Verification

- Source contract: `tests/test_nd039_host_event_bridge.py` (topic set equals
  `canopy_core.host_events.TOPICS`, routing targets, fail-closed order, fixed
  size bounds, no transport/poll/visual constructs, scope isolation).
- Bounded-lifetime regression: `tests/test_host_event_bounded_lifetime.py`
  (source asserts no lifetime gate, executable model with injected clock:
  200 spaced valid dispatches all accepted past 64, same-tick burst keeps every
  authoritative state commit with truthful `*-deferred` outcomes, history and
  fingerprint rings stay at 16/4, **20 ticks of 17 valid events per tick with
  the catalog event last deliver 20 refreshes**, and source assertions forbid
  polling, timer threads, new topics and unbounded queues).
- Compiled flag: `--self-test-host-event-bridge` exercises all four tokens,
  rejects an unlisted topic, an oversized value and a partial window snapshot,
  then asserts 6 dispatches / 3 accepted / 3 rejected / history 6 of 16; it
  also drives 200 valid dispatches past the old 64 ceiling, a 200-event
  same-tick burst with truthful deferred outcomes, bounded refresh coalescing
  and the 17-valid-events-per-tick catalog flood, and prints
  `HOST_EVENT_BRIDGE_SELF_TEST_PASS`. The compiled flag itself is
  `NOT_RUN` locally when no serialized Qt toolchain slot is available.
- Foundation: `python tools/check_foundation.py` and the targeted unittest
  modules above. Offscreen compile is `COMPILE_NOT_RUN` unless the dedicated
  Qt toolchain is available and no sibling suite is loading the host.
- No full suite, no VM and no main/protected merge were run in this task.
  Offscreen compile is `COMPILE_NOT_RUN`: at verification time a competing
  `python -m unittest discover -s tests -v` (RI069, PR707 post-merge) and a
  sibling ND-040 CMake/Ninja build were both live on this host, so the suite
  was not quiescent and the serialized Qt build was deliberately not started.

## Resource impact

- Measured (`SYNTHETIC`): Python source-contract and bounded-lifetime test
  counts and durations on the Windows host; static allocation accounting (two
  bridge pointer members, one `QElapsedTimer`, one injectable clock handle,
  four small integer counters, one boolean refresh latch, one `QString`, one
  bounded `QStringList` of at most 16 fixed tokens and one four-entry
  fingerprint vector). Work per accepted event is O(1); no per-event
  allocation, queue growth or background wakeup is added. The latch replaces
  a dropped signal with one bit of state; it never retains caller payload text.
- Deliberately not measured (`NOT_RUN`): real shell-owned PSS/CPU, Mint guest
  behavior, compiled Qt frame timings, monitor/DPI signal rate and full-suite
  deltas. The replacement removes a dead lifetime branch, samples one monotonic
  clock inside `dispatch()` and adds no timer, thread, service, animation or
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
