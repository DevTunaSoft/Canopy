# Classic window activation contract (PE-102)

`canopy_features/windows/window_activation_contract.py` is a **decision-only**
adapter at the existing `canopy_core.host_events` protocol-v2 boundary. A
trusted host pushes already-delivered `window.state.changed` events into a
bounded intake queue. The adapter projects each event into a small observation
of the published window state and folds it against a host-pinned target state
using the **unchanged** transition table and negotiation record in
`canopy_features/windows/window_state_capabilities.py` (PR #688). It does not
modify or duplicate that module, the workspace behavior contract (PR #702), the
dock running-indicator source (PR #704), focus intents, window references,
suspend/resume paths or any compiled/Qt layer.

## Existing contract only

- No new host topic, payload field, protocol version, callback or transport.
  Exactly four v2 topics and the `window.state.changed` topic are required at
  import time; no fifth topic or dynamic registration exists here.
- This consumer reads only the already-documented `state` and `source` fields.
  An event carrying any other field (for example `window_count`, `app_id`,
  `pid` or `exit_code`) belongs to a different consumer and is refused.
- `state` must be an exact canonical window-state token (`normal`,
  `minimized`, `maximized`) from the existing `WindowState` enum. Missing state
  yields `no_facts`; hostile, reordered, duplicated or oversized fields fail
  closed with `ActivationError`.
- `source` defaults to `host-events`; an explicit source must equal the one
  pinned on the boundary. Non-printing, surrogate, oversized or malformed text
  is rejected before any decision.
- The host supplies the target state and the capability `Negotiation` as
  trusted context. Events alone cannot choose a target or grant a capability.

## Decisions and bounds

Activation is expressed as `RESTORE` to `normal` from `minimized`; there is no
new action token. The transition table is inverted from the existing
`(current state, action) -> resulting state` mapping, so only already-defined
legal actions can be offered.

| Observed → target | Outcome | Meaning |
| --- | --- | --- |
| `minimized` → `normal` | `offer` (`restore`) | A later trusted WM bridge *may* restore/activate. |
| `normal` → `minimized` | `offer` (`minimize`) | A later bridge *may* minimize. |
| `maximized` → `normal` | `offer` (`restore`) | A later bridge *may* restore. |
| any negotiation refusal | `fallback` | The pure negotiation status is returned verbatim. |
| missing state | `defer` | No target or action is inferred. |
| already at target | `redundant` | No action is offered. |
| `maximized` → `minimized` | `rejected` | Prior state is unknown; refuse to guess. |
| `minimized` → `maximized` | `rejected` | No direct transition exists. |

- Queue capacity 16, default drain 8, history 16. All are constructor-pinned
  ceilings; `drain()` takes a bounded `islice` snapshot and builds **every**
  decision before removing any queued record.
- Duplicate and stale event sequences are rejected without mutating queued
  facts. Overflow is `reject_new` (fixed token `QUEUE_FULL`) or `drop_oldest`.
  `close()` clears queue, history and the negotiation reference, and all later
  calls fail closed.
- Outputs are immutable read-only mappings in fixed key order. Cross-field
  contradictions (an offer without an action, a deferred decision carrying a
  status, a forged success claim) raise `ActivationError` before publication.

## Non-claims and resources

The adapter never starts a window manager, activates/minimizes/restores a real
window, polls a compositor, sleeps, launches a process, reads the environment
or observes a desktop. `wm_requests` is 0, `polling` is false, `acceptance` is
`NOT_ESTABLISHED`, `observation` is `NOT_PERFORMED`, screen-reader behavior is
`NOT_RUN`, `mint_acceptance_proven` and `owner_visual_approval` are false on
every record.

Real X11/Wayland/Mint behavior, compiled Qt wiring, screen-reader announcements
and owner visual approval are all **NOT_RUN** here. This is a policy boundary
for a later reviewed host adapter, not evidence that activation works.

`tests/test_pe102_window_activation_contracts.py` covers event projections,
existing-bus integration, capability offers and fallbacks, contradiction
guards, hostile inputs, queue/history bounds, stale-sequence rejection,
lifecycle cleanup and the fixed negative claims. Tests use inert in-process
records and must not be represented as Mint guest, compositor or visual
acceptance.
