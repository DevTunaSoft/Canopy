# Classic workspace behavior boundary (PE-086)

`canopy_features/windows/workspace_behavior_contract.py` is a **decision-only**
adapter at the existing `canopy_core.host_events` protocol-v2 boundary. A
trusted host pushes already-delivered `window.state.changed` events into a
bounded queue. The adapter projects each event into a small observation and
folds it through the unchanged
`canopy_features/windows/workspace_state_contract.py` pure decision layer.
It does not duplicate or modify that contract, the window-reference validation
layer, or the suspend/resume paths.

## Existing contract only

- No new topic, payload field, protocol version, callback transport or dynamic
  registration. Only the existing `state`, `window_count` and `source` fields
  are read; an event with any other field is refused.
- `state` must be an exact canonical workspace identifier (`[a-z0-9][a-z0-9-]`,
  at most 64 bytes). The adapter does not normalize or invent one.
- `window_count` is an exact bounded `int` from 0 to 1,000,000. A target with
  zero windows is contradictory and rejected.
- `source` defaults to `host-events`; an explicit source must match the one
  configured on the boundary. Hostile, non-printing or oversized text fails
  closed with `WorkspaceBehaviorError`.
- A missing `state` and `window_count` produces `no_facts`; an explicit zero
  count produces `windows_empty`. Neither can produce a switch offer.

## Decisions and bounds

| Observation | Outcome | Meaning |
| --- | --- | --- |
| `observed` + native-ready pure decision | `switch_offer` | A later trusted host WM bridge *may* request a switch. |
| `observed` + any non-native pure decision | `fallback` | The pure contract's reason is returned verbatim. |
| `no_facts`, `windows_empty` | `defer` | No target is inferred from incomplete facts. |

- Queue capacity 16, default drain 8, history 16. All are
  constructor-pinned ceilings; `drain()` takes a bounded `islice` snapshot and
  builds every decision before removing any queued record.
- Duplicate and stale event sequences are rejected without mutating queued
  facts. Overflow is `reject_new` (fixed rejection token `QUEUE_FULL`) or
  `drop_oldest`. `close()` clears queue, history and context, and all later
  calls fail closed.
- Decisions are fully computed before any queue record is removed; a rejected
  context cannot lose events or publish a partial history.
- Output is immutable read-only mappings with fixed key order.

## Non-claims

The adapter never starts a window manager, activates a window, polls a
compositor, sleeps, launches a process, reads the environment or observes a
desktop. `wm_requests` is 0, `polling` is false, `acceptance` is
`NOT_ESTABLISHED` and `observation` is `NOT_PERFORMED` on every record.
Real X11/Wayland/Mint behavior, compiled Qt wiring, screen-reader announcements
and visual acceptance are **NOT_RUN** here. This is a policy boundary for a
later reviewed host adapter, not evidence that workspace switching works.
