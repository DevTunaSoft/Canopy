# Classic suspend/resume native host path (PE-081)

This is a **source contract**, not a desktop or power-management claim. No real
suspend, resume, login, D-Bus call, VM action, Qt signal, compiled UI, thread,
timer or poll loop was exercised to produce it. It extends, and does not
replace, the pure decision layer in
[`CLASSIC_SUSPEND_RESUME_CONTRACT.md`](CLASSIC_SUSPEND_RESUME_CONTRACT.md).

## Boundary

`canopy_features/reliability/suspend_resume_native.py` is a bounded host-boundary
adapter around the already-merged pure decision layer. A trusted host pushes
already-delivered protocol v2 `HostEvent` values on the existing
`session.state.changed` topic, or an existing reconciled `SessionState`, into a
bounded intake queue. The adapter drains them through
`SuspendResumeContracts.observe()` and returns immutable, read-only decisions.
It never executes an operation, opens a bus, subscribes, emits, or performs
I/O — the caller owns any eventual host action.

No new protocol version, topic or payload field is introduced. The topic and
session token vocabulary remain those of `canopy_core.host_events` and
`canopy_features.system.quick_controls_state.STATUS_TOKENS`.

## Bounded intake and drain

| Constant | Value | Meaning |
| --- | --- | --- |
| `MAX_PENDING` | 32 | hard ceiling on queued host events |
| `MAX_DRAIN` | 16 | hard ceiling on events folded per `drain()` |
| `MAX_BATCH` | 32 | hard ceiling on items read by `submit_many()` |
| `MAX_HISTORY` | 32 | hard ceiling on boundary-loss markers |

- `submit(event)` requires the exact `HostEvent` type, the session topic,
  protocol v2 and a non-negative integer sequence. Hostile caller types raise
  `SuspendResumeNativeError`.
- `submit_many(events)` uses `islice` so at most `max_pending` items are read;
  an endless generator cannot pin a host callback. Scalars, byte strings and
  mappings are refused with the domain error, not a raw `TypeError`.
- `drain(limit=None)` folds at most `max_drain` queued events and reports
  processed/ignored counts. Stale sequences are ignored by the pure layer and
  cannot regress a fail-closed phase.
- Overflow (`reject_new` or `drop_oldest`) is always fail-closed, because an
  unqueued state observation cannot be trusted.

## Fail-closed availability

An operation (`read_status`, `open_settings`, `focus_window`, `launch_app`) is
available only when the host boundary is trusted, no re-observation is owing,
and the pure decision layer has folded a confirmed `active` state.

| Condition | Availability | Reason |
| --- | --- | --- |
| no observation | `UNAVAILABLE` | `unknown-host-state` |
| suspended / locked / resume pending | `UNAVAILABLE` | pure-layer reason |
| boundary lost or intake overflow | `UNAVAILABLE` | `host-boundary-unavailable` |
| path closed | `UNAVAILABLE` | `native-path-closed` |
| re-observation owed | `UNAVAILABLE` | `resume-needs-reobservation` |
| confirmed active, boundary trusted | `AVAILABLE` | `ok` |

Boundary loss (an explicit `mark_host_unavailable()`, overflow or `close()`)
clears the queue and degrades the folded snapshot to `unknown` while preserving
sequence monotonicity, so a late event cannot resurrect a stale `active` phase.
Recovery is two-step and trusted: `mark_host_available()` only reopens intake;
availability stays denied until a fresh `active` event is observed **and**
`resume_ready()` acknowledges re-observation. A resume notification alone never
re-enables anything. `close()` is irreversible.

Every reason maps to a fixed, caller-independent disclosure. No observed
payload string is interpolated into a disclosure or a log line. Every view is
a `MappingProxyType` with fixed key order and bounded history.

## Verification

Targeted offline tests: `python3 -m unittest tests.test_pe081_suspend_resume_native -v`
(21 tests, PASS). Mutation probes show the bounded-batch, overflow-fail-closed
and boundary-denial guards are load-bearing (each mutated guard turns its
single regression test RED; the pristine tree is GREEN). Exact head, artifact
SHA-256 and scope are recorded under
`scratch/master_directive_20261126/evidence/suspend_resume_native/`.

## Resource impact

- Measured (`SYNTHETIC`, in-process Python only): the adapter holds at most 32
  queued `HostEvent` references, a 16-event drain step and a 32-entry marker
  deque. Bounds are enforced by construction and pinned by counting-proxy
  tests; no allocation grows with the input iterator length.
- `NOT_RUN`: real-desktop incremental PSS, average CPU/GPU cost and scheduler
  wakeups (no Linux Mint guest or compiled Qt run in this change).
- `screen-reader`: `NOT_RUN`. The module emits no UI output, announcements or
  visual change; it only returns decision records to its caller.
- No new thread, timer, daemon, socket or poll loop. No stability, security,
  accessibility or approved-visual trade-off is made for a resource gain. No
  visual, QML, C++, asset or workflow path is touched.

## Non-claims

`NOT_RUN`: real suspend/resume, real lock/unlock, Mint guest acceptance,
compiled Qt behavior, screen-reader announcements, visual approval and release
readiness. "Available" means a presentation may *offer* the operation; it is
not permission to perform it and is not evidence of a working desktop.
