# PE-083 logout/shutdown native host-event contracts

Status: **implemented, offline-only**. Base tip:
`778ed45cb361d293ea2452a8ba91e6555cd8df37` (`integration/canopy-classic-20261123`
at the time the task was issued). The exact PR head and its SHA-256 evidence
are recorded in `scratch/master_directive_20261126/evidence/session_logout_shutdown_contracts/`.

Owned paths in this change are only:

- `canopy_features/system/session_controls_native.py`
- `tests/test_pe083_session_controls_native.py`
- `docs/SESSION_CONTROLS_NATIVE_CONTRACT.md` (this document)

No compiled source, QML, approved artwork, workflow, protected path or `main`
is touched. No VM was contacted, no credential was used and no real logout,
reboot, shutdown, D-Bus call or process was performed.

## Boundary

`SessionControlsNativePath` is the bounded host-boundary adapter *beyond* the
existing pure decision layer in `session_controls.py`. A trusted host pushes
already-delivered protocol-v2 `HostEvent` values on the existing
`session.state.changed` topic into a bounded intake queue. The adapter drains
them, keeps a fail-closed session view and folds that view into the unchanged
`evaluate_native_path()` decision. It never emits or subscribes to an event,
opens a bus, executes an action, reads credentials, performs I/O, polls, waits
or starts a thread/timer.

Reused, not extended: protocol v2 and the four-topic allowlist from
`canopy_core.host_events`; the `state` field vocabulary (`active`, `locked`,
`suspended`, `unknown`) and reason/disclosure codes from
`quick_controls_state`; the immutable `NativeCapability`, `Confirmation`,
`NativePath` and `Decision` records plus the unconditional raw-command refusal
from `session_controls`. No new topic, version or payload field is introduced.
The only action tokens remain `logout` and `shutdown`; they are abstract names,
not executables, method names, service calls or shell fragments.

## Bounded intake and drain

| Constant | Value | Meaning |
| --- | --- | --- |
| `MAX_PENDING` | 32 | hard ceiling on queued host events |
| `MAX_DRAIN` | 16 | hard ceiling on events folded per `drain()` |
| `MAX_BATCH` | 32 | hard ceiling on items read by `submit_many()` |
| `MAX_HISTORY` | 32 | hard ceiling on boundary-loss markers |

- `submit()` requires the exact `HostEvent` type, the session topic, protocol
  v2 and a non-negative integer sequence. Envelope and payload violations
  fail closed: the boundary is marked unavailable and the module's domain
  error is raised. No observed text is rendered into a disclosure.
- `submit_many()` uses `islice` with the instance bound, so at most
  `max_pending` items are read. Finite oversized input in the tests proves the
  consume count; scalar, byte string and mapping inputs are refused with the
  domain error rather than a raw `TypeError`.
- `drain(limit=None)` folds at most `max_drain` events. A stale or duplicate
  sequence is ignored without regressing the committed view; an absent or
  unsupported `state` token degrades the boundary to unavailable.
- Overflow (`reject_new` or `drop_oldest`) is always fail-closed, because an
  unqueued observation cannot be trusted.

## Fail-closed availability

A privileged action may be *offered* only when the boundary is trusted, the
session view is `active`, no re-observation is owing, and the unchanged pure
contract returns an allowed path for a matching capability and confirmation.

| Condition | Availability | Reason |
| --- | --- | --- |
| no observation / explicit `unknown` | `UNAVAILABLE` | `no-host-observation` |
| locked or suspended session | `UNAVAILABLE` | `session-not-active` |
| boundary lost or intake overflow | `UNAVAILABLE` | `host-boundary-unavailable` |
| path closed | `UNAVAILABLE` | `native-path-closed` |
| re-observation owed | `UNAVAILABLE` | `session-needs-reobservation` |
| raw command candidate supplied | `UNAVAILABLE` | `raw-command-refused` |
| active + trusted boundary + matching grant | boundary `AVAILABLE` | `ok` |

Returning from a locked or suspended session requires an explicit
`reobserve_ready()` acknowledgement; an `active` event alone never re-enables
an offer. Boundary loss (an explicit `mark_host_unavailable()`, an invalid
event, overflow or `close()`) clears the queue and sets the view back to
`unknown` while preserving sequence monotonicity, so a late event cannot
resurrect a stale `active` view. `mark_host_available()` reopens intake only;
availability stays denied until a fresh observation is acknowledged.
`close()` is irreversible.

`NativeDecision.to_dict()` and `SessionControlsNativePath.to_dict()` return
fresh bounded mappings with `executed: false`, an explicit `execution` token
and no `argv`, command, executable path, D-Bus call or credential field.
Disclosures are fixed strings; no caller-supplied value is interpolated.

## Verification (targeted only)

Commands run from the exact worktree at the final head:

```text
PYTHONPATH=. python -m unittest tests.test_pe083_session_controls_native -v
Ran 49 tests — OK
PYTHONPATH=. python -m unittest tests.test_pe048_session_controls tests.test_host_events tests.test_core_host_events_contract_v2
Ran 41 tests — OK
PYTHONPATH=. python -m py_compile canopy_features/system/session_controls_native.py tests/test_pe083_session_controls_native.py
exit 0, no output
```

RED before the production module existed: `Ran 46 tests`,
`FAILED (errors=46)`, import failure for `session_controls_native`
(`red.log`, rc 1). GREEN after implementation: `green.log`, rc 0. A scratch
mutation probe removed individual guards; each mutated guard turned its single
regression test RED while the pristine tree stayed GREEN, and the production
bytes were restored and verified (`mutation_report.json`). Every log and report
has a SHA-256 sidecar recomputed from on-disk bytes. Full
`unittest discover -s tests` is **NOT_RUN** by this bounded task; only the
owned module and the directly reused boundary tests were run. No Qt build, CI
artifact, compiled self-test or full-suite comparison is claimed.

- `SYNTHETIC` — pure-Python tests with in-memory events and grants, plus a
  scratch source mutation; no network, VM, real session, process spawn or host
  probe.
- `NOT_RUN` — real Mint logout/shutdown/reboot, D-Bus/logind handoff, VM
  session proof, Qt wiring, compiled runtime, real desktop incremental PSS /
  CPU / GPU, screen-reader announcements and owner visual acceptance. No
  acceptance verdict is claimed for any of them.

Resource impact: `SYNTHETIC` bounded work only. The adapter retains at most 32
queued event references, a 16-event drain step and a 32-entry marker deque;
all bounds are enforced by construction and pinned by counting-proxy tests.
There is no timer, cache beyond those deques, polling, background wakeup, I/O
or process. No allocation grows with the length of a caller iterator. There is
no UI, icon, geometry or announcement surface, so `screen-reader` behavior is
unchanged. No stability, security, accessibility or approved-visual tradeoff
is made for a resource gain.
