# Classic suspend/resume source contract (PE-057)

This is a **source contract**, not a desktop or power-management claim. No real
suspend, resume, login, D-Bus call, VM action, Qt signal or compiled UI was
exercised to produce it.

## Boundary

`canopy_features/reliability/suspend_resume_contracts.py` is a decision layer at
the existing host-event boundary. It accepts either:

- an already-delivered `canopy_core.host_events.HostEvent` on the existing
  `session.state.changed` topic (protocol v2, `state` field), or
- an existing reconciled
  `canopy_features.reliability.lock_session_events.SessionState`.

It creates no bus, subscribes to nothing, emits nothing, and performs no I/O,
process, filesystem, network, timer, thread or poll. A trusted host pushes an
observation in; the module returns an immutable decision. It never executes an
operation — the caller owns any eventual host action.

## Fail-closed availability

A host-interaction operation (`read_status`, `open_settings`, `focus_window`,
`launch_app`) is available **only** when the host is confirmed active.

| Phase | Availability | Reason |
| --- | --- | --- |
| `active` | `AVAILABLE` | `ok` |
| `suspended` | `UNAVAILABLE` | `host-suspended` |
| `locked` | `UNAVAILABLE` | `host-locked` |
| `resume_pending` | `UNAVAILABLE` | `resume-needs-reobservation` |
| `unknown` | `UNAVAILABLE` | `unknown-host-state` |

An invalid operation token is `UNAVAILABLE` with `invalid-operation`. Every
reason maps to a fixed disclosure; no observed payload string is ever rendered
or logged by this module.

## Rules

- A suspended observation invalidates any previously active state.
- A live state token observed after suspension enters `resume_pending`. A
  resume event alone never re-enables anything: only an explicit
  `resume_ready()` from a trusted caller that has re-observed the desktop may
  transition to `active`. `resume_ready()` on any other phase is rejected.
- An older event sequence cannot regress a fail-closed phase.
- A malformed `state` field on the correct topic degrades to `unknown` without
  raising, so a host callback cannot be crashed by observed data. A wrong
  caller type or a different topic is a caller contract error.
- `SessionState` is read through its durable `suspended`/`locked` fields, not a
  subclass-supplied label, so a forged view cannot acquire availability.
- History is a bounded immutable tuple (at most 64 phase tokens). Every view is
  read-only, and equal inputs produce identical projections.

## Contract dependencies (no new protocol version)

The `session.state.changed` topic name and the session token vocabulary come
from `canopy_core.host_events` and
`canopy_features.system.quick_controls_state.STATUS_TOKENS`. The module guards
those values at import and refuses to load if they drift; it does not add a
topic, payload field or protocol version of its own.

## Non-claims

`NOT_RUN`: real suspend/resume, real lock/unlock, Mint guest acceptance,
compiled Qt behavior, screen-reader announcements, visual approval and release
readiness. Availability here means "a presentation may offer the operation";
it is not permission to perform it and is not evidence of a working desktop.
